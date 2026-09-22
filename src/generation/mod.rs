//! Bounded, non-streaming generation for OpenRouter and FastMetal.
//! Generation reservations and receipts are separate from Jev accounting.
mod journal;
mod vision;
pub use vision::InputEvidence;
pub mod server;
use crate::valid_route_label;
use journal::Journal;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    net::{IpAddr, SocketAddr},
    path::PathBuf,
    sync::{Arc, Mutex},
    time::Duration,
};

pub const LIVE_URL: &str = "https://openrouter.ai/api/v1/chat/completions";
/// Explicit wire dialect; omitted defaults preserve existing OpenRouter journals.
#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Backend {
    #[default]
    Openrouter,
    Fastmetal,
}
impl Backend {
    fn is_openrouter(&self) -> bool {
        *self == Self::Openrouter
    }
    pub fn live_url(self) -> &'static str {
        match self {
            Self::Openrouter => LIVE_URL,
            Self::Fastmetal => crate::fastmetal::CHAT_URL,
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "mode", rename_all = "snake_case", deny_unknown_fields)]
pub enum Reasoning {
    Disabled,
    Effort { effort: Effort },
    Budget { max_tokens: u32 },
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Effort {
    None,
    Minimal,
    Low,
    Medium,
    High,
    Xhigh,
    Max,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OutputFormat {
    Text,
    JsonObject,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    Live,
    Mock,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Route {
    pub model: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub provider: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reasoning: Option<Reasoning>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub output_format: Option<OutputFormat>,
    pub max_tokens: u32,
    #[serde(default, skip_serializing_if = "InputMode::is_text")]
    pub input_mode: InputMode,
}
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum InputMode {
    #[default]
    Text,
    VisionReference,
}
impl InputMode {
    fn is_text(&self) -> bool {
        *self == Self::Text
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    #[serde(default, skip_serializing_if = "Backend::is_openrouter")]
    pub backend: Backend,
    pub bind: SocketAddr,
    pub mode: Mode,
    pub url: String,
    pub journal_path: PathBuf,
    pub deadline_ms: u64,
    pub max_request_bytes: usize,
    pub max_response_bytes: usize,
    pub admission_limit: usize,
    pub max_calls: u64,
    pub routes: BTreeMap<String, Route>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub vision_bundles: BTreeMap<String, PathBuf>,
}
fn label(s: &str, max: usize) -> bool {
    !s.is_empty() && s.len() <= max && !s.chars().any(char::is_control)
}
impl Config {
    pub fn validate(&self) -> Result<(), &'static str> {
        let mock_url = reqwest::Url::parse(&self.url).ok().is_some_and(|u| {
            u.scheme() == "http"
                && u.username().is_empty()
                && u.password().is_none()
                && u.query().is_none()
                && u.fragment().is_none()
                && u.port_or_known_default() != Some(0)
                && u.host_str().is_some_and(|h| {
                    h.trim_matches(['[', ']'])
                        .parse::<IpAddr>()
                        .is_ok_and(|a| a.is_loopback())
                })
        });
        if self.url.len() > 4096
            || !self.bind.ip().is_loopback()
            || self.bind.port() == 0
            || !self.journal_path.is_absolute()
            || !(100..=120_000).contains(&self.deadline_ms)
            || !(128..=65_536).contains(&self.max_request_bytes)
            || !(1024..=1_048_576).contains(&self.max_response_bytes)
            || !(1..=64).contains(&self.admission_limit)
            || !(1..=100_000).contains(&self.max_calls)
            || !(1..=32).contains(&self.routes.len())
            || (self.mode == Mode::Live && self.url != self.backend.live_url())
            || (self.mode == Mode::Mock && !mock_url)
        {
            return Err(match self.backend {
                Backend::Openrouter => "invalid_openrouter_config",
                Backend::Fastmetal => "invalid_fastmetal_config",
            });
        }
        for (name, route) in &self.routes {
            if !valid_route_label(name)
                || name == "fallback"
                || !label(&route.model, 256)
                || route.model.chars().any(char::is_whitespace)
                || match self.backend {
                    Backend::Openrouter => {
                        !route.model.contains('/')
                            || route.model.starts_with(['~', '/'])
                            || route.model.starts_with("openrouter/")
                            || !label(&route.provider, 128)
                            || route.provider.chars().any(char::is_whitespace)
                            || route.reasoning.is_some()
                            || route.output_format.is_some()
                    }
                    Backend::Fastmetal => {
                        !crate::fastmetal::fixed_model(&route.model) || !route.provider.is_empty()
                    }
                }
                || matches!(route.reasoning, Some(Reasoning::Budget { max_tokens }) if max_tokens == 0 || max_tokens > route.max_tokens)
                || !(1..=32_768).contains(&route.max_tokens)
            {
                return Err(match self.backend {
                    Backend::Openrouter => "invalid_openrouter_route",
                    Backend::Fastmetal => "invalid_fastmetal_route",
                });
            }
        }
        if self.vision_bundles.len() > 8
            || self.vision_bundles.iter().any(|(hash, path)| {
                !vision::is_hash(hash) || !path.is_absolute() || path.as_os_str().len() > 4096
            })
            || (!self.vision_bundles.is_empty() && self.admission_limit > 4)
            || (self
                .routes
                .values()
                .any(|r| r.input_mode == InputMode::VisionReference)
                && self.vision_bundles.is_empty())
        {
            return Err("invalid_vision_config");
        }
        Ok(())
    }
    fn scope(&self) -> Result<String, &'static str> {
        self.validate()?;
        serde_json::to_string(self).map_err(|_| "invalid_openrouter_config")
    }
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub request: String,
    pub route: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Usage {
    pub prompt_tokens: u64,
    pub completion_tokens: u64,
    pub total_tokens: u64,
    pub cost: Option<serde_json::Number>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    #[serde(default, skip_serializing_if = "Backend::is_openrouter")]
    pub backend: Backend,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reported_cost_jpy: Option<serde_json::Number>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reasoning_tokens: Option<u64>,
    pub attempt_id: u64,
    pub route: String,
    pub requested_model: String,
    pub model: String,
    pub provider: Option<String>,
    pub generation_id: String,
    pub finish_reason: String,
    pub usage: Usage,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub input_evidence: Option<InputEvidence>,
}
impl Receipt {
    fn valid(&self) -> bool {
        (self.backend != Backend::Fastmetal
            || (self.usage.cost.is_none() && self.model == self.requested_model))
            && (self.backend != Backend::Openrouter || self.reported_cost_jpy.is_none())
            && self
                .reported_cost_jpy
                .as_ref()
                .is_none_or(|n| n.as_f64().is_some_and(|v| v.is_finite() && v >= 0.0))
            && self
                .reasoning_tokens
                .is_none_or(|n| n <= self.usage.completion_tokens)
            && label(&self.model, 256)
            && self
                .input_evidence
                .as_ref()
                .is_none_or(InputEvidence::valid)
            && label(&self.generation_id, 256)
            && self.provider.as_ref().is_none_or(|p| label(p, 128))
            && ["stop", "length", "content_filter"].contains(&self.finish_reason.as_str())
            && self
                .usage
                .prompt_tokens
                .checked_add(self.usage.completion_tokens)
                == Some(self.usage.total_tokens)
            && self
                .usage
                .cost
                .as_ref()
                .is_none_or(|c| c.as_f64().is_some_and(|v| v.is_finite() && v >= 0.0))
    }
}
#[derive(Debug, Serialize)]
pub struct Generation {
    pub answer: String,
    pub execution: Receipt,
}
#[derive(Debug)]
pub struct Failure {
    pub status: u16,
    pub code: &'static str,
}
fn fail(status: u16, code: &'static str) -> Failure {
    Failure { status, code }
}
#[derive(Deserialize)]
struct WireResponse {
    id: String,
    model: String,
    provider: Option<String>,
    object: String,
    choices: Vec<Choice>,
    usage: WireUsage,
    error: Option<Value>,
}
#[derive(Deserialize)]
struct WireUsage {
    prompt_tokens: u64,
    completion_tokens: u64,
    total_tokens: u64,
    cost: Option<serde_json::Number>,
}
#[derive(Deserialize)]
struct Choice {
    index: u32,
    finish_reason: String,
    message: Message,
}
#[derive(Deserialize)]
struct Message {
    role: String,
    content: String,
    tool_calls: Option<Vec<Value>>,
}
fn decode(bytes: &[u8], id: u64, route: &str, requested: &str) -> Result<Generation, Failure> {
    let invalid = || fail(502, "openrouter_invalid_response");
    let wire: WireResponse = serde_json::from_slice(bytes).map_err(|_| invalid())?;
    if wire.error.is_some() || wire.object != "chat.completion" || wire.choices.len() != 1 {
        return Err(invalid());
    }
    let choice = wire.choices.into_iter().next().ok_or_else(invalid)?;
    if choice.index != 0
        || choice.message.role != "assistant"
        || choice.message.tool_calls.is_some_and(|t| !t.is_empty())
    {
        return Err(invalid());
    }
    let receipt = Receipt {
        backend: Backend::Openrouter,
        reported_cost_jpy: None,
        reasoning_tokens: None,
        attempt_id: id,
        route: route.into(),
        requested_model: requested.into(),
        model: wire.model,
        provider: wire.provider,
        generation_id: wire.id,
        finish_reason: choice.finish_reason,
        input_evidence: None,
        usage: Usage {
            prompt_tokens: wire.usage.prompt_tokens,
            completion_tokens: wire.usage.completion_tokens,
            total_tokens: wire.usage.total_tokens,
            cost: wire.usage.cost,
        },
    };
    if !receipt.valid() {
        return Err(invalid());
    }
    Ok(Generation {
        answer: choice.message.content,
        execution: receipt,
    })
}

fn decode_fastmetal(
    bytes: &[u8],
    id: u64,
    route: &str,
    requested: &str,
    reported_cost: Option<serde_json::Number>,
) -> Result<Generation, Failure> {
    let mut output = decode(bytes, id, route, requested)?;
    if output.execution.model != requested || output.answer.trim().is_empty() {
        return Err(fail(502, "fastmetal_invalid_response"));
    }
    output.execution.backend = Backend::Fastmetal;
    output.execution.usage.cost = None;
    output.execution.reported_cost_jpy = reported_cost;
    let value: Value =
        serde_json::from_slice(bytes).map_err(|_| fail(502, "fastmetal_invalid_response"))?;
    if let Some(n) = value.pointer("/usage/completion_tokens_details/reasoning_tokens") {
        output.execution.reasoning_tokens = Some(
            n.as_u64()
                .ok_or_else(|| fail(502, "fastmetal_invalid_response"))?,
        );
    }
    if !output.execution.valid() {
        return Err(fail(502, "fastmetal_invalid_response"));
    }
    Ok(output)
}

fn request_body(backend: Backend, route: &Route, content: Value) -> Value {
    let mut body = json!({"model":route.model,"messages":[{"role":"user","content":content}],"stream":false,"max_tokens":route.max_tokens});
    match backend {
        Backend::Openrouter => {
            body["provider"] = json!({"only":[route.provider],"order":[route.provider],"allow_fallbacks":false,"require_parameters":true})
        }
        Backend::Fastmetal => {
            if let Some(reasoning) = &route.reasoning {
                body["reasoning"] = match reasoning {
                    Reasoning::Disabled => json!({"enabled":false}),
                    Reasoning::Effort { effort } => json!({"effort":effort}),
                    Reasoning::Budget { max_tokens } => json!({"max_tokens":max_tokens}),
                };
            }
            if let Some(format) = &route.output_format {
                body["response_format"] = match format {
                    OutputFormat::Text => json!({"type":"text"}),
                    OutputFormat::JsonObject => json!({"type":"json_object"}),
                };
            }
        }
    }
    body
}

pub struct Adapter {
    config: Config,
    client: reqwest::Client,
    key: Option<reqwest::header::HeaderValue>,
    journal: Arc<Mutex<Journal>>,
    vision: vision::Registry,
}
impl Adapter {
    /// Explicit creation only; startup never replaces missing or damaged state.
    pub fn initialize(config: &Config) -> Result<(), &'static str> {
        config.validate()?;
        vision::Registry::load(config)?;
        Journal::initialize(config).map_err(|_| "journal_initialize_failed")
    }
    pub fn new(config: Config, key: Option<String>) -> Result<Arc<Self>, &'static str> {
        config.validate()?;
        let vision = vision::Registry::load(&config)?;
        let key = match (&config.mode, key) {
            (Mode::Live, Some(k)) if !k.trim().is_empty() => {
                let mut value = reqwest::header::HeaderValue::from_str(&format!("Bearer {k}"))
                    .map_err(|_| match config.backend {
                        Backend::Openrouter => "invalid_openrouter_key",
                        Backend::Fastmetal => "invalid_fastmetal_key",
                    })?;
                value.set_sensitive(true);
                Some(value)
            }
            (Mode::Mock, None) => None,
            _ => {
                return Err(match config.backend {
                    Backend::Openrouter => "openrouter_key_mode_mismatch",
                    Backend::Fastmetal => "fastmetal_key_mode_mismatch",
                });
            }
        };
        let client = reqwest::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .retry(reqwest::retry::never())
            .timeout(Duration::from_millis(config.deadline_ms))
            .build()
            .map_err(|_| "openrouter_client_failed")?;
        let journal = Journal::open(&config).map_err(|_| "journal_open_failed")?;
        Ok(Arc::new(Self {
            config,
            client,
            key,
            journal: Arc::new(Mutex::new(journal)),
            vision,
        }))
    }
    pub fn inspect(config: &Config) -> Result<Value, &'static str> {
        let journal = Journal::open(config).map_err(|_| "journal_open_failed")?;
        Ok(journal.status())
    }
    pub async fn status(&self) -> Result<Value, Failure> {
        let journal = self.journal.clone();
        tokio::task::spawn_blocking(move || {
            journal
                .lock()
                .map_err(|_| fail(503, "journal_unavailable"))
                .map(|j| j.status())
        })
        .await
        .map_err(|_| fail(503, "journal_unavailable"))?
    }
    /// One HTTP attempt; failed/aborted dispatch remains charged until proven complete.
    pub async fn execute(&self, input: Request) -> Result<Generation, Failure> {
        self.execute_inner(input).await.map_err(|mut e| {
            if self.config.backend == Backend::Fastmetal {
                e.code = match e.code {
                    "openrouter_invalid_response" => "fastmetal_invalid_response",
                    "openrouter_transport_error" => "fastmetal_transport_error",
                    "openrouter_http_error" => "fastmetal_http_error",
                    "openrouter_response_too_large" => "fastmetal_response_too_large",
                    "openrouter_request_too_large" => "fastmetal_request_too_large",
                    "openrouter_deadline_exceeded" => "fastmetal_deadline_exceeded",
                    other => other,
                };
            }
            e
        })
    }
    async fn execute_inner(&self, input: Request) -> Result<Generation, Failure> {
        if input.request.trim().is_empty() || input.request.len() > self.config.max_request_bytes {
            return Err(fail(400, "invalid_request"));
        }
        let route = self
            .config
            .routes
            .get(&input.route)
            .ok_or_else(|| fail(400, "unknown_route"))?
            .clone();
        let (content, input_evidence) = match route.input_mode {
            InputMode::Text => (Value::String(input.request.clone()), None),
            InputMode::VisionReference => {
                let (content, evidence) = self
                    .vision
                    .content(&input.request)
                    .map_err(|code| fail(400, code))?;
                (content, Some(evidence))
            }
        };
        let body = request_body(self.config.backend, &route, content);
        let body = serde_json::to_vec(&body).map_err(|_| fail(400, "invalid_request"))?;
        if body.len() > vision::MAX_OUTBOUND {
            return Err(fail(400, "openrouter_request_too_large"));
        }
        let journal = self.journal.clone();
        let route_name = input.route.clone();
        let requested = route.model.clone();
        let id = tokio::task::spawn_blocking(move || {
            journal
                .lock()
                .map_err(|_| fail(503, "journal_unavailable"))?
                .begin(route_name, requested)
        })
        .await
        .map_err(|_| fail(503, "journal_unavailable"))??;
        let mut request = self
            .client
            .post(&self.config.url)
            .header(reqwest::header::CONTENT_TYPE, "application/json")
            .body(body);
        if let Some(key) = &self.key {
            request = request.header(reqwest::header::AUTHORIZATION, key.clone());
        }
        let mut result =
            tokio::time::timeout(Duration::from_millis(self.config.deadline_ms), async {
                let mut response = request
                    .send()
                    .await
                    .map_err(|_| fail(502, "openrouter_transport_error"))?;
                if !response.status().is_success() {
                    return Err(fail(502, "openrouter_http_error"));
                }
                if response
                    .content_length()
                    .is_some_and(|n| n > self.config.max_response_bytes as u64)
                {
                    return Err(fail(502, "openrouter_response_too_large"));
                }
                let reported_cost = if self.config.backend == Backend::Fastmetal {
                    response
                        .headers()
                        .get("x-litellm-response-cost")
                        .map(|h| {
                            h.to_str()
                                .ok()
                                .and_then(|v| v.parse::<serde_json::Number>().ok())
                                .filter(|n| n.as_f64().is_some_and(|v| v.is_finite() && v >= 0.0))
                                .ok_or_else(|| fail(502, "fastmetal_invalid_cost"))
                        })
                        .transpose()?
                } else {
                    None
                };
                let mut bytes = Vec::new();
                while let Some(chunk) = response
                    .chunk()
                    .await
                    .map_err(|_| fail(502, "openrouter_transport_error"))?
                {
                    if chunk.len() > self.config.max_response_bytes.saturating_sub(bytes.len()) {
                        return Err(fail(502, "openrouter_response_too_large"));
                    }
                    bytes.extend_from_slice(&chunk);
                }
                let output = match self.config.backend {
                    Backend::Openrouter => decode(&bytes, id, &input.route, &route.model)?,
                    Backend::Fastmetal => {
                        decode_fastmetal(&bytes, id, &input.route, &route.model, reported_cost)?
                    }
                };
                if matches!(route.output_format, Some(OutputFormat::JsonObject))
                    && !serde_json::from_str::<Value>(&output.answer).is_ok_and(|v| v.is_object())
                {
                    return Err(fail(502, "fastmetal_invalid_response"));
                }
                Ok(output)
            })
            .await
            .map_err(|_| fail(504, "openrouter_deadline_exceeded"))??;
        result.execution.input_evidence = input_evidence;
        let receipt = result.execution.clone();
        let journal = self.journal.clone();
        tokio::task::spawn_blocking(move || {
            journal
                .lock()
                .map_err(|_| fail(503, "journal_unavailable"))?
                .complete(receipt)
        })
        .await
        .map_err(|_| fail(503, "journal_unavailable"))??;
        Ok(result)
    }
}

#[cfg(test)]
mod tests;
