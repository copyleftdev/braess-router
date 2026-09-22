//! Read-only MCP discovery. Metadata never changes executable route policy.
use reqwest::header::{CONTENT_TYPE, HeaderValue};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    net::IpAddr,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

pub const MCP_URL: &str = "https://mcp.fastmetal.ai/mcp";
const PROTOCOL: &str = "2025-03-26";
const MAX_BYTES: usize = 2 * 1024 * 1024;
const MAX_MODELS: usize = 512;
const MAX_TOOLS: usize = 256;
const MAX_PAGES: usize = 4;
const MAX_SELECTED: usize = 8;
type Result<T> = std::result::Result<T, &'static str>;

#[derive(Debug, Serialize)]
pub struct Snapshot {
    pub schema_version: u32,
    pub source: String,
    pub started_at_unix_ms: u64,
    pub completed_at_unix_ms: u64,
    pub protocol_version: String,
    pub currency: &'static str,
    pub tools: Vec<String>,
    pub models: Vec<Model>,
    pub selected_models: Vec<Model>,
    pub quota: Quota,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct DataPolicy {
    pub trains: Policy,
    pub retains: Policy,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Policy {
    Yes,
    No,
    Unknown,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Model {
    pub id: String,
    #[serde(rename = "type")]
    pub kind: String,
    pub supports_vision: Option<bool>,
    pub input_per_1m_yen: Option<serde_json::Number>,
    pub output_per_1m_yen: Option<serde_json::Number>,
    pub cost_per_image_yen: Option<serde_json::Number>,
    pub data_policy: Option<DataPolicy>,
    #[serde(default)]
    pub auto_routed: bool,
}
impl Model {
    fn validate(&self) -> Result<()> {
        if !label(&self.id, 256)
            || !label(&self.kind, 32)
            || [
                &self.input_per_1m_yen,
                &self.output_per_1m_yen,
                &self.cost_per_image_yen,
            ]
            .into_iter()
            .flatten()
            .any(|n| !nonnegative(n))
        {
            return Err("mcp_invalid_model");
        }
        Ok(())
    }
}
#[derive(Debug, Deserialize, Serialize)]
pub struct Quota {
    pub balance: serde_json::Number,
    pub max_budget: serde_json::Number,
    pub spend: serde_json::Number,
}
fn nonnegative(n: &serde_json::Number) -> bool {
    n.as_f64().is_some_and(|v| v.is_finite() && v >= 0.0)
}
fn label(s: &str, max: usize) -> bool {
    !s.is_empty() && s.len() <= max && !s.chars().any(char::is_control)
}
fn now() -> Result<u64> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .ok()
        .and_then(|d| d.as_millis().try_into().ok())
        .ok_or("clock_unavailable")
}

// There is deliberately no arbitrary tool-call API: this enum admits only free discovery.
#[derive(Clone, Copy)]
enum Tool {
    Models,
    Model,
    Quota,
}
impl Tool {
    fn name(self) -> &'static str {
        match self {
            Self::Models => "list_models",
            Self::Model => "get_model",
            Self::Quota => "quota",
        }
    }
}
struct Client {
    http: reqwest::Client,
    url: String,
    key: Option<HeaderValue>,
    session: Option<HeaderValue>,
    initialized: bool,
    next_id: u64,
}
impl Client {
    fn new(key: Option<String>, mock_url: Option<&str>) -> Result<Self> {
        let url = match mock_url {
            Some(url) => {
                let u = reqwest::Url::parse(url).map_err(|_| "mcp_invalid_mock_url")?;
                if key.is_some()
                    || u.scheme() != "http"
                    || !u.username().is_empty()
                    || u.password().is_some()
                    || u.query().is_some()
                    || u.fragment().is_some()
                    || u.port_or_known_default() == Some(0)
                    || !u.host_str().is_some_and(|h| {
                        h.trim_matches(['[', ']'])
                            .parse::<IpAddr>()
                            .is_ok_and(|ip| ip.is_loopback())
                    })
                {
                    return Err("mcp_invalid_mock_url");
                }
                url.to_owned()
            }
            None => MCP_URL.to_owned(),
        };
        let key = match (mock_url, key) {
            (None, Some(k)) if !k.trim().is_empty() => {
                let mut h =
                    HeaderValue::from_str(&format!("Bearer {k}")).map_err(|_| "mcp_invalid_key")?;
                h.set_sensitive(true);
                Some(h)
            }
            (Some(_), None) => None,
            _ => return Err("mcp_key_required"),
        };
        let http = reqwest::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .retry(reqwest::retry::never())
            .connect_timeout(Duration::from_secs(5))
            .timeout(Duration::from_secs(15))
            .user_agent(concat!("braess-router/", env!("CARGO_PKG_VERSION")))
            .build()
            .map_err(|_| "mcp_client_failed")?;
        Ok(Self {
            http,
            url,
            key,
            session: None,
            initialized: false,
            next_id: 1,
        })
    }
    async fn exchange(&mut self, method: &str, params: Value, notification: bool) -> Result<Value> {
        let id = self.next_id;
        self.next_id += 1;
        let mut body = json!({"jsonrpc":"2.0","method":method,"params":params});
        if !notification {
            body["id"] = json!(id);
        }
        let mut request = self
            .http
            .post(&self.url)
            .header("Accept", "application/json, text/event-stream")
            .json(&body);
        if let Some(key) = &self.key {
            request = request.header("Authorization", key.clone());
        }
        if let Some(session) = &self.session {
            request = request.header("Mcp-Session-Id", session.clone());
        }
        if self.initialized {
            request = request.header("MCP-Protocol-Version", PROTOCOL);
        }
        let mut response = request.send().await.map_err(|_| "mcp_transport_failed")?;
        if notification {
            return if response.status().as_u16() == 202 {
                Ok(Value::Null)
            } else {
                Err("mcp_notification_rejected")
            };
        }
        if response.status().as_u16() != 200 {
            return Err("mcp_http_error");
        }
        if method == "initialize"
            && let Some(session) = response.headers().get("Mcp-Session-Id")
        {
            if session.is_empty()
                || session.len() > 1024
                || !session.as_bytes().iter().all(|b| (0x21..=0x7e).contains(b))
            {
                return Err("mcp_invalid_session");
            }
            let mut session = session.clone();
            session.set_sensitive(true);
            self.session = Some(session);
        }
        let content_type = response
            .headers()
            .get(CONTENT_TYPE)
            .and_then(|h| h.to_str().ok())
            .and_then(|s| s.split(';').next())
            .map(str::trim)
            .ok_or("mcp_invalid_content_type")?;
        let streaming = match content_type {
            "text/event-stream" => true,
            "application/json" => false,
            _ => return Err("mcp_invalid_content_type"),
        };
        if response
            .content_length()
            .is_some_and(|n| n > MAX_BYTES as u64)
        {
            return Err("mcp_response_too_large");
        }
        let mut bytes = Vec::new();
        let mut sse = Sse::default();
        let mut seen = 0usize;
        while let Some(chunk) = response.chunk().await.map_err(|_| "mcp_transport_failed")? {
            if chunk.len() > MAX_BYTES.saturating_sub(seen) {
                return Err("mcp_response_too_large");
            }
            seen += chunk.len();
            if streaming {
                if let Some(result) = sse.feed(&chunk, id)? {
                    return Ok(result);
                }
            } else {
                bytes.extend_from_slice(&chunk);
            }
        }
        if streaming {
            return Err("mcp_incomplete_stream");
        }
        rpc_result(&bytes, id)?.ok_or("mcp_missing_response")
    }
    async fn tool(&mut self, tool: Tool, arguments: Value) -> Result<Value> {
        let result = self
            .exchange(
                "tools/call",
                json!({"name":tool.name(),"arguments":arguments}),
                false,
            )
            .await?;
        tool_data(result)
    }
    async fn snapshot(&mut self, selected: &[String]) -> Result<Snapshot> {
        let started = now()?;
        let init = self.exchange("initialize", json!({"protocolVersion":PROTOCOL,"capabilities":{},"clientInfo":{"name":"braess-router-discovery","version":env!("CARGO_PKG_VERSION")}}), false).await?;
        if init["protocolVersion"] != PROTOCOL || !init["capabilities"]["tools"].is_object() {
            return Err("mcp_unsupported_protocol");
        }
        self.initialized = true;
        self.exchange("notifications/initialized", json!({}), true)
            .await?;
        let mut names = BTreeSet::new();
        let mut cursor = None;
        let mut cursors = BTreeSet::new();
        for page in 0..MAX_PAGES {
            let params = cursor
                .as_ref()
                .map_or_else(|| json!({}), |c| json!({"cursor":c}));
            let result = self.exchange("tools/list", params, false).await?;
            let tools = result["tools"].as_array().ok_or("mcp_invalid_tools")?;
            if tools.len() > MAX_TOOLS.saturating_sub(names.len()) {
                return Err("mcp_too_many_tools");
            }
            for tool in tools {
                let name = tool["name"]
                    .as_str()
                    .filter(|n| label(n, 128))
                    .ok_or("mcp_invalid_tools")?;
                if !names.insert(name.to_owned()) {
                    return Err("mcp_duplicate_tool");
                }
                if [Tool::Models.name(), Tool::Model.name(), Tool::Quota.name()].contains(&name) {
                    validate_schema(tool, name == Tool::Model.name())?;
                }
            }
            cursor = match result.get("nextCursor") {
                None => None,
                Some(Value::String(c)) if label(c, 1024) && cursors.insert(c.clone()) => {
                    Some(c.clone())
                }
                _ => return Err("mcp_invalid_cursor"),
            };
            if cursor.is_none() {
                break;
            }
            if page + 1 == MAX_PAGES {
                return Err("mcp_too_many_pages");
            }
        }
        if [Tool::Models, Tool::Model, Tool::Quota]
            .iter()
            .any(|t| !names.contains(t.name()))
        {
            return Err("mcp_missing_discovery_tool");
        }
        let catalog = self.tool(Tool::Models, json!({})).await?;
        let models = models(catalog)?;
        let mut details = Vec::new();
        for id in selected {
            if !models.iter().any(|m| &m.id == id) {
                return Err("mcp_selected_model_unavailable");
            }
            let mut value = self.tool(Tool::Model, json!({"model":id})).await?;
            if value["model"].as_str() != Some(id) {
                return Err("mcp_model_mismatch");
            }
            value["id"] = json!(id);
            value["type"] = json!(match value["is_image"].as_bool() {
                Some(true) => "image",
                Some(false) => "text",
                None => return Err("mcp_invalid_model"),
            });
            let model: Model = serde_json::from_value(value).map_err(|_| "mcp_invalid_model")?;
            model.validate()?;
            details.push(model);
        }
        // Deserialize only these numeric fields. Never serialize the raw account response.
        let quota: Quota = serde_json::from_value(self.tool(Tool::Quota, json!({})).await?)
            .map_err(|_| "mcp_invalid_quota")?;
        if !nonnegative(&quota.max_budget)
            || !nonnegative(&quota.spend)
            || !quota.balance.as_f64().is_some_and(f64::is_finite)
        {
            return Err("mcp_invalid_quota");
        }
        Ok(Snapshot {
            schema_version: 1,
            source: self.url.clone(),
            started_at_unix_ms: started,
            completed_at_unix_ms: now()?,
            protocol_version: PROTOCOL.into(),
            currency: "JPY",
            tools: names.into_iter().collect(),
            models,
            selected_models: details,
            quota,
        })
    }
}
/// Capture a bounded observation using only the documented free discovery tools.
/// A mock endpoint must be a literal loopback HTTP URL and cannot receive a key.
pub async fn discover(
    key: Option<String>,
    mock_url: Option<&str>,
    selected: &[String],
) -> Result<Snapshot> {
    if selected.len() > MAX_SELECTED
        || selected.iter().any(|s| !super::fixed_model(s))
        || selected.iter().collect::<BTreeSet<_>>().len() != selected.len()
    {
        return Err("mcp_invalid_selection");
    }
    let mut client = Client::new(key, mock_url)?;
    tokio::time::timeout(Duration::from_secs(60), client.snapshot(selected))
        .await
        .map_err(|_| "mcp_deadline_exceeded")?
}
fn models(value: Value) -> Result<Vec<Model>> {
    let array = value["models"].as_array().ok_or("mcp_invalid_catalog")?;
    if array.is_empty()
        || array.len() > MAX_MODELS
        || value["count"].as_u64() != Some(array.len() as u64)
    {
        return Err("mcp_invalid_catalog");
    }
    let mut models: Vec<Model> =
        serde_json::from_value(value["models"].clone()).map_err(|_| "mcp_invalid_catalog")?;
    let mut ids = BTreeSet::new();
    for model in &models {
        model.validate()?;
        if !ids.insert(&model.id) {
            return Err("mcp_duplicate_model");
        }
    }
    models.sort_by(|a, b| a.id.cmp(&b.id));
    Ok(models)
}
fn validate_schema(tool: &Value, model: bool) -> Result<()> {
    let schema = &tool["inputSchema"];
    if schema["type"] != "object" {
        return Err("mcp_incompatible_tool_schema");
    }
    if let Some(required) = schema.get("required") {
        let required = required.as_array().ok_or("mcp_incompatible_tool_schema")?;
        if required.iter().any(|v| !model || v != "model") {
            return Err("mcp_incompatible_tool_schema");
        }
    }
    if model && schema["properties"]["model"]["type"] != "string" {
        return Err("mcp_incompatible_tool_schema");
    }
    Ok(())
}
fn tool_data(result: Value) -> Result<Value> {
    if result.get("isError").is_some_and(|v| v != false) {
        return Err("mcp_tool_error");
    }
    if let Some(value) = result.get("structuredContent") {
        return if value.is_object() {
            Ok(value.clone())
        } else {
            Err("mcp_invalid_tool_result")
        };
    }
    let content = result["content"]
        .as_array()
        .ok_or("mcp_invalid_tool_result")?;
    if content.len() != 1 || content[0]["type"] != "text" {
        return Err("mcp_invalid_tool_result");
    }
    let value: Value = serde_json::from_str(
        content[0]["text"]
            .as_str()
            .ok_or("mcp_invalid_tool_result")?,
    )
    .map_err(|_| "mcp_invalid_tool_result")?;
    if !value.is_object() {
        return Err("mcp_invalid_tool_result");
    }
    Ok(value)
}
fn rpc_result(bytes: &[u8], id: u64) -> Result<Option<Value>> {
    let value: Value = serde_json::from_slice(bytes).map_err(|_| "mcp_invalid_json")?;
    if value["jsonrpc"] != "2.0" {
        return Err("mcp_invalid_envelope");
    }
    if value.get("id").is_none()
        && value["method"].is_string()
        && value.get("result").is_none()
        && value.get("error").is_none()
    {
        return Ok(None);
    }
    if value["id"].as_u64() != Some(id) || value.get("method").is_some() {
        return Err("mcp_response_id_mismatch");
    }
    if value.get("error").is_some() {
        return Err("mcp_rpc_error");
    }
    value
        .get("result")
        .filter(|v| v.is_object())
        .cloned()
        .map(Some)
        .ok_or("mcp_invalid_result")
}
#[derive(Default)]
struct Sse {
    line: Vec<u8>,
    data: Vec<u8>,
    after_cr: bool,
    events: usize,
}
impl Sse {
    fn feed(&mut self, bytes: &[u8], id: u64) -> Result<Option<Value>> {
        for &b in bytes {
            if self.after_cr && b == b'\n' {
                self.after_cr = false;
                continue;
            }
            self.after_cr = b == b'\r';
            if b == b'\r' || b == b'\n' {
                if self.line.is_empty() {
                    if !self.data.is_empty() {
                        self.events += 1;
                        if self.events > 128 {
                            return Err("mcp_too_many_events");
                        }
                        let result = rpc_result(&self.data, id)?;
                        self.data.clear();
                        if result.is_some() {
                            return Ok(result);
                        }
                    }
                } else if self.line == b"data" || self.line.starts_with(b"data:") {
                    let value = self.line.get(5..).unwrap_or_default();
                    let value = value.strip_prefix(b" ").unwrap_or(value);
                    if !self.data.is_empty() {
                        self.data.push(b'\n');
                    }
                    self.data.extend_from_slice(value);
                }
                self.line.clear();
            } else {
                self.line.push(b);
            }
        }
        Ok(None)
    }
}

#[cfg(test)]
mod tests;
