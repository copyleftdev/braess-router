use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;

pub mod admission;
pub mod durable_budget;
pub mod durable_requests;
pub mod gateway;
pub mod ledger_http;
pub mod local_http;
pub mod openrouter;
pub mod rate_limit;
pub mod request_ledger;
pub mod simulation;

/// Stable operator label; fallback is reserved by the routing policy.
pub fn valid_route_label(label: &str) -> bool {
    !label.is_empty()
        && label.len() <= 64
        && label.as_bytes()[0].is_ascii_lowercase()
        && label
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_' || b == b'-')
}

pub const ROUTES: [&str; 4] = ["general", "coding", "reasoning", "fallback"];

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Case {
    pub id: String,
    pub split: String,
    pub tag: String,
    pub request: String,
    pub expected: String,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Rubric {
    pub version: String,
    pub model: String,
    pub min_confidence: f64,
    pub min_probability: f64,
    pub min_supported: f64,
    pub questions: Value,
}

impl Rubric {
    pub fn validate(&self) -> Result<(), String> {
        if self.model != "jev-1.13.0" || self.version.is_empty() {
            return Err("Use a pinned, reviewed model and a versioned rubric".into());
        }
        if ![
            self.min_confidence,
            self.min_probability,
            self.min_supported,
        ]
        .into_iter()
        .all(probability)
        {
            return Err("Thresholds must be finite probabilities".into());
        }
        let criteria = self.questions["route"]["criteria"]
            .as_object()
            .ok_or("Missing route criteria")?;
        if !(2..=33).contains(&criteria.len())
            || !criteria.contains_key("fallback")
            || criteria.keys().any(|key| !valid_route_label(key))
        {
            return Err("Rubric requires 1..32 named routes plus local fallback".into());
        }
        Ok(())
    }

    pub fn request(&self, case: &Case) -> Value {
        // Labels, split, IDs and tags never reach the model.
        json!({"model": self.model, "state": {"request": case.request}, "questions": self.questions})
    }
}

pub fn cases_from_jsonl(input: &str) -> Result<Vec<Case>, String> {
    parse_cases(input, &ROUTES)
}

/// Validate expected labels against the same operator catalog used by the gate.
pub fn cases_for_rubric(input: &str, rubric: &Rubric) -> Result<Vec<Case>, String> {
    rubric.validate()?;
    let labels: Vec<_> = rubric.questions["route"]["criteria"]
        .as_object()
        .ok_or("Missing route criteria")?
        .keys()
        .map(String::as_str)
        .collect();
    parse_cases(input, &labels)
}

fn parse_cases(input: &str, labels: &[&str]) -> Result<Vec<Case>, String> {
    let mut cases = Vec::new();
    let mut ids = std::collections::BTreeSet::new();
    for line in input.lines().filter(|s| !s.trim().is_empty()) {
        let case: Case = serde_json::from_str(line).map_err(|e| e.to_string())?;
        if !labels.contains(&case.expected.as_str())
            || !["dev", "heldout"].contains(&case.split.as_str())
            || case.request.trim().is_empty()
            || case.request.len() > 8000
            || !ids.insert(case.id.clone())
        {
            return Err("Invalid case, duplicate ID, or request over 8000 bytes".into());
        }
        cases.push(case);
    }
    if cases.is_empty() || cases.len() > 40 {
        return Err("Evaluation requires 1–40 cases".into());
    }
    Ok(cases)
}

pub fn baseline(request: &str) -> &'static str {
    let text = request.to_lowercase();
    if [
        "right now",
        "current price",
        "bank account",
        "attached",
        "fix it",
        "routing rules",
    ]
    .iter()
    .any(|w| text.contains(w))
    {
        return "fallback";
    }
    if [
        "rust",
        "python",
        "javascript",
        "sql",
        "debug",
        "function",
        "code",
    ]
    .iter()
    .any(|w| text.contains(w))
    {
        return "coding";
    }
    if [
        "prove",
        "logic",
        "schedule",
        "solve",
        "equation",
        "step by step",
    ]
    .iter()
    .any(|w| text.contains(w))
    {
        return "reasoning";
    }
    "general"
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum Answer {
    Choice {
        choice: String,
        probabilities: BTreeMap<String, f64>,
        confidence: f64,
    },
    Noul {
        noul: f64,
    },
}

#[derive(Debug, Deserialize, Serialize)]
pub struct Response {
    pub model: String,
    pub answers: BTreeMap<String, Answer>,
    pub usage: Usage,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct Usage {
    pub input_tokens: u64,
    pub output_tokens: u64,
}

#[derive(Debug, Serialize)]
pub struct Decision {
    pub route: String,
    pub reason: String,
}

fn probability(p: f64) -> bool {
    p.is_finite() && (0.0..=1.0).contains(&p)
}

pub fn gate(response: &Response, rubric: &Rubric) -> Result<Decision, String> {
    rubric.validate()?;
    let catalog = rubric.questions["route"]["criteria"]
        .as_object()
        .ok_or("missing_catalog")?;
    if response.model != rubric.model {
        return Err("model_mismatch".into());
    }
    if response.answers.len() != 2 {
        return Err("answer_count".into());
    }
    let Some(Answer::Choice {
        choice,
        probabilities,
        confidence,
    }) = response.answers.get("route")
    else {
        return Err("route_answer_type".into());
    };
    let Some(Answer::Noul { noul }) = response.answers.get("supported") else {
        return Err("supported_answer_type".into());
    };
    if probabilities.len() != catalog.len()
        || !catalog.keys().all(|r| probabilities.contains_key(r))
        || !probabilities.values().copied().all(probability)
        || !probability(*confidence)
        || !probability(*noul)
        || (probabilities.values().sum::<f64>() - 1.0).abs() > 0.001
    {
        return Err("invalid_distribution".into());
    }
    let Some(&chosen) = probabilities.get(choice) else {
        return Err("unknown_route".into());
    };
    if probabilities.values().any(|p| *p > chosen + 1e-9) {
        return Err("choice_not_maximum".into());
    }
    let reason = if choice == "fallback" {
        "model_fallback"
    } else if *noul < rubric.min_supported {
        "unsupported"
    } else if *confidence < rubric.min_confidence || chosen < rubric.min_probability {
        "uncertain"
    } else if probabilities
        .iter()
        .any(|(k, p)| k != choice && (p - chosen).abs() < 1e-9)
    {
        "tie"
    } else {
        "accepted"
    };
    Ok(Decision {
        route: if reason == "accepted" {
            choice.clone()
        } else {
            "fallback".into()
        },
        reason: reason.into(),
    })
}

#[derive(Serialize)]
pub struct Record {
    pub case: Case,
    pub baseline: String,
    pub decision: Decision,
    pub latency_ms: Option<f64>,
    pub error: Option<String>,
    pub response: Option<Response>,
}

pub fn metrics(records: &[&Record], use_baseline: bool) -> Value {
    let n = records.len();
    let mut correct = 0;
    let mut automatic = 0;
    let mut wrong_automatic = 0;
    let mut unnecessary_fallbacks = 0;
    let mut errors = 0;
    let mut confusion: BTreeMap<String, BTreeMap<String, usize>> = BTreeMap::new();
    for r in records {
        // Transport/contract failures are not successful semantic abstentions.
        // Keep them in the accuracy denominator without awarding label credit.
        if !use_baseline && r.error.is_some() {
            errors += 1;
            *confusion
                .entry(r.case.expected.clone())
                .or_default()
                .entry("__error__".into())
                .or_default() += 1;
            continue;
        }
        let actual = if use_baseline {
            &r.baseline
        } else {
            &r.decision.route
        };
        correct += usize::from(actual == &r.case.expected);
        automatic += usize::from(actual != "fallback");
        wrong_automatic += usize::from(actual != "fallback" && actual != &r.case.expected);
        unnecessary_fallbacks += usize::from(actual == "fallback" && r.case.expected != "fallback");
        *confusion
            .entry(r.case.expected.clone())
            .or_default()
            .entry(actual.clone())
            .or_default() += 1;
    }
    json!({"cases": n, "correct": correct, "automatic": automatic, "wrong_automatic": wrong_automatic,
        "fallbacks": n - automatic - errors, "unnecessary_fallbacks": unnecessary_fallbacks, "errors": errors,
        "valid_decisions": n - errors, "error_rate": ratio(errors,n),
        "accuracy": ratio(correct,n), "coverage": ratio(automatic,n),
        "automatic_error_rate": ratio(wrong_automatic,automatic), "confusion_expected_to_actual": confusion})
}

fn ratio(a: usize, b: usize) -> Option<f64> {
    (b != 0).then(|| a as f64 / b as f64)
}

pub fn percentile(values: &mut [f64], quantile: f64) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    Some(values[(quantile * values.len() as f64).ceil().max(1.0) as usize - 1])
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rubric() -> Rubric {
        serde_json::from_str(include_str!("../eval/rubric.json")).unwrap()
    }
    fn response() -> Response {
        serde_json::from_value(
            json!({"model":"jev-1.13.0", "usage":{"input_tokens":400,"output_tokens":80},
            "answers":{"route":{"type":"choice","choice":"coding","confidence":0.9,
                "probabilities":{"coding":0.94,"general":0.02,"reasoning":0.03,"fallback":0.01}},
                "supported":{"type":"noul","noul":0.99}}}),
        )
        .unwrap()
    }

    #[test]
    fn custom_catalog_accepts_its_labels_and_rejects_demo_distribution() {
        let mut rubric = rubric();
        rubric.questions["route"]["criteria"] =
            json!({"billing":"Billing", "support":"Technical support", "fallback":"Review"});
        rubric.validate().unwrap();
        assert!(gate(&response(), &rubric).is_err());
        let mut reply = response();
        reply.answers.insert(
            "route".into(),
            Answer::Choice {
                choice: "billing".into(),
                confidence: 0.99,
                probabilities: BTreeMap::from([
                    ("billing".into(), 0.98),
                    ("support".into(), 0.01),
                    ("fallback".into(), 0.01),
                ]),
            },
        );
        assert_eq!(gate(&reply, &rubric).unwrap().route, "billing");
        for label in [
            "",
            "../billing",
            "https://evil.invalid",
            "Uppercase",
            "fallback space",
        ] {
            assert!(!valid_route_label(label));
        }
        rubric.questions["route"]["criteria"] = json!({"billing":"Billing"});
        assert!(rubric.validate().is_err());
    }
    #[test]
    fn valid_and_uncertain_decisions() {
        let mut r = response();
        assert_eq!(gate(&r, &rubric()).unwrap().route, "coding");
        r.answers
            .insert("supported".into(), Answer::Noul { noul: 0.5 });
        assert_eq!(gate(&r, &rubric()).unwrap().route, "fallback");
        r.answers
            .insert("supported".into(), Answer::Noul { noul: 0.99 });
        if let Answer::Choice { confidence, .. } = r.answers.get_mut("route").unwrap() {
            *confidence = 0.5;
        }
        assert_eq!(gate(&r, &rubric()).unwrap().reason, "uncertain");
    }

    #[test]
    fn rejects_contract_violations() {
        for corruption in 0..6 {
            let mut r = response();
            if let Answer::Choice {
                choice,
                probabilities,
                confidence,
            } = r.answers.get_mut("route").unwrap()
            {
                match corruption {
                    0 => *choice = "invented".into(),
                    1 => {
                        probabilities.insert("coding".into(), 0.4);
                    }
                    2 => *confidence = f64::NAN,
                    3 => *choice = "general".into(),
                    4 => {
                        probabilities.remove("fallback");
                    }
                    _ => r.model = "jev-latest".into(),
                }
            }
            assert!(gate(&r, &rubric()).is_err(), "corruption {corruption}");
        }
    }

    #[test]
    fn missing_answers_and_wrong_types_are_rejected() {
        let mut r = response();
        r.answers.remove("supported");
        assert!(gate(&r, &rubric()).is_err());
        r.answers
            .insert("supported".into(), Answer::Noul { noul: 2.0 });
        assert!(gate(&r, &rubric()).is_err());
        r.answers
            .insert("route".into(), Answer::Noul { noul: 0.99 });
        assert!(gate(&r, &rubric()).is_err());
    }

    #[test]
    fn low_winner_probability_and_ties_abstain() {
        let mut r = response();
        if let Answer::Choice { probabilities, .. } = r.answers.get_mut("route").unwrap() {
            *probabilities = BTreeMap::from([
                ("coding".into(), 0.5),
                ("general".into(), 0.5),
                ("reasoning".into(), 0.0),
                ("fallback".into(), 0.0),
            ]);
        }
        assert_eq!(gate(&r, &rubric()).unwrap().reason, "uncertain");
        let mut relaxed = rubric();
        relaxed.min_probability = 0.0;
        assert_eq!(gate(&r, &relaxed).unwrap().reason, "tie");
    }

    #[test]
    fn failed_calls_never_receive_fallback_accuracy_credit() {
        let cases = cases_from_jsonl(include_str!("../eval/cases.jsonl")).unwrap();
        let records: Vec<_> = cases
            .into_iter()
            .take(3)
            .enumerate()
            .map(|(i, mut case)| {
                case.expected = "fallback".into();
                Record {
                    case,
                    baseline: "fallback".into(),
                    decision: Decision {
                        route: if i == 2 { "coding" } else { "fallback" }.into(),
                        reason: "fixture".into(),
                    },
                    latency_ms: None,
                    error: (i == 0).then(|| "http_500".into()),
                    response: None,
                }
            })
            .collect();
        let refs: Vec<_> = records.iter().collect();
        let result = metrics(&refs, false);
        assert_eq!(result["correct"], 1);
        assert_eq!(result["accuracy"], json!(1.0 / 3.0));
        assert_eq!(result["errors"], 1);
        assert_eq!(result["fallbacks"], 1);
        assert_eq!(result["automatic"], 1);
        assert_eq!(result["wrong_automatic"], 1);
        assert_eq!(result["valid_decisions"], 2);
        assert_eq!(
            result["confusion_expected_to_actual"]["fallback"]["__error__"],
            1
        );
        assert_eq!(metrics(&refs, true)["correct"], 3);
        assert_eq!(
            metrics(&[&records[0]], false)["automatic_error_rate"],
            Value::Null
        );
        assert_eq!(metrics(&[], false)["accuracy"], Value::Null);
    }
    #[test]
    fn evaluation_labels_follow_the_selected_rubric() {
        let custom: Rubric =
            serde_json::from_str(include_str!("../eval/rubric.customer-service.json")).unwrap();
        let row = json!({"id":"billing-1","split":"heldout","tag":"fixture", "request":"Explain this invoice", "expected":"billing"}).to_string();
        let cases = cases_for_rubric(&row, &custom).unwrap();
        assert_eq!(cases.len(), 1);
        assert_eq!(
            custom.request(&cases[0])["state"],
            json!({"request":"Explain this invoice"})
        );
        assert!(cases_from_jsonl(&row).is_err());
        assert!(cases_for_rubric(&row.replace("\"billing\"", "\"coding\""), &custom).is_err());
        assert!(cases_for_rubric(&format!("{row}\n{row}"), &custom).is_err());
        assert!(cases_for_rubric("", &custom).is_err());
        let too_many = (0..41)
            .map(|n| row.replace("billing-1", &format!("billing-{n}")))
            .collect::<Vec<_>>()
            .join("\n");
        assert!(cases_for_rubric(&too_many, &custom).is_err());
    }
    #[test]
    fn labels_are_not_sent_and_cases_are_valid() {
        let cases = cases_from_jsonl(include_str!("../eval/cases.jsonl")).unwrap();
        assert_eq!(cases.len(), 24);
        let r = rubric();
        r.validate().unwrap();
        let request = r.request(&cases[0]);
        assert_eq!(request["state"], json!({"request":cases[0].request}));
        assert!(request.get("expected").is_none());
        let duplicate = format!(
            "{}\n{}",
            serde_json::to_string(&cases[0]).unwrap(),
            serde_json::to_string(&cases[0]).unwrap()
        );
        assert!(cases_from_jsonl(&duplicate).is_err());
    }

    #[test]
    fn abstention_does_not_hide_wrong_automatic_routes() {
        let cases = cases_from_jsonl(include_str!("../eval/cases.jsonl")).unwrap();
        let records: Vec<_> = cases
            .into_iter()
            .take(2)
            .enumerate()
            .map(|(i, case)| Record {
                case,
                baseline: "general".into(),
                decision: Decision {
                    route: if i == 0 { "coding" } else { "fallback" }.into(),
                    reason: "test".into(),
                },
                latency_ms: None,
                error: None,
                response: None,
            })
            .collect();
        let refs: Vec<_> = records.iter().collect();
        let m = metrics(&refs, false);
        assert_eq!(m["automatic_error_rate"], 1.0);
        assert_eq!(m["coverage"], 0.5);
        assert_eq!(m["unnecessary_fallbacks"], 1);
        assert!(metrics(&[], false)["accuracy"].is_null());
    }
}
