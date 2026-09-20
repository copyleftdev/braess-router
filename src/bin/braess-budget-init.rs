//! Explicitly create a new durable budget; never overwrite existing state.
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 3 {
        return Err("usage: braess-budget-init PATH MAX_CALLS".into());
    }
    braess_router::durable_budget::DurableBudget::initialize(
        std::path::Path::new(&args[1]),
        args[2].parse()?,
    )?;
    println!("durable budget initialized");
    Ok(())
}
