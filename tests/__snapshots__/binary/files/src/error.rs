//! The error type, and the diagnostics it renders to.
//!
//! `thiserror` defines them, `miette` renders them. A diagnostic must carry the
//! two things the user does not already know: what specifically failed, and
//! what to do about it.

// Private to the binary: nothing outside this crate can name `Error`, so the
// placeholder variant below is never constructed until the project grows a real
// failure path, and `-D warnings` would otherwise reject it. Delete this once
// the variants are used.
#![allow(dead_code)]

use miette::Diagnostic;
use thiserror::Error;

/// The crate's result type.
pub(crate) type Result<T> = std::result::Result<T, Error>;

/// Everything that can go wrong.
///
/// Diagnostic codes are `binary_example::<module>::<kind>`. A code is a public
/// identifier users grep for, so renaming one is a breaking change.
#[derive(Debug, Error, Diagnostic)]
#[non_exhaustive]
pub(crate) enum Error {
    /// Reading or writing a file failed.
    #[error("failed to access `{path}`")]
    #[diagnostic(code(binary_example::error::io))]
    Io {
        /// The path that could not be accessed.
        path: String,
        /// Why.
        #[source]
        source: std::io::Error,
    },
}
