"""Exercise the rendered publisher without contacting GitHub or uploading assets."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


class RollingPublication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.render = tempfile.TemporaryDirectory()
        subprocess.run([
            "git", "tpl", "render", str(ROOT), "--dirty", "--json",
            "--output", cls.render.name, "--answers-from", str(ROOT / "tests/rolling.toml"),
            "--defaults", "--strict-answers",
        ], check=True, capture_output=True)
        path = Path(cls.render.name) / ".github/scripts/publish-main.py"
        spec = importlib.util.spec_from_file_location("publisher", path)
        cls.publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.publisher)

    @classmethod
    def tearDownClass(cls):
        cls.render.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dist = Path(self.temp.name)
        for name in self.publisher.EXPECTED:
            (self.dist / name).write_bytes(b"binary fixture")
        self.calls = []
        self.head = SHA
        self.release = None
        self.tag = None
        self.pages = [[]]
        self.environment = patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "example/agent", "GITHUB_SHA": SHA,
            "GITHUB_SERVER_URL": "https://github.com", "GITHUB_RUN_ID": "123",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def api(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        endpoint = args[-1]
        if endpoint.endswith("git/ref/heads/main"):
            return {"object": {"sha": self.head}}
        if endpoint.endswith("releases/tags/main"):
            return self.release
        if endpoint.endswith("git/ref/tags/main"):
            return self.tag
        if endpoint.endswith("/assets"):
            return self.pages
        if endpoint.endswith("/releases"):
            return {"id": 42}
        return None

    def invoke(self, upload=None):
        with patch.object(self.publisher, "gh", side_effect=self.api), \
             patch.object(self.publisher.subprocess, "run", side_effect=upload) as run:
            self.publisher.publish(self.dist)
            return run

    def test_an_old_rerun_cannot_mutate_the_channel(self):
        self.head = "b" * 40
        run = self.invoke()
        run.assert_not_called()
        self.assertEqual(len(self.calls), 1)

    def test_missing_or_empty_binaries_prevent_all_mutations(self):
        name = next(iter(self.publisher.EXPECTED))
        (self.dist / name).unlink()
        with self.assertRaises(ValueError):
            self.invoke()
        (self.dist / name).touch()
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertTrue(all(not kwargs.get("payload") for _, kwargs in self.calls))

    def test_a_stable_release_named_main_is_never_overwritten(self):
        self.release = {"id": 42, "prerelease": False}
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertTrue(all(not kwargs.get("payload") for _, kwargs in self.calls))

    def test_an_unexpected_artifact_cannot_become_a_release_asset(self):
        (self.dist / "unexpected").write_bytes(b"extra")
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertTrue(all(not kwargs.get("payload") for _, kwargs in self.calls))

    def test_main_advancing_during_validation_prevents_mutation(self):
        original = self.api

        def advancing_api(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[-1].endswith("releases/tags/main"):
                self.head = "b" * 40
            return result

        with patch.object(self, "api", side_effect=advancing_api):
            run = self.invoke()
        run.assert_not_called()
        self.assertTrue(all(not kwargs.get("payload") for _, kwargs in self.calls))

    def test_only_not_found_is_treated_as_a_missing_release(self):
        with patch.object(self.publisher.subprocess, "run", return_value=
                          subprocess.CompletedProcess([], 1, "", "HTTP 403: denied")):
            with self.assertRaises(RuntimeError):
                self.publisher.gh("api", "release", missing_ok=True)
        with patch.object(self.publisher.subprocess, "run", return_value=
                          subprocess.CompletedProcess([], 1, "", "gh: Not Found (HTTP 404)")):
            self.assertIsNone(self.publisher.gh("api", "release", missing_ok=True))

    def test_first_publication_stages_a_draft_and_uploads_checksums_last(self):
        run = self.invoke()
        uploads = [call.args[0][4] for call in run.call_args_list]
        self.assertEqual(Path(uploads[-1]).name, "SHA256SUMS")
        self.assertEqual(Path(uploads[-2]).name, "build.json")
        self.assertEqual(len(uploads), 9)
        manifest = json.loads((self.dist / "build.json").read_text())
        self.assertEqual(manifest["commit"], SHA)
        payloads = [kwargs["payload"] for _, kwargs in self.calls if "payload" in kwargs]
        self.assertTrue(payloads[1]["draft"])
        self.assertFalse(payloads[-1]["draft"])
        self.assertTrue(payloads[-1]["prerelease"])
        self.assertEqual(payloads[-1]["make_latest"], "false")
        subprocess.run(["sha256sum", "--check", "SHA256SUMS"], cwd=self.dist,
                       check=True, capture_output=True)

    def test_upload_failure_never_announces_a_successful_release(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(upload=subprocess.CalledProcessError(1, "upload"))
        self.assertFalse(any(kwargs.get("payload", {}).get("draft") is False
                             for _, kwargs in self.calls))

    def test_reruns_update_existing_tags_and_delete_obsolete_assets(self):
        self.release = {"id": 42, "prerelease": True}
        self.tag = {"object": {"sha": "b" * 40}}
        self.pages = [[{"id": 99, "name": "obsolete-binary"}], [{"id": 100, "name": "build.json"}]]
        self.invoke()
        self.assertTrue(any(args[-1].endswith("assets/99") for args, _ in self.calls))
        self.assertFalse(any(args[-1].endswith("assets/100") for args, _ in self.calls))
        self.assertFalse(any(args[-1].endswith("/releases") for args, _ in self.calls))


class StableTagDiscovery(unittest.TestCase):
    def test_a_rolling_tag_at_head_does_not_replace_the_previous_stable_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.run(["git", *args], cwd=directory, check=True,
                                      capture_output=True, text=True).stdout.strip()
            git("init", "-q")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.com",
                "commit", "--allow-empty", "-m", "feat: initial")
            git("tag", "0.1.0")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.com",
                "commit", "--allow-empty", "-m", "chore: follow-up")
            git("tag", "main")
            workflow = (ROOT / "template/.github/workflows/prepare-release.yaml").read_text()
            line = next(line.strip() for line in workflow.splitlines() if line.strip().startswith("last_tag="))
            result = subprocess.run(["bash", "-c", line + '; printf "%s" "$last_tag"'],
                                    cwd=directory, check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout, "0.1.0")

    def test_a_repository_with_only_a_rolling_tag_has_no_previous_stable_release(self):
        with tempfile.TemporaryDirectory() as directory:
            for args in (("init", "-q"),
                         ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.com",
                          "commit", "--allow-empty", "-m", "feat: initial"),
                         ("tag", "main")):
                subprocess.run(["git", *args], cwd=directory, check=True, capture_output=True)
            workflow = (ROOT / "template/.github/workflows/prepare-release.yaml").read_text()
            line = next(line.strip() for line in workflow.splitlines() if line.strip().startswith("last_tag="))
            result = subprocess.run(["bash", "-c", line + '; printf "%s" "$last_tag"'],
                                    cwd=directory, check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
