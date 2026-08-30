<h1 align="center">rust.tpl</h1>

<p align="center"><strong>Base stack for Rust projects, as a <a href="https://github.com/noirbizarre/git-tpl">git-tpl</a> template</strong></p>

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
mise run lint             # git tpl lint -D warnings, actionlint, typos
mise run test             # git tpl test: every case, in full — see below
mise run test:write       # re-record every case's snapshot
mise run render minimal   # render one case into a scratch directory, for a look
mise run render full
mise run check:tasks DIR  # are any task names shadowed by a mise builtin? (manual use)
```

Two layers, cheapest first.

`git tpl lint` asks whether the template is a valid *template* — see its own
`-D warnings` rationale in `mise.toml`.

`git tpl test` asks whether each case renders *what it should*, and whether
the result actually works. `[expect]` and `snapshot = true` cover the first;
each case's own `[commands]` covers the second, rendering it into a sandbox
and running `mise test`, `prek -a` and `gh ship validate` against it —
`workspace` runs `mise build` instead of `mise test` and stubs a member crate
first, since an empty workspace has nothing else to build.

CI (`.github/workflows/ci.yaml`) calls this directly, once: `mise run test`.

### The cases are also the answer files

`tests/minimal.toml` and `tests/full.toml` are read twice: by `git tpl test`,
which uses `[answers]` and `[expect]`, and by `--answers-from`, which reads the
`[answers]` table and ignores the rest. One file, so the runner and the render
tasks cannot drift onto different inputs.

### Updating a snapshot

```bash
mise run test:write              # re-record every case's snapshot
git diff tests/__snapshots__      # review it — a generated project's own diff
```

`--write` never blesses a broken case: `[expect]` still runs and still fails.
Review the diff, then commit it alongside the template change that caused it.

Snapshots were deliberately not committed here before git-tpl 0.9.0: this
template renders a `mise.toml` `.gitignore` negation that used to break
snapshot read-back — see
[git-tpl#51](https://github.com/noirbizarre/git-tpl/issues/51), fixed in 0.9.0.

### Snapshots and prek's workspace mode

A recorded snapshot is a full rendered project, so it carries its own
`prek.toml`. prek's workspace mode auto-discovers *any* `prek.toml` in the
tree and runs it as an independent nested project (`prek list` shows one per
case) — which means, left unchecked, `prek run --all-files` would compile the
recorded `src/*.rs` with a real `cargo clippy`, using this repository's own
toolchain, against a frozen recording that isn't a project to lint.
`.prekignore` at the repository root stops that, and also keeps these files
out of this repository's own hooks — no per-hook `exclude` needed. See
[prek's workspace mode docs](https://prek.j178.dev/workspace/) if a hook ever
starts running against `tests/__snapshots__/` again.

### The mise shorthand hazard

`mise <task>` is shorthand for `mise run <task>`, and a builtin subcommand of
the same name wins it **silently** — `mise fmt` formats `mise.toml` and says
nothing about the task it shadowed. That is why the rendered tasks are `format`
rather than `fmt`, and `cli` rather than `run`.

mise's own documentation warns that new subcommands can claim a name in any
release, so `mise run check:tasks DIR` asks the installed mise which names are
taken (`mise help <name>` exits 0 only for a builtin or an alias) rather than
comparing against a list written down here that would go stale. Manual use,
against a `mise run render` output.

### Conditional files

A path segment that renders **empty** skips the entry, and that is git-tpl's
only whole-file include mechanism. Where the `{% endif %}` goes decides whether
it works, and getting it wrong produces a real file rather than an error:

```
{% if msrv %}msrv.yaml{% endif %}                 ✅ renders to nothing
{% if msrv %}msrv{% endif %}.yaml                 ❌ renders to `.yaml`
{% if docs %}zensical.toml{% endif %}.jinja       ✅ renders to nothing
```

The third looks like the second and is correct, because the `.jinja` suffix is
stripped from the path *before* the segments are rendered — so for a template
file the suffix is already gone by the time the conditional collapses, and for a
verbatim file it is not. Both forms are in `template/`.

`git tpl lint` reports the middle one as `tpl::lint::degenerate_path` and knows
not to flag the third. Before it existed, one gated file produced `.yaml` in
silence; two produced a collision that named them both, which is the only reason
it was ever caught.

### The `${{ }}` hazard

git-tpl renders with stock MiniJinja delimiters, so GitHub's `${{ … }}` is
inside the templating language's syntax. Two rules follow:

1. **Prefer verbatim workflows.** A file not named `.jinja` is copied
   byte-for-byte, so its `${{ }}` is never at risk. This is why the MSRV job is
   its own workflow rather than a job inside `ci.yaml`.
2. **A `.jinja` workflow wraps every GitHub expression in `{% raw %}`,** or
   escapes it as `${{ '{{' }} … {{ '}}' }}`. Forgetting is silent:
   `${{ github.ref }}` resolves to `$` and the YAML stays valid.

`git tpl lint` enforces the second as `tpl::lint::foreign_expression`, checking
every occurrence rather than merely that a raw block was opened somewhere, and
recognising the escape idiom. It replaced a hand-written prek hook that did
neither, missed `cliff.toml.jinja` — also Tera-bodied — entirely, and once
shipped inert.

## License

MIT — see [LICENSE](LICENSE).
