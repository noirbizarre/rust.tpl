# AGENTS.md

Notes for anyone — human or otherwise — changing this repository.

## What this project is

Cargo.toml as a virtual manifest

<!-- Replace this with the one paragraph that, if someone read only it, would -->
<!-- stop them proposing the wrong thing. Then list the invariants below.     -->

## Non-negotiable invariants

Each of these should be enforced by a hook or a test. An invariant nothing
checks is a comment, and it will be violated.

<!-- 1. **...** — enforced by `tests/....rs`. -->

## Layout

A Cargo workspace: `Cargo.toml` at the root is a virtual manifest — no code of
its own — and each member crate lives under its own directory with its own
`Cargo.toml` and `src/`.

## Style

**Every non-obvious line carries a comment saying why.** Not what — the code
says what. Ideally naming the failure it prevents. A comment that restates the
code is worse than none.

**Errors are typed and actionable.** `thiserror` for the library, `miette` at
the binary edge. A diagnostic must carry the two things the user does not
already know: what specifically failed, and what to do about it. Diagnostic
codes are `workspace_example::<module>::<kind>`, and a code is a public identifier
users grep for — renaming one is a breaking change.

**Test names are sentences.** `an_unchanged_input_produces_no_output`, not
`test_run_2`. The name should say what would be broken if it failed.

## Commits

Conventional Commits, enforced by commitlint on `commit-msg`. The type becomes a
changelog heading, so choose it as if someone will read it in release notes —
because they will.

## Releases

Driven by gh-ship. Never bump a version or push a tag by hand: `cliff.toml`
derives the version from the commit history, `prepare-release` applies it, and
`.github/ship.yml` is the contract between them. See CONTRIBUTING.md.

## Before you push

Choose checks based on the files changed and the risk. Run relevant tasks
individually rather than launching every check in parallel by default.

- **Rust code:** run `mise run lint` (Clippy) and the relevant tests through
  `mise run test`, which accepts nextest selectors. Target affected packages
  and tests instead of running the whole suite by default. For example,
  replacing the placeholders with the affected package and test name:

  ```sh
  mise run test -- -p <package> -E 'test(<test_name>)'
  ```

- **Documentation, workflows or tooling:** run the relevant checks, such as
  `mise run lint:md`, `mise run spell` or `mise run lint:actions`.
  Documentation-only changes do not require Rust lint or tests.

Broaden validation when the change warrants it. `mise run ci` is available as
an optional comprehensive check, not a prerequisite for committing, pushing or
opening a PR.

If a local check is unavailable or prohibitively expensive, proceed with the
commit or PR and report which checks ran, which were skipped and why in the
handoff or PR description. CI provides full validation.

## This repository is generated from a template

The toolchain, hooks, CI and release workflows come from
[rust.tpl](https://github.com/noirbizarre/rust.tpl) and are updated with
`git tpl update`. Files carrying template-owned content end with a
`# --- project-specific ---` marker: add below it, never above.

Changing template-owned content here fixes it in one repository. Changing it in
the template fixes it in all of them — prefer that.
