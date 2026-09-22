//! FastMetal chat execution and Jev decision constants. No currency conversion.
pub use crate::generation::{
    Adapter, Backend, Config, Effort, Failure, Generation, InputEvidence, InputMode, Mode,
    OutputFormat, Reasoning, Receipt, Request, Route, Usage, server,
};
pub const CHAT_URL: &str = "https://api.fastmetal.ai/v1/chat/completions";
pub const DECISION_URL: &str = "https://api.fastmetal.ai/openrouter/decisions/jev-1-13";
pub const DECISION_MODEL: &str = "typesafe/jev-1.13-20260917";
pub(crate) fn fixed_model(model: &str) -> bool {
    !model.is_empty()
        && model.len() <= 256
        && model
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-._".contains(&b))
        && !matches!(model, "auto" | "random-free")
}
