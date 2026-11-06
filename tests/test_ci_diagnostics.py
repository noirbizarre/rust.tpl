"""Exercise failure evidence collection without needing a broken LLVM runtime."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "template/.github/scripts/collect-ci-diagnostics.py"
SPEC = importlib.util.spec_from_file_location("diagnostics", SCRIPT)
diagnostics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostics)


class FailureDiagnostics(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="coverage evidence ")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.root = self.workspace / "custom target/llvm-cov-target"
        self.root.mkdir(parents=True)
        self.output = self.workspace / "bundle"
        self.output.mkdir()
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"CARGO_LLVM_COV_TARGET_DIR": str(self.root)}).start()
        patch.object(diagnostics, "command", return_value="").start()

    def report(self, *profiles):
        text = "\n".join(
            f"\x1b[33mwarning: {path}: invalid instrumentation profile data (file header is corrupt)\x1b[0m"
            for path in profiles
        )
        (self.output / "report.log").write_text(text, encoding="utf-8")

    def collect(self):
        diagnostics.collect(self.workspace, self.output)
        return json.loads((self.output / "context.json").read_text(encoding="utf-8"))

    def test_corrupt_bytes_and_empty_profiles_survive_collection(self):
        broken = self.root / "broken profile.profraw"
        empty = self.root / "empty.profraw"
        broken.write_bytes(b"\x00\xffbroken\x00")
        empty.touch()
        (self.root / "example-profraw-list").write_text(str(broken), encoding="utf-8")
        self.report(broken, empty)
        self.collect()
        self.assertEqual((self.output / "corrupt-profiles" / broken.name).read_bytes(), broken.read_bytes())
        self.assertEqual((self.output / "corrupt-profiles" / empty.name).read_bytes(), b"")
        self.assertEqual((self.output / "example-profraw-list").read_text(encoding="utf-8"), str(broken))
        inventory = [json.loads(line) for line in (self.output / "profiles.jsonl").read_text().splitlines()]
        self.assertEqual([entry["name"] for entry in inventory], [broken.name, empty.name])
        self.assertEqual(inventory[0]["header_hex"], broken.read_bytes().hex())

    def test_missing_inputs_still_produce_actionable_context(self):
        self.root.rmdir()
        context = self.collect()
        self.assertEqual(context["context"]["coverage_directory"], str(self.root.resolve()))
        self.assertIn("Cargo target directory unavailable", context["collection_notes"][0])
        self.assertEqual((self.output / "profiles.jsonl").read_bytes(), b"")

    def test_warned_paths_cannot_copy_files_outside_the_coverage_root(self):
        outside = self.workspace / "outside.profraw"
        outside.write_bytes(b"private")
        self.report(outside, self.root / "disappeared.profraw")
        context = self.collect()
        self.assertEqual(list((self.output / "corrupt-profiles").iterdir()), [])
        self.assertTrue(any("Rejected profile" in note for note in context["collection_notes"]))
        self.assertTrue(any("disappeared.profraw" in note for note in context["collection_notes"]))

    def test_file_and_byte_limits_are_reported_without_changing_inputs(self):
        profiles = [self.root / f"{number}.profraw" for number in range(3)]
        for path in profiles:
            path.write_bytes(b"broken")
        self.report(*profiles)
        with patch.object(diagnostics, "PROFILE_COUNT", 1), patch.object(diagnostics, "PROFILE_LIMIT", 6):
            context = self.collect()
        self.assertEqual(len(list((self.output / "corrupt-profiles").iterdir())), 1)
        self.assertEqual(sum("payload limit" in note for note in context["collection_notes"]), 2)
        self.assertTrue(all(path.read_bytes() == b"broken" for path in profiles))

    def test_log_tails_and_inventory_are_bounded(self):
        (self.output / "tests.log").write_bytes(b"x" * 200 + b"final error")
        (self.root / "large.profraw").write_bytes(b"bad")
        with patch.object(diagnostics, "LOG_LIMIT", 20), patch.object(diagnostics, "METADATA_LIMIT", 10):
            context = self.collect()
        self.assertTrue((self.output / "tests.log").read_bytes().endswith(b"final error"))
        self.assertEqual((self.output / "tests.log").stat().st_size, 20)
        self.assertLessEqual((self.output / "profiles.jsonl").stat().st_size, 10)
        self.assertTrue(any("inventory truncated" in note for note in context["collection_notes"]))

    def test_warning_parser_keeps_windows_drive_colons_and_spaces(self):
        path = r"D:\a\project name\target\hive-4388.profraw"
        self.assertEqual(diagnostics.warned_profiles(
            f"warning: {path}: invalid instrumentation profile data (file header is corrupt)\r\n"
        ), [path])

    def test_streaming_capture_bounds_logs_and_retains_early_warnings_and_failure(self):
        log = self.output / "report.log"
        profile = self.root / "early warning.profraw"
        profile.write_bytes(b"broken")
        program = (
            "import sys; "
            f"print('warning: ' + {str(profile)!r} + ': invalid instrumentation profile data'); "
            "print('x' * 3000000); sys.exit(42)"
        )
        helper = SCRIPT.with_name("capture-ci-output.sh")
        bash = "bash"
        if os.name == "nt":
            # Native Python can find the WSL launcher before Git Bash on PATH.
            # Locate Bash in the Git installation that provides the CI shell.
            git = Path(shutil.which("git")).resolve()
            bash = str(next(parent / "bin/bash.exe" for parent in git.parents
                            if (parent / "bin/bash.exe").is_file()))
        result = subprocess.run(
            [bash, helper.as_posix(), log.as_posix(), sys.executable, "-c", program],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30,
        )
        self.assertEqual(result.returncode, 42, result.stderr[-4096:].decode("utf-8", errors="replace"))
        self.assertLessEqual(log.stat().st_size, diagnostics.LOG_LIMIT)
        self.assertNotIn(b"warning:", log.read_bytes())
        self.collect()
        self.assertEqual((self.output / "corrupt-profiles" / profile.name).read_bytes(), b"broken")

    def test_valid_metadata_with_stderr_warnings_keeps_the_configured_target(self):
        patch.stopall()
        errors = []
        # Probe the real command boundary rather than stubbing its decoded result.
        result = diagnostics.command([
            sys.executable, "-c",
            'import sys; print(\'{"target_directory": "custom target"}\'); print("warning: config", file=sys.stderr)',
        ], errors, separate_stderr=True)
        self.assertEqual(json.loads(result)["target_directory"], "custom target")
        self.assertTrue(any("warning: config" in note for note in errors))

    def test_nextest_report_location_is_independent_of_the_cargo_target(self):
        junit = self.workspace / "target/nextest/ci/junit.xml"
        junit.parent.mkdir(parents=True)
        junit.write_text("<testsuites/>", encoding="utf-8")
        self.collect()
        self.assertEqual((self.output / "junit.xml").read_text(encoding="utf-8"), "<testsuites/>")

    def test_custom_nextest_store_and_report_are_collected(self):
        config = self.workspace / ".config/nextest.toml"
        config.parent.mkdir()
        config.write_text('[store]\ndir = "test results"\n[profile.ci.junit]\npath = "results.xml"\n', encoding="utf-8")
        junit = self.workspace / "test results/ci/results.xml"
        junit.parent.mkdir(parents=True)
        junit.write_text("<testsuites/>", encoding="utf-8")
        self.collect()
        self.assertTrue((self.output / "results.xml").is_file())

    def test_many_manifests_and_profiles_obey_aggregate_limits(self):
        for number in range(25):
            (self.root / f"{number}-profraw-list").write_bytes(b"x" * 100)
            (self.root / f"{number}.profraw").touch()
        with patch.object(diagnostics, "METADATA_LIMIT", 250), patch.object(diagnostics, "ENTRY_COUNT", 2):
            context = self.collect()
        manifests = list(self.output.glob("*-profraw-list"))
        self.assertLessEqual(sum(path.stat().st_size for path in manifests), 250)
        self.assertTrue(any("enumeration truncated" in note for note in context["collection_notes"]))

    def test_missing_and_hung_tools_are_recorded(self):
        # Bypass setUp's command stub to exercise real subprocess error handling.
        patch.stopall()
        errors = []
        self.assertEqual(diagnostics.command([str(self.workspace / "missing-tool")], errors), "")
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("tool", 10)):
            self.assertEqual(diagnostics.command(["tool"], errors), "")
        self.assertEqual(len(errors), 2)

    def test_cli_produces_evidence_even_without_a_toolchain(self):
        # The actual entry point must survive missing executables on all runner OSes.
        broken = self.root / "cli.profraw"
        broken.write_bytes(b"bad header")
        self.report(broken)
        env = {**os.environ, "PATH": "", "CARGO_LLVM_COV_TARGET_DIR": str(self.root)}
        subprocess.run(
            [sys.executable, str(SCRIPT), "--workspace", str(self.workspace), "--output", str(self.output)],
            env=env, check=True, timeout=30,
        )
        self.assertEqual((self.output / "corrupt-profiles/cli.profraw").read_bytes(), b"bad header")


if __name__ == "__main__":
    unittest.main()
