//! Bounded, process-local semantic router. Configuration is operator-owned.
use crate::{
    Answer, Response, Rubric, Usage, gate,
    ledger_http::{HttpLedgerError, LedgerResponse},
    request_ledger::{LedgerConfig, LedgerError, RequestLedger},
};
use poise_core::{Backend, Policy, Status, policy::LeastLoaded};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    net::{IpAddr, SocketAddr},
    sync::{
        Arc, Mutex,
        atomic::{AtomicU64, AtomicUsize, Ordering},
    },
    time::{Duration, Instant},
};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Mode {
    Mock,
    Live,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub bind: String,
    pub mode: Mode,
    pub jev_url: String,
    pub rubric_path: String,
    pub deadline_ms: u64,
    pub max_request_bytes: usize,
    pub max_response_bytes: usize,
    pub admission_limit: usize,
    pub tracking_limit: usize,
    pub uncertainty_ttl_ms: u64,
    pub max_jev_calls: u64,
    #[serde(default)]
    pub jev_rate_limit: Option<crate::rate_limit::RateConfig>,
    #[serde(default)]
    pub budget_path: Option<std::path::PathBuf>,
    #[serde(default)]
    pub request_journal_path: Option<std::path::PathBuf>,
    pub handlers: BTreeMap<String, Vec<String>>,
}
fn local_url(raw: &str) -> bool {
    let Ok(url) = reqwest::Url::parse(raw) else {
        return false;
    };
    let host = url.host_str().unwrap_or("").trim_matches(['[', ']']);
    url.scheme() == "http"
        && host.parse::<IpAddr>().is_ok_and(|ip| ip.is_loopback())
        && url.username().is_empty()
        && url.password().is_none()
        && url.fragment().is_none()
        && url.query().is_none()
        && url.port_or_known_default().is_some_and(|p| p != 0)
}
impl Config {
    pub fn request_journal_scope(&self, rubric: &Rubric) -> Result<String, String> {
        self.validate()?;
        rubric.validate()?;
        validate_rubric(rubric)?;
        self.validate_catalog(rubric)?;
        let mut scope = json!({"mode":self.mode,"jev_url":self.jev_url,"handlers":self.handlers,
            "rubric":rubric,"admission_limit":self.admission_limit,"tracking_limit":self.tracking_limit,
            "max_jev_calls":self.max_jev_calls,"budget_path":self.budget_path});
        if let Some(rate) = &self.jev_rate_limit {
            scope["jev_rate_limit"] = json!(rate);
        }
        let scope = scope.to_string();
        if scope.len() > 65536 {
            return Err("journal scope too large".into());
        }
        Ok(scope)
    }
    fn validate_catalog(&self, rubric: &Rubric) -> Result<(), String> {
        let catalog = rubric.questions["route"]["criteria"]
            .as_object()
            .ok_or("missing route criteria")?;
        if catalog.len() != self.handlers.len() + 1
            || !catalog.contains_key("fallback")
            || !self
                .handlers
                .keys()
                .all(|label| catalog.contains_key(label))
        {
            return Err(
                "handler catalog must exactly match rubric routes except local fallback".into(),
            );
        }
        Ok(())
    }
    pub fn validate(&self) -> Result<(), String> {
        if let Some(rate) = &self.jev_rate_limit {
            rate.validate()?;
        }
        if !self
            .bind
            .parse::<SocketAddr>()
            .is_ok_and(|addr| addr.ip().is_loopback())
        {
            return Err("bind must be a literal loopback socket address".into());
        }
        if !(1..=60_000).contains(&self.deadline_ms)
            || !(1..=65_536).contains(&self.max_request_bytes)
            || !(1..=1_048_576).contains(&self.max_response_bytes)
            || !(1..=1024).contains(&self.admission_limit)
            || self.tracking_limit < self.admission_limit
            || self.tracking_limit > 65_536
            || self.uncertainty_ttl_ms > 3_600_000
            || self.max_jev_calls == 0
            || self.max_jev_calls > 1_000_000
            || self.rubric_path.is_empty()
        {
            return Err("invalid resource bounds".into());
        }
        if match self.mode {
            Mode::Mock => !local_url(&self.jev_url),
            Mode::Live => self.jev_url != "https://api.typesafe.ai/v1/systemone",
        } {
            return Err("invalid Jev destination for mode".into());
        }
        if self.handlers.is_empty()
            || self.handlers.len() > 32
            || self
                .handlers
                .keys()
                .any(|label| label == "fallback" || !crate::valid_route_label(label))
            || self.handlers.values().map(Vec::len).sum::<usize>() > 48
        {
            return Err(
                "configure 1..32 named routes, at most 48 endpoints; fallback is local".into(),
            );
        }
        if self.request_journal_path.is_some()
            && (self.budget_path.is_none()
                || self.handlers.values().flatten().any(|url| url.len() > 4088))
        {
            return Err("request journal requires durable budget and bounded destinations".into());
        }
        let mut destinations = BTreeSet::new();
        for urls in self.handlers.values() {
            if urls.is_empty()
                || urls.len() > 16
                || urls.iter().any(|url| {
                    !local_url(url)
                        || !destinations.insert(reqwest::Url::parse(url).unwrap().to_string())
                })
            {
                return Err(
                    "handler destinations must be unique literal loopback HTTP URLs".into(),
                );
            }
        }
        Ok(())
    }
}
fn validate_rubric(rubric: &Rubric) -> Result<(), String> {
    let questions = rubric
        .questions
        .as_object()
        .ok_or("invalid rubric questions")?;
    if questions.len() != 2
        || rubric.version.len() > 128
        || rubric.questions.to_string().len() > 32_768
    {
        return Err("invalid rubric bounds".into());
    }
    let route_labels: Vec<&str> = rubric.questions["route"]["criteria"]
        .as_object()
        .ok_or("invalid route criteria")?
        .keys()
        .map(String::as_str)
        .collect();
    for (name, kind, labels) in [
        ("route", "choice", route_labels.as_slice()),
        ("supported", "noul", &["true", "false"][..]),
    ] {
        let question = questions
            .get(name)
            .and_then(Value::as_object)
            .ok_or("missing rubric question")?;
        if question.len() != 3
            || question.get("type").and_then(Value::as_str) != Some(kind)
            || question
                .get("instructions")
                .and_then(Value::as_str)
                .is_none_or(|s| s.trim().is_empty())
        {
            return Err("invalid rubric question contract".into());
        }
        let criteria = question
            .get("criteria")
            .and_then(Value::as_object)
            .ok_or("invalid criteria")?;
        if criteria.len() != labels.len()
            || labels.iter().any(|label| {
                criteria
                    .get(*label)
                    .and_then(Value::as_str)
                    .is_none_or(|s| s.trim().is_empty())
            })
        {
            return Err("invalid rubric criteria".into());
        }
    }
    Ok(())
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GatewayRequest {
    pub request: String,
}
#[derive(Debug, Serialize)]
pub struct GatewayFailure {
    pub status: u16,
    pub code: String,
    pub retry_after_seconds: Option<u64>,
    pub routing_trace: Option<Box<RoutingTrace>>,
}
impl GatewayFailure {
    fn new(status: u16, code: &str) -> Self {
        Self {
            status,
            code: code.into(),
            retry_after_seconds: None,
            routing_trace: None,
        }
    }
}
#[derive(Serialize)]
pub struct GatewayResponse {
    pub route: String,
    pub reason: String,
    pub handler_response: Value,
    pub policy_version: String,
    pub model: String,
    pub latency_ms: f64,
    pub usage: Usage,
    pub handler_index: Option<usize>,
    pub routing_trace: Option<RoutingTrace>,
}

/// Local monotonic offsets from execute entry. A send start is not a remote
/// acknowledgement. Missing boundaries remain unknown, including on timeouts.
#[derive(Debug, Default, Serialize)]
pub struct RoutingTrace {
    pub decision_send_started_ns: Option<u64>,
    pub decision_validated_ns: Option<u64>,
    pub handler_send_started_ns: Option<u64>,
    pub handler_validated_ns: Option<u64>,
    pub finished_ns: u64,
    pub decision: Option<DecisionEvidence>,
}

/// Provider scores and configured thresholds, not calibrated review accuracy.
#[derive(Debug, Serialize)]
pub struct DecisionEvidence {
    pub choice: String,
    pub probabilities: BTreeMap<String, f64>,
    pub confidence: f64,
    pub supported: f64,
    pub min_confidence: f64,
    pub min_probability: f64,
    pub min_supported: f64,
    pub route: String,
    pub reason: String,
}

fn offset_ns(start: Instant) -> u64 {
    u64::try_from(start.elapsed().as_nanos()).unwrap_or(u64::MAX)
}
fn transport_failure(error: HttpLedgerError, code: &str) -> GatewayFailure {
    match error {
        HttpLedgerError::Transport(error) if error.is_timeout() => {
            GatewayFailure::new(504, "deadline_exceeded")
        }
        _ => GatewayFailure::new(502, code),
    }
}
fn admission_failure(error: LedgerError, upstream: &str) -> GatewayFailure {
    let suffix = match error {
        LedgerError::TrackingFull => "tracking_full",
        LedgerError::AdmissionFull => "admission_full",
        _ => "ledger_error",
    };
    GatewayFailure::new(503, &format!("{upstream}_{suffix}"))
}
struct Endpoint {
    url: String,
    ledger: Arc<RequestLedger>,
    awaiting_journal: AtomicUsize,
}
struct SelectionReservation<'a>(&'a AtomicUsize);
impl<'a> SelectionReservation<'a> {
    fn new(counter: &'a AtomicUsize) -> Self {
        counter.fetch_add(1, Ordering::SeqCst);
        Self(counter)
    }
}
impl Drop for SelectionReservation<'_> {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::SeqCst);
    }
}
impl Endpoint {
    fn candidate(
        &self,
        index: usize,
        durable_pending: usize,
        config: &Config,
    ) -> Backend<usize, (), u64> {
        let snapshot = self.ledger.snapshot();
        let charged = snapshot
            .charged()
            .max(durable_pending.saturating_add(self.awaiting_journal.load(Ordering::SeqCst)));
        Backend::new(index).with_load(charged as u64).with_status(
            if charged < config.admission_limit && snapshot.tracked() < config.tracking_limit {
                Status::Ready
            } else {
                Status::Unavailable
            },
        )
    }
}
pub struct Gateway {
    config: Config,
    rubric: Rubric,
    client: reqwest::Client,
    key: Option<String>,
    jev: Arc<RequestLedger>,
    handlers: BTreeMap<String, Vec<Endpoint>>,
    selector: Mutex<LeastLoaded>,
    calls: AtomicU64,
    rate_limit: Option<Arc<crate::rate_limit::RateLimiter>>,
    durable_budget: Option<Arc<crate::durable_budget::DurableBudget>>,
    durable_slots: Arc<tokio::sync::Semaphore>,
    durable_requests: Option<Arc<crate::durable_requests::DurableRequests>>,
    offered: AtomicU64,
    completed: AtomicU64,
    failed: AtomicU64,
    cancelled: AtomicU64,
    fallbacks: AtomicU64,
}
struct Execution<'a> {
    cancelled: &'a AtomicU64,
    finished: bool,
}
impl Drop for Execution<'_> {
    fn drop(&mut self) {
        if !self.finished {
            self.cancelled.fetch_add(1, Ordering::Relaxed);
        }
    }
}
impl Gateway {
    pub fn new(config: Config, rubric: Rubric, key: Option<String>) -> Result<Arc<Self>, String> {
        config.validate()?;
        rubric.validate()?;
        validate_rubric(&rubric)?;
        config.validate_catalog(&rubric)?;
        if config.mode == Mode::Live
            && key.as_ref().is_none_or(|k| {
                k.trim().is_empty()
                    || k.len() > 8192
                    || reqwest::header::HeaderValue::from_str(&format!("Bearer {k}")).is_err()
            })
        {
            return Err("live mode requires a valid API key".into());
        }
        if config.mode == Mode::Mock && key.is_some() {
            return Err("mock mode must not receive credentials".into());
        }
        let ledger = || {
            RequestLedger::new(LedgerConfig {
                admission_limit: config.admission_limit,
                tracking_limit: config.tracking_limit,
                uncertainty_ttl: Duration::from_millis(config.uncertainty_ttl_ms),
            })
            .map_err(|_| "invalid ledger".to_string())
        };
        let jev = ledger()?;
        let mut handlers = BTreeMap::new();
        for (route, urls) in &config.handlers {
            let mut endpoints = Vec::new();
            for url in urls {
                endpoints.push(Endpoint {
                    url: url.clone(),
                    ledger: ledger()?,
                    awaiting_journal: AtomicUsize::new(0),
                });
            }
            handlers.insert(route.clone(), endpoints);
        }
        let client = reqwest::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .retry(reqwest::retry::never())
            .timeout(Duration::from_millis(config.deadline_ms))
            .pool_max_idle_per_host(2)
            .build()
            .map_err(|_| "client initialization failed")?;
        let durable_budget = config
            .budget_path
            .as_ref()
            .map(|path| {
                crate::durable_budget::DurableBudget::open(path, config.max_jev_calls)
                    .map(Arc::new)
                    .map_err(|_| "durable budget initialization failed".to_string())
            })
            .transpose()?;
        let durable_requests = config
            .request_journal_path
            .as_ref()
            .map(|path| {
                let scope = config.request_journal_scope(&rubric)?;
                crate::durable_requests::DurableRequests::open(path, &scope, config.admission_limit)
                    .map(Arc::new)
                    .map_err(|_| "request journal initialization failed".to_string())
            })
            .transpose()?;
        let rate_limit = config
            .jev_rate_limit
            .map(crate::rate_limit::RateLimiter::new)
            .transpose()?;
        Ok(Arc::new(Self {
            rate_limit,
            durable_requests,
            durable_slots: Arc::new(tokio::sync::Semaphore::new(config.admission_limit)),
            durable_budget,
            config,
            rubric,
            client,
            key,
            jev,
            handlers,
            selector: Mutex::new(LeastLoaded::new()),
            calls: AtomicU64::new(0),
            offered: AtomicU64::new(0),
            completed: AtomicU64::new(0),
            failed: AtomicU64::new(0),
            cancelled: AtomicU64::new(0),
            fallbacks: AtomicU64::new(0),
        }))
    }
    fn reserve_call(&self) -> Result<(), GatewayFailure> {
        self.calls
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |n| {
                (n < self.config.max_jev_calls).then_some(n + 1)
            })
            .map(|_| ())
            .map_err(|_| GatewayFailure::new(429, "jev_call_budget_exhausted"))
    }
    async fn reserve_durable_call(&self) -> Result<(), GatewayFailure> {
        if let Some(budget) = &self.durable_budget {
            let permit = self
                .durable_slots
                .clone()
                .try_acquire_owned()
                .map_err(|_| GatewayFailure::new(503, "jev_budget_busy"))?;
            let budget = budget.clone();
            match tokio::task::spawn_blocking(move || {
                let _permit = permit;
                budget.reserve()
            })
            .await
            {
                Ok(Ok(true)) => Ok(()),
                Ok(Ok(false)) => Err(GatewayFailure::new(429, "jev_call_budget_exhausted")),
                _ => Err(GatewayFailure::new(503, "jev_budget_unavailable")),
            }
        } else {
            self.reserve_call()
        }
    }
    fn durable_pending(&self, endpoint: &str) -> usize {
        self.durable_requests
            .as_ref()
            .map_or(0, |j| j.pending(endpoint))
    }
    async fn journal_begin(&self, endpoint: String) -> Result<Option<u64>, GatewayFailure> {
        let Some(journal) = &self.durable_requests else {
            return Ok(None);
        };
        let permit = self
            .durable_slots
            .clone()
            .try_acquire_owned()
            .map_err(|_| GatewayFailure::new(503, "request_journal_busy"))?;
        let journal = journal.clone();
        tokio::task::spawn_blocking(move || {
            let _permit = permit;
            journal.begin(&endpoint)
        })
        .await
        .map_err(|_| GatewayFailure::new(503, "request_journal_unavailable"))?
        .map(Some)
        .map_err(|_| GatewayFailure::new(503, "request_journal_unavailable"))
    }
    async fn journal_complete(&self, id: Option<u64>) -> Result<(), GatewayFailure> {
        let Some(id) = id else {
            return Ok(());
        };
        let journal = self
            .durable_requests
            .as_ref()
            .expect("journal attempt requires journal")
            .clone();
        let permit = self
            .durable_slots
            .clone()
            .try_acquire_owned()
            .map_err(|_| GatewayFailure::new(503, "request_journal_busy"))?;
        tokio::task::spawn_blocking(move || {
            let _permit = permit;
            journal.complete(id)
        })
        .await
        .map_err(|_| GatewayFailure::new(503, "request_journal_unavailable"))?
        .map_err(|_| GatewayFailure::new(503, "request_journal_unavailable"))
    }
    /// Advisory local capacity only: no network probes, reservation or disk I/O.
    /// Every route must have capacity; actual admission remains authoritative.
    pub fn readiness(&self) -> Value {
        let mut reasons = Vec::new();
        let used = self.durable_budget.as_ref().map_or_else(
            || self.calls.load(Ordering::Relaxed),
            |budget| budget.used(),
        );
        if used >= self.config.max_jev_calls {
            reasons.push("jev_call_budget_exhausted");
        }
        if self.durable_budget.as_ref().is_some_and(|b| !b.healthy()) {
            reasons.push("jev_budget_unavailable");
        }
        if let Some(journal) = &self.durable_requests
            && journal.snapshot()["healthy"] != true
        {
            reasons.push("request_journal_unavailable");
        }
        if (self.durable_budget.is_some() || self.durable_requests.is_some())
            && self.durable_slots.available_permits() == 0
        {
            reasons.push("storage_workers_full");
        }
        if let Some(rate) = &self.rate_limit {
            let snapshot = rate.snapshot();
            if snapshot["healthy"] != true {
                reasons.push("jev_rate_unavailable");
            } else if snapshot["remaining"].as_u64().unwrap_or(0) == 0 {
                reasons.push("jev_rate_limited");
            }
        }
        let jev = self.jev.snapshot();
        if jev.charged().max(self.durable_pending("jev")) >= self.config.admission_limit
            || jev.tracked() >= self.config.tracking_limit
        {
            reasons.push("jev_capacity_full");
        }
        let unavailable_routes: Vec<_> = self
            .handlers
            .iter()
            .filter_map(|(label, endpoints)| {
                let available = endpoints.iter().any(|endpoint| {
                    let snapshot = endpoint.ledger.snapshot();
                    let pending = self
                        .durable_pending(&format!("handler:{}", endpoint.url))
                        .saturating_add(endpoint.awaiting_journal.load(Ordering::SeqCst));
                    snapshot.charged().max(pending) < self.config.admission_limit
                        && snapshot.tracked() < self.config.tracking_limit
                });
                (!available).then_some(label)
            })
            .collect();
        if !unavailable_routes.is_empty() {
            reasons.push("handler_capacity_full");
        }
        if self.selector.is_poisoned() {
            reasons.push("selector_unavailable");
        }
        json!({"ready": reasons.is_empty(), "scope": "local_admission",
            "upstream_health": "unchecked", "reasons": reasons,
            "unavailable_routes": unavailable_routes})
    }
    pub fn status(&self) -> Value {
        let handlers: BTreeMap<_, _> = self
            .handlers
            .iter()
            .map(|(route, endpoints)| {
                (
                    route,
                    endpoints
                        .iter()
                        .map(|e| e.ledger.snapshot())
                        .collect::<Vec<_>>(),
                )
            })
            .collect();
        json!({"jev_rate_limit":self.rate_limit.as_ref().map(|r| r.snapshot()),"request_journal":self.durable_requests.as_ref().map(|j| j.snapshot()),"mode":self.config.mode,"offered":self.offered.load(Ordering::Relaxed),"completed":self.completed.load(Ordering::Relaxed),"failed":self.failed.load(Ordering::Relaxed),"cancelled":self.cancelled.load(Ordering::Relaxed),"fallbacks":self.fallbacks.load(Ordering::Relaxed),"budget_durable":self.durable_budget.is_some(),"jev_calls_reserved":self.durable_budget.as_ref().map_or_else(|| self.calls.load(Ordering::Relaxed), |b| b.used()),"max_jev_calls":self.config.max_jev_calls,"jev_ledger":self.jev.snapshot(),"handler_ledgers":handlers})
    }
    pub async fn execute(&self, input: GatewayRequest) -> Result<GatewayResponse, GatewayFailure> {
        let start = Instant::now();
        let mut trace = RoutingTrace::default();
        self.offered.fetch_add(1, Ordering::Relaxed);
        let mut execution = Execution {
            cancelled: &self.cancelled,
            finished: false,
        };
        let mut result = tokio::time::timeout(
            Duration::from_millis(self.config.deadline_ms),
            self.execute_inner(input, start, &mut trace),
        )
        .await
        .unwrap_or_else(|_| Err(GatewayFailure::new(504, "deadline_exceeded")));
        trace.finished_ns = offset_ns(start);
        match &mut result {
            Ok(response) => response.routing_trace = Some(trace),
            Err(failure) => failure.routing_trace = Some(Box::new(trace)),
        }
        execution.finished = true;
        match &result {
            Ok(r) => {
                self.completed.fetch_add(1, Ordering::Relaxed);
                if r.route == "fallback" {
                    self.fallbacks.fetch_add(1, Ordering::Relaxed);
                }
            }
            Err(_) => {
                self.failed.fetch_add(1, Ordering::Relaxed);
            }
        }
        result
    }
    async fn read(&self, response: &mut LedgerResponse) -> Result<Vec<u8>, GatewayFailure> {
        let mut body = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|e| transport_failure(e, "upstream_body_error"))?
        {
            if chunk.len() > self.config.max_response_bytes.saturating_sub(body.len()) {
                return Err(GatewayFailure::new(502, "upstream_response_too_large"));
            }
            body.extend_from_slice(&chunk);
        }
        Ok(body)
    }
    async fn execute_inner(
        &self,
        input: GatewayRequest,
        start: Instant,
        trace: &mut RoutingTrace,
    ) -> Result<GatewayResponse, GatewayFailure> {
        if input.request.trim().is_empty() || input.request.len() > self.config.max_request_bytes {
            return Err(GatewayFailure::new(400, "invalid_request"));
        }
        if self.durable_pending("jev") >= self.config.admission_limit {
            return Err(GatewayFailure::new(503, "jev_durable_admission_full"));
        }
        let attempt = self
            .jev
            .try_admit()
            .map_err(|e| admission_failure(e, "jev"))?;
        let rate_lease = self
            .rate_limit
            .as_ref()
            .map(|rate| rate.try_reserve())
            .transpose()
            .map_err(|error| match error {
                crate::rate_limit::RateError::Limited { retry_after_ms } => {
                    let mut failure = GatewayFailure::new(429, "jev_rate_limited");
                    failure.retry_after_seconds = retry_after_ms.map(|ms| ms.div_ceil(1000).max(1));
                    failure
                }
                crate::rate_limit::RateError::Unavailable => {
                    GatewayFailure::new(503, "jev_rate_unavailable")
                }
            })?;
        self.reserve_durable_call().await?;
        let journal_id = self.journal_begin("jev".into()).await?;
        let mut request=self.client.post(&self.config.jev_url).json(&json!({"model":self.rubric.model,"state":{"request":input.request},"questions":self.rubric.questions}));
        if let Some(key) = &self.key {
            request = request.bearer_auth(key);
        }
        if let Some(lease) = rate_lease {
            lease
                .commit()
                .map_err(|_| GatewayFailure::new(503, "jev_rate_unavailable"))?;
        }
        trace.decision_send_started_ns = Some(offset_ns(start));
        let mut response = LedgerResponse::send(request, attempt)
            .await
            .map_err(|e| transport_failure(e, "jev_transport_error"))?;
        let body = self.read(&mut response).await?;
        let parsed: Response = serde_json::from_slice(&body)
            .map_err(|_| GatewayFailure::new(502, "jev_invalid_response"))?;
        let decision = gate(&parsed, &self.rubric)
            .map_err(|_| GatewayFailure::new(502, "jev_contract_violation"))?;
        response
            .validated()
            .map_err(|_| GatewayFailure::new(500, "ledger_error"))?;
        // gate already checked all types, labels, scores and policy thresholds.
        if let (
            Some(Answer::Choice {
                choice,
                probabilities,
                confidence,
            }),
            Some(Answer::Noul { noul }),
        ) = (parsed.answers.get("route"), parsed.answers.get("supported"))
        {
            trace.decision = Some(DecisionEvidence {
                choice: choice.clone(),
                probabilities: probabilities.clone(),
                confidence: *confidence,
                supported: *noul,
                min_confidence: self.rubric.min_confidence,
                min_probability: self.rubric.min_probability,
                min_supported: self.rubric.min_supported,
                route: decision.route.clone(),
                reason: decision.reason.clone(),
            });
        }
        trace.decision_validated_ns = Some(offset_ns(start));
        self.journal_complete(journal_id).await?;
        let (handler_response, handler_index) = if decision.route == "fallback" {
            (
                json!({"status":"needs_review","message":"The request could not be routed automatically."}),
                None,
            )
        } else {
            let endpoints = self
                .handlers
                .get(&decision.route)
                .ok_or_else(|| GatewayFailure::new(500, "route_not_configured"))?;
            let (index, attempt, pending_journal) = {
                let mut selector = self
                    .selector
                    .lock()
                    .map_err(|_| GatewayFailure::new(500, "selector_error"))?;
                let candidates: Vec<Backend<usize, (), u64>> = endpoints
                    .iter()
                    .enumerate()
                    .map(|(i, e)| {
                        e.candidate(
                            i,
                            self.durable_pending(&format!("handler:{}", e.url)),
                            &self.config,
                        )
                    })
                    .collect();
                let index = selector
                    .pick(&candidates, &())
                    .map_err(|_| {
                        GatewayFailure::new(
                            503,
                            if endpoints.iter().all(|e| {
                                e.ledger.snapshot().tracked() >= self.config.tracking_limit
                            }) {
                                "handler_tracking_full"
                            } else {
                                "handler_admission_full"
                            },
                        )
                    })?
                    .index();
                let attempt = endpoints[index]
                    .ledger
                    .try_admit()
                    .map_err(|e| admission_failure(e, "handler"))?;
                let pending = SelectionReservation::new(&endpoints[index].awaiting_journal);
                (index, attempt, pending)
            };
            let journal_id = self
                .journal_begin(format!("handler:{}", endpoints[index].url))
                .await?;
            drop(pending_journal);
            let request = self
                .client
                .post(&endpoints[index].url)
                .json(&json!({"request":input.request,"route":decision.route}));
            trace.handler_send_started_ns = Some(offset_ns(start));
            let mut response = LedgerResponse::send(request, attempt)
                .await
                .map_err(|e| transport_failure(e, "handler_transport_error"))?;
            let body = self.read(&mut response).await?;
            let value: Value = serde_json::from_slice(&body)
                .map_err(|_| GatewayFailure::new(502, "handler_invalid_response"))?;
            response
                .validated()
                .map_err(|_| GatewayFailure::new(500, "ledger_error"))?;
            trace.handler_validated_ns = Some(offset_ns(start));
            self.journal_complete(journal_id).await?;
            (value, Some(index))
        };
        Ok(GatewayResponse {
            route: decision.route,
            reason: decision.reason,
            handler_response,
            policy_version: self.rubric.version.clone(),
            model: parsed.model,
            usage: parsed.usage,
            handler_index,
            latency_ms: start.elapsed().as_secs_f64() * 1000.0,
            routing_trace: None,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn config() -> Config {
        Config {
            bind: "127.0.0.1:0".into(),
            mode: Mode::Mock,
            jev_url: "http://127.0.0.1:1234/jev".into(),
            rubric_path: "eval/rubric.json".into(),
            deadline_ms: 100,
            max_request_bytes: 8000,
            max_response_bytes: 65536,
            admission_limit: 2,
            tracking_limit: 4,
            uncertainty_ttl_ms: 100,
            max_jev_calls: 4,
            jev_rate_limit: None,
            budget_path: None,
            request_journal_path: None,
            handlers: [("general", 1235), ("coding", 1236), ("reasoning", 1237)]
                .into_iter()
                .map(|(r, p)| (r.into(), vec![format!("http://127.0.0.1:{p}/")]))
                .collect(),
        }
    }
    fn rubric() -> Rubric {
        serde_json::from_str(include_str!("../eval/rubric.json")).unwrap()
    }
    #[test]
    fn recovered_work_and_not_yet_journaled_selection_both_charge_capacity() {
        let config = config();
        let endpoint = Endpoint {
            url: "http://127.0.0.1:1235/".into(),
            ledger: RequestLedger::new(LedgerConfig {
                admission_limit: 2,
                tracking_limit: 4,
                uncertainty_ttl: Duration::ZERO,
            })
            .unwrap(),
            awaiting_journal: AtomicUsize::new(0),
        };
        let attempt = endpoint.ledger.try_admit().unwrap();
        let pending = SelectionReservation::new(&endpoint.awaiting_journal);
        let mut policy = LeastLoaded::new();
        assert!(
            policy
                .pick(&[endpoint.candidate(0, 1, &config)], &())
                .is_err()
        );
        let alternative = Backend::new(1).with_load(1u64).with_status(Status::Ready);
        assert_eq!(
            policy
                .pick(&[endpoint.candidate(0, 1, &config), alternative], &())
                .unwrap()
                .index(),
            1
        );
        drop(pending);
        drop(attempt);
        assert!(
            policy
                .pick(&[endpoint.candidate(0, 1, &config)], &())
                .is_ok()
        );
    }
    #[test]
    fn custom_destinations_require_exact_versioned_rubric_catalog() {
        let mut config = config();
        config.handlers = BTreeMap::from([(
            "billing".into(),
            vec!["http://127.0.0.1:1235/billing".into()],
        )]);
        config.validate().unwrap();
        assert!(config.request_journal_scope(&rubric()).is_err());
        let mut custom = rubric();
        custom.version = "billing-v1".into();
        custom.questions["route"]["criteria"] = json!({"billing":"Payments", "fallback":"Review"});
        config.request_journal_scope(&custom).unwrap();
        config.handlers.insert(
            "fallback".into(),
            vec!["http://127.0.0.1:1235/fallback".into()],
        );
        assert!(config.validate().is_err());
    }
    #[test]
    fn destinations_and_configuration_fail_closed() {
        config().validate().unwrap();
        for url in [
            "http://localhost/x",
            "https://127.0.0.1/x",
            "http://10.0.0.1/x",
            "http://127.0.0.1/x#frag",
            "http://user@127.0.0.1/",
            "http://127.0.0.1/x?key=secret",
            "http://127.0.0.1:0/",
        ] {
            let mut c = config();
            c.jev_url = url.into();
            assert!(c.validate().is_err(), "{url}");
        }
        let mut c = config();
        c.mode = Mode::Live;
        assert!(c.validate().is_err());
        c.jev_url = "https://api.typesafe.ai/v1/systemone".into();
        c.validate().unwrap();
        assert!(Gateway::new(c.clone(), rubric(), None).is_err());
        c.jev_url.push('/');
        assert!(c.validate().is_err());
        for field in 0..5 {
            let mut c = config();
            match field {
                0 => c.max_jev_calls = 0,
                1 => c.tracking_limit = 1,
                2 => c.deadline_ms = 0,
                3 => {
                    c.handlers
                        .insert("fallback".into(), vec!["http://127.0.0.1/".into()]);
                }
                _ => c.bind = "0.0.0.0:9000".into(),
            };
            assert!(c.validate().is_err());
        }
        assert!(
            serde_json::from_value::<GatewayRequest>(
                json!({"request":"hello","destination":"http://evil/"})
            )
            .is_err()
        );
    }
    #[test]
    fn incomplete_or_unversioned_rubrics_are_rejected() {
        let mut r = rubric();
        r.questions.as_object_mut().unwrap().remove("supported");
        assert!(Gateway::new(config(), r, None).is_err());
        let mut r = rubric();
        r.questions["supported"]["type"] = json!("choice");
        assert!(Gateway::new(config(), r, None).is_err());
        assert!(Gateway::new(config(), rubric(), Some("secret".into())).is_err());
    }
    #[test]
    fn readiness_observes_capacity_without_reserving_work() {
        let gateway = Gateway::new(config(), rubric(), None).unwrap();
        assert_eq!(gateway.readiness()["ready"], true);
        assert_eq!(gateway.status()["jev_calls_reserved"], 0);
        let first = gateway.jev.try_admit().unwrap();
        let second = gateway.jev.try_admit().unwrap();
        assert_eq!(gateway.readiness()["ready"], false);
        drop((first, second));
        assert_eq!(gateway.readiness()["ready"], true);
        let endpoint = &gateway.handlers["coding"][0];
        let first = endpoint.ledger.try_admit().unwrap();
        let second = endpoint.ledger.try_admit().unwrap();
        assert_eq!(gateway.readiness()["unavailable_routes"], json!(["coding"]));
        drop((first, second));
        assert_eq!(gateway.readiness()["ready"], true);
        for _ in 0..4 {
            gateway.reserve_call().unwrap();
        }
        assert_eq!(
            gateway.readiness()["reasons"],
            json!(["jev_call_budget_exhausted"])
        );
    }
    #[test]
    fn call_budget_is_atomic_and_finite() {
        let gateway = Gateway::new(config(), rubric(), None).unwrap();
        let threads: Vec<_> = (0..32)
            .map(|_| {
                let g = gateway.clone();
                std::thread::spawn(move || g.reserve_call().is_ok())
            })
            .collect();
        assert_eq!(
            threads
                .into_iter()
                .filter_map(|t| t.join().ok())
                .filter(|accepted| *accepted)
                .count(),
            4
        );
        assert_eq!(gateway.status()["jev_calls_reserved"], 4);
        assert_eq!(
            gateway.reserve_call().unwrap_err().code,
            "jev_call_budget_exhausted"
        );
    }
}
