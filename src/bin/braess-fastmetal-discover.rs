//! Write a private, create-only snapshot using free FastMetal MCP discovery tools.
#[cfg(unix)]
use std::os::unix::fs::OpenOptionsExt;
use std::{fs::OpenOptions, io::Write, path::PathBuf};
fn run() -> Result<(), &'static str> {
    let mut args = std::env::args().skip(1);
    let mut output = None;
    let mut models = Vec::new();
    let mut mock = None;
    while let Some(arg) = args.next() {
        let value = args.next().ok_or(
            "usage: braess-fastmetal-discover --output PATH [--model ID] [--mock-url URL]",
        )?;
        match arg.as_str() {
            "--output" if output.is_none() => output = Some(PathBuf::from(value)),
            "--model" if models.len() < 8 => models.push(value),
            "--mock-url" if mock.is_none() => mock = Some(value),
            _ => return Err("invalid_discovery_arguments"),
        }
    }
    let path = output.ok_or("discovery_output_required")?;
    let key = if mock.is_none() {
        std::env::var("FASTMETAL_API_KEY").ok()
    } else {
        None
    };
    // Reserve the output path before network traffic. Existing files/symlinks cannot be overwritten.
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    options.mode(0o600);
    let mut file = options
        .open(&path)
        .map_err(|_| "discovery_output_create_failed")?;
    let snapshot = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|_| "runtime_failed")?
        .block_on(braess_router::fastmetal::discovery::discover(
            key,
            mock.as_deref(),
            &models,
        ))?;
    let mut bytes = serde_json::to_vec_pretty(&snapshot).map_err(|_| "discovery_encode_failed")?;
    bytes.push(b'\n');
    file.write_all(&bytes)
        .and_then(|_| file.sync_all())
        .map_err(|_| "discovery_output_write_failed")?;
    println!(
        "Snapshot written: {} models, {} tools; currency JPY",
        snapshot.models.len(),
        snapshot.tools.len()
    );
    Ok(())
}
fn main() {
    if let Err(code) = run() {
        eprintln!("{code}");
        std::process::exit(1);
    }
}
