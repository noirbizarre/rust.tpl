<h1 align="center">rust.tpl</h1>

<p align="center">
  <strong>
    Base stack for Rust projects, as a
    <a href="https://github.com/noirbizarre/git-tpl">git-tpl</a> template
  </strong>
</p>

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
| **Hooks** | `prek.toml`: fmt, actionlint, typos, commitlint |
| **Rust lint** | Clippy through `mise lint` and CI, separate from commit hooks |
| **Tests** | nextest + llvm-cov, `.config/nextest.toml`, Codecov with per-OS flags |
| **CI** | `ci.yaml` (hooks, 3-OS tests, PR-only debug Build matrix, `gh ship validate`, optional MSRV check) |
| **Changelog** | `cliff.toml` — Conventional Commits, emoji sections, no `v` tag prefix |
| **Release** | gh-ship: `ship.yaml`, `prepare-release.yaml`, `publish-release.yaml` |
| **Docs** | optional Zensical site + `docs.yaml` deploying to GitHub Pages |
| **Crate** | `Cargo.toml` metadata, `[profile.release]`, a `thiserror`/`miette` skeleton, optional `cargo-binstall` metadata |
| **Man pages** | optional `build.rs` (clap_mangen + clap_complete) and a `mise man` task |
| **Archive** | optional `<crate>_<tag>_<asset>.tar.gz` per Unix target in the native package layout (`bin/`, `share/doc`, man pages, completions, `lib/systemd/user`), built reproducibly, and a systemd user unit skeleton |
| **Packaging** | optional Homebrew formula / AUR `-bin` PKGBUILD, each with its own release-triggered workflow |

## Project shapes

One answer, `kind`, picks what the project builds, and everything else follows
from it. The default is `library-and-binary`, which is what this template
rendered before `kind` existed.

| `kind` | Renders | Does not render |
|---|---|---|
| `binary` | `src/main.rs`, `src/cli.rs`, `src/error.rs` (private to the binary), CLI dependencies, per-target release assets, binary packaging | `src/lib.rs`, any public library API, an explicit `[lib]` |
| `library` | `src/lib.rs`, `src/error.rs`, a release workflow that only publishes to crates.io | `src/main.rs`, CLI modules and dependencies (`clap`, `console`, `demand`), `bin_name`, `targets`, `man_pages`, `archive`, `service`, `homebrew`, `aur`, `[[bin]]` |
| `library-and-binary` | both, with the binary a thin CLI over the library | |
| `workspace` | a virtual manifest with `[workspace.package]` and `[workspace.dependencies]` | a root `src/`, root targets and anything binary-specific |

Cargo's automatic target discovery is used wherever it is enough: no `[lib]`
is ever rendered, and `[[bin]]` only when `bin_name` differs from `crate`.

## Questions

Answered at `init`, stored in `.config/git.tpl.toml`, reused on every update.

`crate`, `description`, `owner`, `author`, `copyright_holder`, `copyright_year`,
`kind`, `keywords`, `categories`, `msrv`, `msrv_version`, `publish`, `docs`,
`docs_accent`, `mbx`.

Only asked when the shape contains a binary (`binary`, `library-and-binary`):
`bin_name`, `man_pages`, `archive`, `service`, `targets`, `homebrew`,
`homebrew_tap`, `aur`, `rolling_prerelease`.

Projects rendered before `kind` existed carry `workspace = true|false` in
`.config/git.tpl.toml`; `git tpl update` shows a migration note explaining how
to set `kind` instead.

Two of these deserve a note:

- **`copyright_year`** is a question, not a clock read. Rendering is
  deterministic by design, so the template has no access to the current date —
  and a copyright notice records the year of first publication anyway.
- **`targets`** is a `multi_choice` over `data/targets.toml`, which also carries
  the runner, asset name, `cross` flag and executable extension each target
  needs in the PR and publication matrices.

### Mr Boxington (optional)

