//! Explicitly initialize a request journal bound to the router configuration.
use braess_router::{Rubric, durable_requests::DurableRequests, gateway::Config};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 2 {
        return Err("usage: braess-journal-init CONFIG_PATH".into());
    }
    let config: Config = serde_json::from_slice(&std::fs::read(&args[1])?)?;
    let rubric: Rubric = serde_json::from_slice(&std::fs::read(&config.rubric_path)?)?;
    let scope = config.request_journal_scope(&rubric)?;
    let path = config
        .request_journal_path
        .as_ref()
        .ok_or("request_journal_path required")?;
    DurableRequests::initialize(path, &scope)?;
    println!("request journal initialized");
    Ok(())
}
