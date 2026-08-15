<h1 align="center">rust.tpl</h1>

<p align="center"><strong>The base stack for noirbizarre's Rust projects, as a <a href="https://github.com/noirbizarre/git-tpl">git-tpl</a> template</strong></p>

---

```bash
git tpl init https://github.com/noirbizarre/rust.tpl
```

Renders mise, prek, git-cliff, gh-ship, CI and publication into a repository —
new or existing — and keeps them updatable with `git tpl update`.

## What it renders

| | |
|---|---|
| **Toolchain** | `mise.toml` + `rust-toolchain.toml`, every tool pinned by `mise.lock` |
| **Hooks** | `prek.toml`: fmt, clippy, actionlint, typos, commitlint |
| **Tests** | nextest + llvm-cov, `.config/nextest.toml`, Codecov with per-OS flags |
| **CI** | `ci.yaml` (hooks, 3-OS test matrix, `gh ship validate`), optional `msrv.yaml` |
| **Changelog** | `cliff.toml` — Conventional Commits, emoji sections, no `v` tag prefix |
| **Release** | gh-ship: `ship.yaml`, `prepare-release.yaml`, `publish-release.yaml` |
| **Docs** | optional Zensical site + `docs.yaml` deploying to GitHub Pages |
| **Crate** | `Cargo.toml` metadata, `[profile.release]`, and a `thiserror`/`miette` skeleton |

## Questions

Answered at `init`, stored in `.config/git.tpl.toml`, reused on every update.

`crate`, `description`, `owner`, `author`, `copyright_holder`, `copyright_year`,
`keywords`, `categories`, `bin_name`, `msrv`, `msrv_version`, `publish`, `docs`,
`docs_accent`, `targets`.

Two of these deserve a note:

- **`copyright_year`** is a question, not a clock read. Rendering is
  deterministic by design, so the template has no access to the current date —
  and a copyright notice records the year of first publication anyway.
- **`targets`** is a `multi_choice` over `data/targets.toml`, which also carries
  the runner, asset name, `cross` flag and executable extension each target
  needs in the publish matrix.

## What it does not render

Deliberately left to each project: `gh` extension packaging, artwork
(`icons`/`social`) tasks, OS packaging, and architecture-guard hooks.

## Project-specific additions

`mise.toml`, `prek.toml` and `Cargo.toml` end with a
`# --- project-specific ---` marker. Add below it. Git's 3-way merge then keeps
your additions across every `git tpl update`; the template never writes there.

`Cargo.toml`'s `[dependencies]` are seeded once and then abandoned by the
template — Dependabot bumps them weekly in every consumer, and a template that
propagated its own versions would conflict with every one of those PRs.

## Working on the template

```bash
mise run render minimal   # render one answer case into a scratch repo
mise run render full
mise run test             # render both, then build, test, lint and actionlint
mise run check:tasks DIR  # are any task names shadowed by a mise builtin?
```

`--dirty` throughout, so the loop is edit-and-see rather than
edit-commit-and-see.

Both cases run in CI on every pull request. `minimal` is the one that earns its
keep: it is where every conditional takes its other branch.

### The mise shorthand hazard

`mise <task>` is shorthand for `mise run <task>`, and a builtin subcommand of
the same name wins it **silently** — `mise fmt` formats `mise.toml` and says
nothing about the task it shadowed. That is why the rendered tasks are `format`
rather than `fmt`, and `cli` rather than `run`.

mise's own documentation warns that new subcommands can claim a name in any
release, so `mise run check:tasks` asks the installed mise which names are
taken (`mise help <name>` exits 0 only for a builtin or an alias) rather than
comparing against a list written down here that would go stale. It runs against
each rendered project in `mise run test` and in CI.

### The `${{ }}` hazard

git-tpl renders with stock MiniJinja delimiters, so GitHub's `${{ … }}` is
inside the templating language's syntax. Two rules follow, and the
`workflow-jinja-escaping` prek hook enforces the second:

1. **Prefer verbatim workflows.** A file not named `.jinja` is copied
   byte-for-byte. Whole-file conditionals use a path segment that renders empty
   — `{% if msrv %}msrv{% endif %}.yaml` — which is git-tpl's only include
   mechanism. This is why the MSRV job is its own workflow.
2. **A `.jinja` workflow wraps every GitHub expression in `{% raw %}`.**
   Forgetting is silent: `${{ github.ref }}` resolves to `$` and the YAML stays
   valid. Only actionlint on the rendered output notices, which is why CI runs
   it.

The same applies to `cliff.toml`, whose body is Tera.

## License

MIT — see [LICENSE](LICENSE).
