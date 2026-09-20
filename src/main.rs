use braess_router::{
    Case, Decision, ROUTES, Record, Response, Rubric, baseline, cases_for_rubric, gate, metrics,
    percentile,
};
use serde_json::json;
use std::{
    error::Error,
    fs,
    io::{Read, Write},
    path::PathBuf,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

const ENDPOINT: &str = "https://api.typesafe.ai/v1/systemone";

struct Options {
    live: bool,
    key_file: Option<PathBuf>,
    out: PathBuf,
    split: String,
    rubric: PathBuf,
    cases: PathBuf,
}

fn options() -> Result<Options, String> {
    let mut result = Options {
        live: false,
        key_file: None,
        out: "eval/results/baseline.json".into(),
        split: "all".into(),
        rubric: "eval/rubric.json".into(),
        cases: "eval/cases.jsonl".into(),
    };
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--live"=>result.live=true,
            "--key-file"=>result.key_file=Some(args.next().ok_or("Missing key file")?.into()),
            "--out"=>result.out=args.next().ok_or("Missing output path")?.into(),
            "--split"=>result.split=args.next().ok_or("Missing split")?,
            "--rubric"=>result.rubric=args.next().ok_or("Missing rubric path")?.into(),
            "--cases"=>result.cases=args.next().ok_or("Missing cases path")?.into(),
            "--help"=>return Err("Usage: cargo run -- [--live] [--key-file PATH] [--rubric PATH] [--cases PATH] [--split all|dev|heldout] [--out PATH]".into()),
            _=>return Err(format!("Unknown argument: {arg}")),
        }
    }
    if !["all", "dev", "heldout"].contains(&result.split.as_str()) {
        return Err("Invalid split".into());
    }
    Ok(result)
}

fn key(path: Option<&PathBuf>) -> Result<String, String> {
    if let Ok(value) = std::env::var("TYPESAFE_API_KEY")
        && !value.trim().is_empty()
    {
        return Ok(value.trim().into());
    }
    if let Some(path) = path {
        // Parse only literal assignments. Never source or execute credential files.
        let content = fs::read_to_string(path).map_err(|_| "Cannot read key file")?;
        for line in content.lines() {
            let line = line.trim().strip_prefix("export ").unwrap_or(line.trim());
            if let Some((name, value)) = line.split_once('=')
                && ["API_KEY", "TYPESAFE_API_KEY"].contains(&name.trim())
            {
                let value = value.trim();
                let value = value
                    .strip_prefix('"')
                    .and_then(|s| s.strip_suffix('"'))
                    .or_else(|| value.strip_prefix('\'').and_then(|s| s.strip_suffix('\'')))
                    .unwrap_or(value);
                if !value.is_empty() {
                    return Ok(value.into());
                }
            }
        }
    }
    Err("Set TYPESAFE_API_KEY or pass --key-file; no credential values are logged".into())
}

fn evaluate(
    client: &reqwest::blocking::Client,
    token: &str,
    rubric: &Rubric,
    case: &Case,
) -> Result<Response, String> {
    let response = client
        .post(ENDPOINT)
        .bearer_auth(token)
        .json(&rubric.request(case))
        .send()
        .map_err(|e| {
            if e.is_timeout() {
                "timeout"
            } else {
                "transport_error"
            }
            .to_string()
        })?;
    decode_response(response.status().as_u16(), response)
}

fn decode_response(status: u16, body: impl Read) -> Result<Response, String> {
    if !(200..300).contains(&status) {
        return Err(format!("http_{status}"));
    }
    // Do not log raw HTTP bodies, headers, or transport errors containing credentials.
    let mut bytes = Vec::new();
    body.take(65537)
        .read_to_end(&mut bytes)
        .map_err(|_| "response_read_error")?;
    if bytes.len() > 65536 {
        return Err("response_too_large".into());
    }
    serde_json::from_slice(&bytes).map_err(|_| "invalid_response_json".into())
}

fn persist_event(file: &mut fs::File, event: serde_json::Value) -> std::io::Result<()> {
    let mut line = serde_json::to_vec(&event)?;
    line.push(b'\n');
    file.write_all(&line)?;
    file.sync_all()
}

