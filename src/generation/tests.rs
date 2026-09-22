use super::*;
use std::{
    fs,
    sync::atomic::{AtomicU64, Ordering},
};
static NEXT: AtomicU64 = AtomicU64::new(0);
struct Temp(PathBuf);
impl Temp {
    fn new() -> Self {
        let p = std::env::temp_dir().join(format!(
            "braess-openrouter-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&p).unwrap();
        Self(p)
    }
}
impl Drop for Temp {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn config(p: &Temp) -> Config {
    Config {
        backend: Backend::Openrouter,
        bind: "127.0.0.1:8089".parse().unwrap(),
        mode: Mode::Mock,
        url: "http://127.0.0.1:8090/chat/completions".into(),
        journal_path: p.0.join("requests.jsonl"),
        deadline_ms: 1000,
        max_request_bytes: 4096,
        max_response_bytes: 8192,
        admission_limit: 1,
        max_calls: 2,
        vision_bundles: BTreeMap::new(),
        routes: BTreeMap::from([(
            "coding".into(),
            Route {
                model: "fixture/code-v1".into(),
                provider: "fixture".into(),
                reasoning: None,
                output_format: None,
                max_tokens: 32,
                input_mode: InputMode::Text,
            },
        )]),
    }
}
fn response() -> Value {
    json!({"id":"gen-fixture","object":"chat.completion","model":"fixture/code-v1","provider":"Fixture","choices":[{"index":0,"finish_reason":"stop","message":{"role":"assistant","content":"answer"}}],"usage":{"prompt_tokens":4,"completion_tokens":2,"total_tokens":6,"cost":0.000001}})
}
#[test]
fn response_contract_retains_usage_without_exposing_reasoning() {
    let mut v = response();
    v["choices"][0]["message"]["reasoning"] = json!("private");
    let out = decode(
        &serde_json::to_vec(&v).unwrap(),
        1,
        "coding",
        "fixture/code-v1",
    )
    .unwrap();
    assert_eq!(out.execution.usage.total_tokens, 6);
    assert!(!serde_json::to_string(&out).unwrap().contains("private"));
}
#[test]
fn malformed_or_unsupported_responses_never_complete() {
    for mutation in 0..8 {
        let mut v = response();
        match mutation {
            0 => v["usage"]["total_tokens"] = json!(7),
            1 => v["choices"][0]["message"]["tool_calls"] = json!([{}]),
            2 => v["choices"][0]["finish_reason"] = json!("tool_calls"),
            3 => v["error"] = json!({"message":"private"}),
            4 => v["id"] = json!(""),
            5 => v["usage"]["cost"] = json!(-1),
            6 => v["choices"][0]["message"]["content"] = Value::Null,
            _ => v["choices"][0]["message"]["role"] = json!("user"),
        };
        assert!(
            decode(
                &serde_json::to_vec(&v).unwrap(),
                1,
                "coding",
                "fixture/code-v1"
            )
            .is_err(),
            "mutation {mutation}"
        );
    }
}
#[test]
fn config_restricts_destinations_and_catalog() {
    let temp = Temp::new();
    let c = config(&temp);
    c.validate().unwrap();
    for url in [
        "http://localhost/chat",
        "http://10.0.0.1/x",
        "http://user:secret@127.0.0.1/x",
        "http://127.0.0.1/x?key=secret",
        "http://127.0.0.1/x#frag",
        "https://evil.test/x",
    ] {
        let mut changed = c.clone();
        changed.url = url.into();
        assert!(changed.validate().is_err());
    }
    let mut live = c.clone();
    live.mode = Mode::Live;
    live.url = LIVE_URL.into();
    live.validate().unwrap();
    assert!(Adapter::new(live, None).is_err());
    let mut changed = c.clone();
    changed.routes.get_mut("coding").unwrap().model = "openrouter/auto".into();
    assert!(changed.validate().is_err());
    assert!(
        serde_json::from_value::<Request>(json!({"request":"x","route":"coding","model":"evil"}))
            .is_err()
    );
}
#[test]
fn restart_retains_uncertainty_and_exclusive_owner() {
    let temp = Temp::new();
    let c = config(&temp);
    Adapter::initialize(&c).unwrap();
    assert!(Adapter::initialize(&c).is_err());
    let mut journal = Journal::open(&c).unwrap();
    assert!(Journal::open(&c).is_err());
    journal
        .begin("coding".into(), "fixture/code-v1".into())
        .unwrap();
    drop(journal);
    let mut journal = Journal::open(&c).unwrap();
    assert_eq!(journal.status()["pending"], 1);
    assert_eq!(
        journal
            .begin("coding".into(), "fixture/code-v1".into())
            .unwrap_err()
            .code,
        "generation_admission_full"
    );
}
#[test]
fn receipts_survive_restart_and_call_budget_never_refunds() {
    let temp = Temp::new();
    let c = config(&temp);
    Adapter::initialize(&c).unwrap();
    let mut j = Journal::open(&c).unwrap();
    for expected in 1..=2 {
        let id = j.begin("coding".into(), "fixture/code-v1".into()).unwrap();
        assert_eq!(id, expected);
        let r = decode(
            &serde_json::to_vec(&response()).unwrap(),
            id,
            "coding",
            "fixture/code-v1",
        )
        .unwrap()
        .execution;
        j.complete(r).unwrap();
    }
    drop(j);
    let mut j = Journal::open(&c).unwrap();
    assert_eq!(j.status()["completed"], 2);
    assert_eq!(j.status()["pending"], 0);
    assert_eq!(j.status()["prompt_tokens_observed"], 8);
    assert_eq!(
        j.begin("coding".into(), "fixture/code-v1".into())
            .unwrap_err()
            .code,
        "generation_call_budget_exhausted"
    );
    let text = fs::read_to_string(&c.journal_path).unwrap();
    assert!(!text.contains("answer"));
}
#[test]
fn corrupted_or_changed_scope_refuses_startup() {
    let temp = Temp::new();
    let c = config(&temp);
    Adapter::initialize(&c).unwrap();
    let mut changed = c.clone();
    changed.routes.get_mut("coding").unwrap().max_tokens = 64;
    assert!(Journal::open(&changed).is_err());
    use std::io::Write;
    let mut f = fs::OpenOptions::new()
        .append(true)
        .open(&c.journal_path)
        .unwrap();
    f.write_all(b"{torn").unwrap();
    assert!(Journal::open(&c).is_err());
}
#[test]
fn receipt_must_match_its_reservation() {
    let temp = Temp::new();
    let c = config(&temp);
    Adapter::initialize(&c).unwrap();
    let mut j = Journal::open(&c).unwrap();
    let id = j.begin("coding".into(), "fixture/code-v1".into()).unwrap();
    let r = decode(
        &serde_json::to_vec(&response()).unwrap(),
        id,
        "general",
        "fixture/code-v1",
    )
    .unwrap()
    .execution;
    assert!(j.complete(r).is_err());
    assert_eq!(j.status()["pending"], 1);
}

#[test]
fn text_config_serialization_preserves_existing_journal_scope() {
    let temp = Temp::new();
    let original = config(&temp);
    let serialized = serde_json::to_value(&original).unwrap();
    assert!(serialized.get("vision_bundles").is_none());
    assert!(serialized["routes"]["coding"].get("input_mode").is_none());
    let roundtrip: Config = serde_json::from_value(serialized).unwrap();
    assert_eq!(original.scope().unwrap(), roundtrip.scope().unwrap());
    assert_eq!(roundtrip.routes["coding"].input_mode, InputMode::Text);
}

#[test]
fn image_mode_requires_bounded_explicit_registry() {
    let temp = Temp::new();
    let mut c = config(&temp);
    c.routes.get_mut("coding").unwrap().input_mode = InputMode::VisionReference;
    assert!(c.validate().is_err());
    c.vision_bundles
        .insert("a".repeat(64), temp.0.join("source"));
    c.validate().unwrap();
    assert!(Adapter::initialize(&c).is_err());
    assert!(!c.journal_path.exists());
    c.admission_limit = 5;
    assert!(c.validate().is_err());
    c.admission_limit = 1;
    c.vision_bundles.insert("bad".into(), temp.0.join("source"));
    assert!(c.validate().is_err());
}

#[test]
fn image_receipt_rejects_unbounded_or_invalid_hash_evidence() {
    let mut r = decode(
        &serde_json::to_vec(&response()).unwrap(),
        1,
        "coding",
        "fixture/code-v1",
    )
    .unwrap()
    .execution;
    r.input_evidence = Some(InputEvidence {
        reference_sha256: "a".repeat(64),
        image_sha256: vec!["b".repeat(64)],
    });
    assert!(r.valid());
    r.input_evidence.as_mut().unwrap().image_sha256 = vec!["b".repeat(64); 9];
    assert!(!r.valid());
    r.input_evidence.as_mut().unwrap().image_sha256 = vec!["bad".into()];
    assert!(!r.valid());
}

#[test]
fn fastmetal_observed_contracts_keep_currency_and_reasoning_separate() {
    for bytes in [
        include_bytes!("fixtures/fastmetal-text.json").as_slice(),
        include_bytes!("fixtures/fastmetal-reasoning.json").as_slice(),
        include_bytes!("fixtures/fastmetal-vision.json").as_slice(),
        include_bytes!("fixtures/fastmetal-structured.json").as_slice(),
    ] {
        let value: Value = serde_json::from_slice(bytes).unwrap();
        let model = value["model"].as_str().unwrap();
        let output = decode_fastmetal(
            bytes,
            1,
            "general",
            model,
            Some(serde_json::Number::from_f64(0.1).unwrap()),
        )
        .unwrap();
        assert_eq!(output.execution.backend, Backend::Fastmetal);
        assert!(output.execution.usage.cost.is_none());
        assert_eq!(
            output
                .execution
                .reported_cost_jpy
                .as_ref()
                .unwrap()
                .as_f64(),
            Some(0.1)
        );
        assert!(
            !serde_json::to_string(&output)
                .unwrap()
                .contains("reasoning_content")
        );
        assert!(decode_fastmetal(bytes, 1, "general", "wrong-model", None).is_err());
    }
    assert!(
        decode_fastmetal(
            include_bytes!("fixtures/fastmetal-tool.json"),
            1,
            "general",
            "gpt-4.1-nano",
            None
        )
        .is_err()
    );
    for mutation in 0..4 {
        let mut v: Value =
            serde_json::from_slice(include_bytes!("fixtures/fastmetal-text.json")).unwrap();
        match mutation {
            0 => v["usage"]["completion_tokens_details"]["reasoning_tokens"] = json!(999),
            1 => v["usage"]["completion_tokens_details"]["reasoning_tokens"] = json!(-1),
            2 => v["choices"][0]["message"]["content"] = json!(" "),
            _ => v["choices"][0]["message"]["content"] = Value::Null,
        }
        assert!(
            decode_fastmetal(
                &serde_json::to_vec(&v).unwrap(),
                1,
                "general",
                "gpt-4.1-nano",
                None
            )
            .is_err()
        );
    }
}

#[test]
fn fastmetal_fixed_routes_and_wire_settings() {
    let temp = Temp::new();
    let mut c = config(&temp);
    c.backend = Backend::Fastmetal;
    let route = c.routes.get_mut("coding").unwrap();
    route.model = "gpt-oss-20b".into();
    route.provider.clear();
    route.reasoning = Some(Reasoning::Effort {
        effort: Effort::Low,
    });
    route.output_format = Some(OutputFormat::JsonObject);
    let body = request_body(Backend::Fastmetal, route, json!("Return JSON"));
    assert_eq!(body["reasoning"], json!({"effort":"low"}));
    assert_eq!(body["response_format"], json!({"type":"json_object"}));
    assert!(body.get("provider").is_none());
    assert_eq!(body["stream"], false);
    assert!(c.validate().is_ok());
    for bad in ["auto", "random-free", "provider/model", "", "../model"] {
        c.routes.get_mut("coding").unwrap().model = bad.into();
        assert!(c.validate().is_err(), "{bad}");
    }
}
