"""Preserve bounded evidence without altering the coverage inputs or exit status."""

import argparse
from itertools import islice
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib


LOG_LIMIT = 2 * 1024 * 1024
METADATA_LIMIT = 1024 * 1024
PROFILE_LIMIT = 50 * 1024 * 1024
PROFILE_COUNT = 20
ENTRY_COUNT = 4096
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
CONTEXT_KEYS = (
    "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "RUNNER_OS",
    "RUNNER_ARCH", "ImageOS", "ImageVersion", "COVERAGE_CLEAN_OUTCOME",
    "COVERAGE_TESTS_OUTCOME", "COVERAGE_REPORT_OUTCOME",
)


def command(args, errors, separate_stderr=False):
    """Use a file so unexpectedly verbose tools cannot exhaust collector memory."""
    try:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as stderr:
            result = subprocess.run(args, stdout=output,
                                    stderr=stderr if separate_stderr else output, timeout=10)
            output.seek(0)
            text = output.read(METADATA_LIMIT + 1)
            if separate_stderr:
                stderr.seek(0)
                warning = stderr.read(4096).decode("utf-8", errors="replace")
                if warning:
                    errors.append(f"{args}: stderr: {warning}")
        if result.returncode or len(text) > METADATA_LIMIT:
            errors.append(f"{args}: exit {result.returncode}; output bytes read {len(text)}")
        return text[:METADATA_LIMIT].decode("utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as error:
        errors.append(f"{args}: {error}")
        return ""


def tail(path, limit):
    # The final warnings are more useful than initial compilation output.
    with path.open("rb") as source:
        source.seek(max(0, path.stat().st_size - limit))
        return source.read(limit)


def warned_profiles(text):
    # Greedy matching retains Windows drive colons and spaces in filenames.
    return re.findall(
        r"warning: (.+?\.profraw): invalid instrumentation profile data",
        ANSI.sub("", text),
    )


def collect(workspace, output):
    workspace, output = workspace.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    class Notes(list):
        # Missing files in a large suite must not grow the manifest indefinitely.
        def append(self, note):
            if len(self) < 100:
                super().append(str(note)[:4096])
            elif len(self) == 100:
                super().append("Further collection notes omitted")

    errors = Notes()
    context = {key: os.environ[key] for key in CONTEXT_KEYS if key in os.environ}
    # Leave useful context even if a later probe is interrupted by the step timeout.
    (output / "context.json").write_text(json.dumps({"context": context, "status": "collecting"}), encoding="utf-8")
    tools = {}
    for name, args in (
        ("rustc", ["rustc", "-vV"]), ("cargo", ["cargo", "--version"]),
        ("llvm-cov", ["cargo", "llvm-cov", "--version"]),
        ("nextest", ["cargo", "nextest", "--version"]),
    ):
        tools[name] = command(args, errors)
    sysroot = command(["rustc", "--print", "sysroot"], errors, separate_stderr=True).strip()
    host = re.search(r"^host: (.+)$", tools["rustc"], re.MULTILINE)
    if sysroot and host:
        executable = "llvm-profdata.exe" if os.name == "nt" else "llvm-profdata"
        profdata = Path(sysroot) / "lib/rustlib" / host[1].strip() / "bin" / executable
        tools["llvm-profdata"] = command([str(profdata), "--version"], errors)

    # Cargo metadata respects .cargo/config.toml as well as CARGO_TARGET_DIR.
    metadata = command(["cargo", "metadata", "--no-deps", "--format-version", "1"], errors,
                       separate_stderr=True)
    try:
        target = Path(json.loads(metadata)["target_directory"])
    except (ValueError, KeyError, TypeError):
        errors.append("Cargo target directory unavailable; using CARGO_TARGET_DIR or target")
        target = Path(os.environ.get("CARGO_TARGET_DIR", workspace / "target"))
    if not target.is_absolute():
        target = workspace / target
    root = Path(os.environ.get("CARGO_LLVM_COV_TARGET_DIR", target / "llvm-cov-target"))
    if not root.is_absolute():
        root = workspace / root
    root = root.resolve()
    context["coverage_directory"] = str(root)

    warnings = []
    for name in ("clean.log", "tests.log", "report.log"):
        path = output / name
        if path.is_file():
            data = tail(path, LOG_LIMIT)
            if path.stat().st_size > LOG_LIMIT:
                errors.append(f"{name}: retained final {LOG_LIMIT} bytes")
            path.write_bytes(data)
            warnings.extend(warned_profiles(data.decode("utf-8", errors="replace")))
        warning_file = output / (name + ".warnings")
        if warning_file.is_file():
            warnings.extend(warned_profiles(tail(warning_file, 65536).decode("utf-8", errors="replace")))

    # Inventory is capped separately from payloads, even for very large suites.
    inventory_size = 0
    with (output / "profiles.jsonl").open("w", encoding="utf-8") as inventory:
        # Cap enumeration before sorting so inventory limits bound memory too.
        paths = list(islice(root.glob("*.profraw"), ENTRY_COUNT + 1))
        if len(paths) > ENTRY_COUNT:
            errors.append(f"Profile enumeration truncated at {ENTRY_COUNT} files")
        for path in sorted(paths[:ENTRY_COUNT]):
            try:
                stat = path.stat()
                with path.open("rb") as source:
                    header = source.read(32).hex()
                entry = json.dumps({"name": path.name, "bytes": stat.st_size,
                                    "mtime_ns": stat.st_mtime_ns, "header_hex": header}) + "\n"
                inventory_size += len(entry.encode("utf-8"))
                if inventory_size > METADATA_LIMIT:
                    errors.append("Profile inventory truncated at metadata limit")
                    break
                inventory.write(entry)
            except OSError as error:
                errors.append(f"{path.name}: {error}")

    samples = output / "corrupt-profiles"
    samples.mkdir(exist_ok=True)
    copied_bytes = copied_count = 0
    for name in sorted(set(warnings)):
        path = Path(name)
        if not path.is_absolute():
            path = workspace / path
        path = path.resolve()
        # Resolve both sides: Windows target may be a Dev Drive junction.
        if path.parent != root or path.suffix != ".profraw":
            errors.append(f"Rejected profile outside coverage directory: {name}")
            continue
        try:
            size = path.stat().st_size
            if copied_count >= PROFILE_COUNT or copied_bytes + size > PROFILE_LIMIT:
                errors.append(f"Omitted profile at payload limit: {path.name} ({size} bytes)")
                continue
            # Bound the read too: a still-running producer may grow the file.
            with path.open("rb") as source:
                data = source.read(PROFILE_LIMIT - copied_bytes + 1)
            if copied_bytes + len(data) > PROFILE_LIMIT:
                errors.append(f"Omitted growing profile: {path.name}")
                continue
            (samples / path.name).write_bytes(data)
            copied_bytes += len(data)
            copied_count += 1
        except OSError as error:
            errors.append(f"{path.name}: {error}")

    # Nextest's store is workspace-relative, independent of Cargo's target dir.
    junit = workspace / "target/nextest/ci/junit.xml"
    config = workspace / ".config/nextest.toml"
    try:
        if config.is_file():
            settings = tomllib.loads(config.read_text(encoding="utf-8"))
            store = settings.get("store", {}).get("dir", "target/nextest")
            report = settings.get("profile", {}).get("ci", {}).get("junit", {}).get("path", "junit.xml")
            junit = workspace / store / "ci" / report
    except (OSError, ValueError, TypeError) as error:
        errors.append(f"Nextest report location: {error}")
    # Aggregate metadata limits prevent many individually small manifests ballooning the bundle.
    metadata_bytes = 0
    manifests = list(islice(root.glob("*-profraw-list"), 21))
    if len(manifests) > 20:
        errors.append("Merge manifest enumeration truncated at 20 files")
    for path in [junit, *sorted(manifests[:20])]:
        try:
            if path.is_file():
                size = path.stat().st_size
                if metadata_bytes + size <= METADATA_LIMIT:
                    with path.open("rb") as source:
                        data = source.read(METADATA_LIMIT - metadata_bytes + 1)
                    if metadata_bytes + len(data) <= METADATA_LIMIT:
                        (output / path.name).write_bytes(data)
                        metadata_bytes += len(data)
                    else:
                        errors.append(f"Omitted growing metadata: {path.name}")
                else:
                    errors.append(f"Omitted oversized metadata: {path.name}")
            elif path == junit:
                errors.append(f"JUnit report not found: {path}")
        except OSError as error:
            errors.append(f"{path.name}: {error}")
    (output / "context.json").write_text(
        json.dumps({"context": context, "tools": tools, "collection_notes": errors}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    arguments.workspace = arguments.workspace.resolve()
    arguments.output = arguments.output.resolve()
    os.chdir(arguments.workspace)
    collect(arguments.workspace, arguments.output)
