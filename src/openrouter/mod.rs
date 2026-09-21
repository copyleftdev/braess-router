//! Text-only, non-streaming OpenRouter execution. Provider policy is explicit;
//! generation reservations and receipts are separate from Jev accounting.
mod journal;
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
    pub provider: String,
    pub max_tokens: u32,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
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
            || (self.mode == Mode::Live && self.url != LIVE_URL)
            || (self.mode == Mode::Mock && !mock_url)
        {
            return Err("invalid_openrouter_config");
        }
        for (name, route) in &self.routes {
            if !valid_route_label(name)
                || name == "fallback"
                || !label(&route.model, 256)
                || !route.model.contains('/')
                || route.model.starts_with(['~', '/'])
                || route.model.starts_with("openrouter/")
                || route.model.chars().any(char::is_whitespace)
                || !label(&route.provider, 128)
                || route.provider.chars().any(char::is_whitespace)
                || !(1..=32_768).contains(&route.max_tokens)
            {
                return Err("invalid_openrouter_route");
            }
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
    pub attempt_id: u64,
    pub route: String,
    pub requested_model: String,
    pub model: String,
    pub provider: Option<String>,
    pub generation_id: String,
    pub finish_reason: String,
    pub usage: Usage,
}
impl Receipt {
    fn valid(&self) -> bool {
        label(&self.model, 256)
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
        attempt_id: id,
        route: route.into(),
        requested_model: requested.into(),
        model: wire.model,
        provider: wire.provider,
        generation_id: wire.id,
        finish_reason: choice.finish_reason,
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

pub struct Adapter {
    config: Config,
    client: reqwest::Client,
    key: Option<reqwest::header::HeaderValue>,
    journal: Arc<Mutex<Journal>>,
}
impl Adapter {
    /// Explicit creation only; startup never replaces missing or damaged state.
    pub fn initialize(config: &Config) -> Result<(), &'static str> {
        Journal::initialize(config).map_err(|_| "journal_initialize_failed")
    }
    pub fn new(config: Config, key: Option<String>) -> Result<Arc<Self>, &'static str> {
        config.validate()?;
        let key = match (&config.mode, key) {
            (Mode::Live, Some(k)) if !k.trim().is_empty() => {
                let mut value = reqwest::header::HeaderValue::from_str(&format!("Bearer {k}"))
                    .map_err(|_| "invalid_openrouter_key")?;
                value.set_sensitive(true);
                Some(value)
            }
            (Mode::Mock, None) => None,
            _ => return Err("openrouter_key_mode_mismatch"),
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
        if input.request.trim().is_empty() || input.request.len() > self.config.max_request_bytes {
            return Err(fail(400, "invalid_request"));
        }
        let route = self
            .config
            .routes
            .get(&input.route)
            .ok_or_else(|| fail(400, "unknown_route"))?
            .clone();
        let body = json!({"model":route.model,"messages":[{"role":"user","content":input.request}],"stream":false,"max_tokens":route.max_tokens,
            "provider":{"only":[route.provider],"order":[route.provider],"allow_fallbacks":false,"require_parameters":true}});
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
        let mut request = self.client.post(&self.config.url).json(&body);
        if let Some(key) = &self.key {
            request = request.header(reqwest::header::AUTHORIZATION, key.clone());
        }
        let result = tokio::time::timeout(Duration::from_millis(self.config.deadline_ms), async {
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
            decode(&bytes, id, &input.route, &route.model)
        })
        .await
        .map_err(|_| fail(504, "openrouter_deadline_exceeded"))??;
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