Answer `mbx = true` to enable [Mr Boxington](https://mr-boxington.jdx.dev/)
through mise's native Rust `mr_boxington` option (mise 2026.9.2+). The default is
off; all project shapes can opt in. Mise installs a separately pinned prebuilt
mbx, retaining the template's stable Rust channel, rustfmt and clippy. Existing
consumers must preserve their own Rust version and tool options when merging.

Mise tasks have mbx built in: use `mise build` or `mise test` without an extra
mbx prefix. `mise exec -- cargo build` and `mise exec -- cargo nextest run`
also work. Activated shells and mise shims also wrap Cargo; installing mbx
alone does not. Explicit toolchain selections and dtolnay's GitHub Actions
rustup default are preserved at runtime while the install request stays stable
and lockable. Mise may install stable and its declared components if missing.

The feature replaces sccache and rust-cache in CI with the Mr Boxington GitHub
Action. Its default target payload includes Cargo outputs and downloads;
main pushes and same-repository PRs can save, with PR entries scoped to the PR.
Cross jobs retain container-produced outputs through that payload. Publication
uses the action's local backend without shared compiler outputs. Existing local
compiler wrappers keep precedence; inspect them before enabling an override.
Remote services and editor setup require separate configuration. Managed target placement and
automatic collection are disabled to preserve outputs and caches. Generated
CONTRIBUTING.md covers cache-hit verification, optional test scheduling and undo.

### Development prereleases

Opt in with `rolling_prerelease = true`. Successful main-push CI builds and publishes
raw release binaries at `releases/download/development/<crate>_development_<asset>`
(with `.exe` for Windows), plus `SHA256SUMS` and the same configured Unix archives/man pages as stable releases.
PRs build every selected
target in debug mode without publication credentials or artifact uploads; superseded PR runs are cancelled.

Main skips CI's PR-only Build matrix. The `prerelease` job calls
`publish-release.yaml` with `ref: github.sha`; publication depends only on its release build.
It has two jobs: an optimized build matrix
that stages final filenames, then one publisher with shared packaging, checksums and uploads.
Both matrices use `matrix.build` objects and short platform labels such as `linux-amd64`.

Every checkout uses the recorded run SHA. gh-ship dispatches on the version tag with
a qualified ref such as `refs/tags/0.1.2`; main CI passes its run SHA for prereleases.
For manual housekeeping, select main in Run workflow and leave ref blank: the run's
recorded SHA is rebuilt even if main advances.

Set the optional repository variable `PRERELEASE_NAME` to change the rolling channel's
tag, release name and filename label; it defaults to `development`. Use a single
Git-valid tag/filename component without spaces, slashes or `#`. The URLs above show the default.

Both workflow entry points accept only `ref`. `.github/ship.yml` opts into gh-ship 0.6's
`release.publish_input: ref`, which dispatches stable releases with a qualified tag ref.
gh-ship owns the stable draft-release lifecycle. Prereleases use `gh release view` or
`gh release create`; both channels upload with `gh release upload "$TAG" dist/* --clobber`.
Both channels use the release environment's GitHub App. The development release
never becomes Latest or publishes to crates.io. Homebrew/AUR automatically run on stable
`released` events, with manual tag-based reruns available to maintainers.

Downloads are mutable and asset replacement is not atomic. Verify checksums,
retry mismatches during updates, and record the source SHA from release notes and the rolling tag.
Pin a stable release for immutable downloads. A binary's package version still
comes from Cargo.toml. After all uploads succeed, a conditional step moves the rolling channel tag
to the published binaries' source SHA.

This draft proposal is being trialled independently in Bee before upstream acceptance.
Bee uses its existing reduced-debug `ci` profile for PR builds; the template uses
Cargo's default debug profile. Main release builds use the same optimized settings.

## What it does not render

Deliberately left to each project: `gh` extension packaging, artwork
(`icons`/`social`) tasks, and architecture-guard hooks.

With `archive` on, the Homebrew formula and the AUR `-bin` package install from
the tarball instead of the raw binary, which is how they get man pages,
completions and the service unit. The raw binaries are published either way
(cargo-binstall and `gh` extensions fetch them by name). Man pages and
completions come from `build.rs` when `man_pages` is on; a project that
generates them another way (a `completions` subcommand, say) adds a step to
`publish-release.yaml` filling `stage/man` and `stage/completions` before the
archive step, and the archive picks them up.

OS packaging is opt-in rather than out of scope: the `homebrew`/`aur`
questions render a formula/PKGBUILD skeleton and the workflow that keeps it
current on every release, but creating and owning the tap repository or the
AUR account itself is still the project's own work.

`aur_package_name` sets the complete AUR package name, defaulting to
`{{ crate }}-bin`. Override it when the crate name is already occupied on AUR;
this leaves the executable and release asset names unchanged. The default
package provides and conflicts with the crate-named source package. Overrides
infer neither relationship: add any required dependencies or file conflicts
below the PKGBUILD's project-specific marker. Changing the answer also changes
the PKGBUILD directory; preserve project-specific additions when integrating
that rename into an existing project.

## Project-specific additions

`mise.toml`, `prek.toml` and `Cargo.toml` end with a
`# --- project-specific ---` marker. Add below it. Git's 3-way merge then keeps
your additions across every `git tpl update`; the template never writes there.

`Cargo.toml`'s `[dependencies]` are seeded once and then abandoned by the
template — Dependabot bumps them weekly in every consumer, and a template that
propagated its own versions would conflict with every one of those PRs.

## Working on the template

```bash
mise lint             # git tpl lint -D warnings, actionlint, typos
mise test             # git tpl test: every case, in full — see below
mise test:write       # re-record every case's snapshot
mise render minimal   # render one case into a scratch directory, for a look
mise render full
mise check:tasks DIR  # are any task names shadowed by a mise builtin? (manual use)
```

Two layers, cheapest first.

`git tpl lint` asks whether the template is a valid *template* — see its own
`-D warnings` rationale in `mise.toml`.

`git tpl test` asks whether each case renders *what it should*, and whether
the result actually works. `[expect]` and `snapshot = true` cover the first;
each case's own `[commands]` covers the second, rendering it into a sandbox
and running `mise test`, `prek -a` and `gh ship validate` against it —
There is one case per project shape (`binary`, `library`, `minimal`/`full` for
library + binary, `workspace`). `workspace` runs `mise build` instead of `mise test` and stubs a member crate
first, since an empty workspace has nothing else to build.

CI (`.github/workflows/ci.yaml`) calls this directly, once: `mise run test`.

### The cases are also the answer files

The `tests/*.toml` cases are read twice: by `git tpl test`,
which uses `[answers]` and `[expect]`, and by `--answers-from`, which reads the
`[answers]` table and ignores the rest. One file, so the runner and the render
tasks cannot drift onto different inputs.

### Updating a snapshot

```bash
mise test:write                  # re-record every case's snapshot
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
case) — which means, left unchecked, `prek run --all-files` would run generated
project hooks against frozen recordings that aren't projects to lint or
rewrite.
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
release, so `mise check:tasks DIR` asks the installed mise which names are
taken (`mise help <name>` exits 0 only for a builtin or an alias) rather than
comparing against a list written down here that would go stale. Manual use,
against a `mise render` output.

### Conditional files

A path segment that renders **empty** skips the entry, and that is git-tpl's
only whole-file include mechanism. Where the `{% endif %}` goes decides whether
it works, and getting it wrong produces a real file rather than an error:

```text
{% if docs %}docs.yaml{% endif %}                 ✅ renders to nothing
{% if docs %}docs{% endif %}.yaml                 ❌ renders to `.yaml`
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
   byte-for-byte, so its `${{ }}` is never at risk. A job that is merely
   optional does not need to be one: `ci.yaml.jinja` carries the MSRV job behind
   `{% if msrv %}` and wraps the rest in `{% raw %}`, which is what keeps it one
   `CI / MSRV` check rather than a workflow of its own.
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
