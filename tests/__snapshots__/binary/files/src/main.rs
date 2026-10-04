//! The bx binary.

#![allow(clippy::result_large_err)]

use std::process::ExitCode;

use clap::Parser;
use miette::MietteHandlerOpts;

mod cli;
mod error;

use cli::{Cli, Command};
use error::Result;

fn main() -> ExitCode {
    let args = Cli::parse();
    let verbose = args.verbose > 0 || std::env::var_os("RUST_BACKTRACE").is_some();
    install_miette_hook(verbose);

    let result = match args.command {
        Command::Run => run(),
    };

    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            // Rendered here rather than returned as `miette::Result`, so the
            // exit code is chosen explicitly instead of inherited from
            // whatever the report wrapper decides.
            eprintln!("{:?}", miette::Report::new(error));
            ExitCode::FAILURE
        }
    }
}

/// Run the thing.
///
/// Private: this crate has no library, so the logic lives beside `main` and
/// nothing outside the binary can call it.
fn run() -> Result<()> {
    Ok(())
}

/// Install miette's diagnostic handler.
///
/// `--verbose` (or `RUST_BACKTRACE`, so a bug report already carries it)
/// prints the full cause chain; otherwise only the primary diagnostic
/// shows, since a source error the user did not ask for is noise more
/// often than it is the answer. Colour is left to miette's own
/// auto-detection so `NO_COLOR`/`TERM=dumb` still produce plain output.
fn install_miette_hook(verbose: bool) {
    let _ = miette::set_hook(Box::new(move |_| {
        let opts = MietteHandlerOpts::new();
        let opts = if verbose {
            opts.with_cause_chain()
        } else {
            opts.without_cause_chain()
        };
        Box::new(opts.build())
    }));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn running_with_nothing_to_do_succeeds() {
        assert!(run().is_ok());
    }
}
