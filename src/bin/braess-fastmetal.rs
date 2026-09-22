//! Companion loopback handler, with explicit create-only state initialization.
use braess_router::fastmetal::{Adapter, Config, Mode, server};
use std::io::Read;
fn run() -> Result<(), &'static str> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if !(args.len() == 2 || args.len() == 3)
        || args[0] != "--config"
        || (args.len() == 3 && args[2] != "--init" && args[2] != "--inspect")
    {
        return Err("usage: braess-fastmetal --config PATH [--init|--inspect]");
    }
    let mut bytes = Vec::new();
    std::fs::File::open(&args[1])
        .map_err(|_| "config_read_failed")?
        .take(65_537)
        .read_to_end(&mut bytes)
        .map_err(|_| "config_read_failed")?;
    if bytes.len() > 65_536 {
        return Err("config_too_large");
    }
    let config: Config = serde_json::from_slice(&bytes).map_err(|_| "invalid_config")?;
    config.validate()?;
    if config.backend != braess_router::generation::Backend::Fastmetal {
        return Err("fastmetal_backend_required");
    }
    if args.get(2).is_some_and(|a| a == "--init") {
        return Adapter::initialize(&config);
    }
    if args.get(2).is_some_and(|a| a == "--inspect") {
        println!("{}", Adapter::inspect(&config)?);
        return Ok(());
    }
    let key = if config.mode == Mode::Live {
        std::env::var("FASTMETAL_API_KEY").ok()
    } else {
        None
    };
    tokio::runtime::Builder::new_multi_thread()
        .worker_threads(4)
        .max_blocking_threads(8)
        .enable_all()
        .build()
        .map_err(|_| "runtime_failed")?
        .block_on(server::serve(config, key))
}
fn main() {
    if let Err(code) = run() {
        eprintln!("{code}");
        std::process::exit(1);
    }
}