fn run() -> Result<(), Box<dyn Error>> {
    let opts = options()?;
    let rubric_text = fs::read_to_string(&opts.rubric)?;
    let rubric: Rubric = serde_json::from_str(&rubric_text)?;
    rubric.validate()?;
    let cases = cases_for_rubric(&fs::read_to_string(&opts.cases)?, &rubric)?;
    let catalog = rubric.questions["route"]["criteria"]
        .as_object()
        .ok_or("Missing catalog")?;
    let legacy_baseline =
        catalog.len() == ROUTES.len() && ROUTES.iter().all(|r| catalog.contains_key(*r));
    let baseline_policy = if legacy_baseline {
        "legacy_keyword"
    } else {
        "always_fallback"
    };
    let selected: Vec<_> = cases
        .into_iter()
        .filter(|c| opts.split == "all" || c.split == opts.split)
        .collect();
    if selected.is_empty() {
        return Err("No selected cases".into());
    }
    if let Some(parent) = opts.out.parent().filter(|p| !p.as_os_str().is_empty()) {
        fs::create_dir_all(parent)?;
    }
    // Refuse to overwrite earlier evidence, and check writability before paid calls.
    let mut output = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&opts.out)?;
    let token = if opts.live {
        Some(key(opts.key_file.as_ref())?)
    } else {
        None
    };
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(10))
        .connect_timeout(Duration::from_secs(3))
        .redirect(reqwest::redirect::Policy::none())
        .build()?;
    let started = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
    let planned = selected.len();
    let mut log_name = opts.out.as_os_str().to_os_string();
    log_name.push(".attempts.jsonl");
    let log_path = PathBuf::from(log_name);
    let mut attempt_log = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&log_path)?;
    persist_event(
        &mut attempt_log,
        json!({"event":"header", "version":1,
        "live":opts.live,"started_unix_seconds":started,"rubric":rubric,
        "baseline_policy":baseline_policy,"planned_cases":selected}),
    )?;
    fs::File::open(
        log_path
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(std::path::Path::new(".")),
    )?
    .sync_all()?;
    let mut records = Vec::new();
    let mut consecutive_errors = 0;
    for case in selected {
        // No provider request starts unless its intent is durably recorded.
        persist_event(
            &mut attempt_log,
            json!({"event":"begin", "case_id":case.id}),
        )?;
        let baseline = if legacy_baseline {
            baseline(&case.request)
        } else {
            "fallback"
        }
        .to_string();
        let mut record = Record {
            case,
            baseline: baseline.clone(),
            decision: Decision {
                route: baseline,
                reason: "baseline".into(),
            },
            latency_ms: None,
            error: None,
            response: None,
        };
        if let Some(token) = &token {
            let start = Instant::now();
            match evaluate(&client, token, &rubric, &record.case) {
                Ok(response) => {
                    match gate(&response, &rubric) {
                        Ok(decision) => record.decision = decision,
                        Err(error) => record.error = Some(error),
                    }
                    record.response = Some(response);
                }
                Err(error) => record.error = Some(error),
            }
            record.latency_ms = Some(start.elapsed().as_secs_f64() * 1000.0);
            if record.error.is_some() {
                record.decision = Decision {
                    route: "fallback".into(),
                    reason: "error".into(),
                };
                consecutive_errors += 1;
            } else {
                consecutive_errors = 0;
            }
            eprintln!(
                "{}: {} ({})",
                record.case.id,
                record.decision.route,
                record.error.as_deref().unwrap_or(&record.decision.reason)
            );
        }
        let stop_auth = record
            .error
            .as_deref()
            .is_some_and(|e| ["http_401", "http_403", "http_402"].contains(&e));
        persist_event(
            &mut attempt_log,
            json!({"event":"outcome", "record":record}),
        )?;
        records.push(record);
        if consecutive_errors >= 3 || stop_auth {
            break;
        }
        if opts.live {
            std::thread::sleep(Duration::from_millis(200));
        }
    }
    let mut splits = serde_json::Map::new();
    for split in ["all", "dev", "heldout"] {
        let subset: Vec<_> = records
            .iter()
            .filter(|r| split == "all" || r.case.split == split)
            .collect();
        if !subset.is_empty() {
            splits.insert(split.into(),json!({"baseline":metrics(&subset,true),"jev":if opts.live{metrics(&subset,false)}else{serde_json::Value::Null}}));
        }
    }
    let mut latency: Vec<_> = records.iter().filter_map(|r| r.latency_ms).collect();
    let input_tokens: u64 = records
        .iter()
        .filter_map(|r| r.response.as_ref().map(|v| v.usage.input_tokens))
        .sum();
    let output_tokens: u64 = records
        .iter()
        .filter_map(|r| r.response.as_ref().map(|v| v.usage.output_tokens))
        .sum();
    let report = json!({
        "schema_version":2,"started_unix_seconds":started,"live":opts.live,
        "metric_semantics":"failed_calls_are_errors_not_semantic_fallbacks",
        "attempt_log":log_path,
        "dataset_kind":if opts.cases == std::path::Path::new("eval/cases.jsonl") { "synthetic_smoke_not_production_benchmark" } else { "operator_supplied_unvalidated" },
        "baseline_policy":baseline_policy,"cases_path":opts.cases,"rubric_path":opts.rubric,
        "planned_cases":planned,"completed_cases":records.len(),
        "complete":records.len()==planned,"rubric":rubric,"splits":splits,
        "latency_ms":{"p50":percentile(&mut latency,0.5),"p95":percentile(&mut latency,0.95)},
        "usage":{"input_tokens":input_tokens,"output_tokens":output_tokens,"estimated_usd":input_tokens as f64*0.042/1_000_000.0,
            "pricing_source":"https://docs.typesafe.ai/models","price_checked":"2026-09-19",
            "note":"Estimate from returned usage only; failed requests may have unreported billing."},
        "records":records
    });
    serde_json::to_writer_pretty(&mut output, &report)?;
    output.write_all(b"\n")?;
    output.sync_all()?;
    persist_event(
        &mut attempt_log,
        json!({"event":"report_written", "attempted":records.len(), "complete":records.len()==planned}),
    )?;
    println!(
        "Saved {} ({} / {} cases)",
        opts.out.display(),
        records.len(),
        planned
    );
    println!("{}", serde_json::to_string_pretty(&report["splits"])?);
    if records.iter().any(|r| r.error.is_some()) {
        return Err("Evaluation contains API/contract errors; inspect the saved report".into());
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn http_errors_never_expose_response_bodies() {
        for status in [401, 403, 422, 429, 500, 529] {
            let result = decode_response(status, b"sensitive provider error".as_slice());
            assert_eq!(result.unwrap_err(), format!("http_{status}"));
        }
    }

    #[test]
    fn malformed_or_oversized_responses_fail_closed() {
        assert_eq!(
            decode_response(200, b"not json".as_slice()).unwrap_err(),
            "invalid_response_json"
        );
        assert_eq!(
            decode_response(200, b"{}".as_slice()).unwrap_err(),
            "invalid_response_json"
        );
        let oversized = vec![b' '; 65537];
        assert_eq!(
            decode_response(200, oversized.as_slice()).unwrap_err(),
            "response_too_large"
        );
    }
}
