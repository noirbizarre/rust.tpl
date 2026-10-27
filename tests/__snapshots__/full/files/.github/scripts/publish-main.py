"""Update the rolling channel only from complete, current main CI artifacts."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


EXPECTED = {
    "full-example_main_linux-amd64",
    "full-example_main_linux-arm64",
    "full-example_main_linux-amd64-musl",
    "full-example_main_linux-arm64-musl",
    "full-example_main_darwin-amd64",
    "full-example_main_darwin-arm64",
    "full-example_main_windows-amd64.exe",
    "full-example_main_windows-arm64.exe",
    "full-example_main_freebsd-amd64",
}


def gh(*args, payload=None, missing_ok=False):
    """Keep all GitHub operations checked; only an explicit 404 means absence."""
    command = ["gh", *args]
    if payload is not None:
        command += ["--input", "-"]
    result = subprocess.run(
        command, input=json.dumps(payload) if payload is not None else None,
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        if missing_ok and "(HTTP 404)" in result.stderr:
            return None
        raise RuntimeError(f"GitHub command failed: {result.stderr.strip()}")
    return json.loads(result.stdout) if result.stdout.strip() else None


def publish(dist=Path("dist")):
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["GITHUB_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("GITHUB_SHA must identify the exact built commit")
    api = f"repos/{repo}"
    # A rerun of an old commit must never roll the channel backwards.
    head = gh("api", f"{api}/git/ref/heads/main")["object"]["sha"]
    if head != sha:
        print("Main advanced; skipping this stale build.")
        return

    # Reject extra files too: an unexpected artifact must not become a release asset.
    actual = {path.name for path in dist.iterdir()}
    if actual != EXPECTED or any(not (dist / name).is_file() for name in EXPECTED):
        raise ValueError(f"Incomplete build artifacts: expected {sorted(EXPECTED)}, got {sorted(actual)}")
    if any((dist / name).stat().st_size == 0 for name in EXPECTED):
        raise ValueError("An empty executable cannot be published")

    run_url = f"{os.environ['GITHUB_SERVER_URL']}/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    manifest = {"commit": sha, "workflow": run_url, "assets": sorted(EXPECTED)}
    (dist / "build.json").write_text(json.dumps(manifest, indent=2) + "\n")
    names = sorted(EXPECTED | {"build.json"})
    (dist / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256((dist / name).read_bytes()).hexdigest()}  {name}\n" for name in names
    ))

    release = gh("api", f"{api}/releases/tags/main", missing_ok=True)
    if release is not None and not release["prerelease"]:
        raise ValueError("Refusing to overwrite a stable release named main")
    # Recheck after validation, before the first mutation, under the workflow lock.
    if gh("api", f"{api}/git/ref/heads/main")["object"]["sha"] != sha:
        print("Main advanced during validation; skipping this stale build.")
        return
    tag = gh("api", f"{api}/git/ref/tags/main", missing_ok=True)
    if tag is None:
        gh("api", f"{api}/git/refs", payload={"ref": "refs/tags/main", "sha": sha})
    if release is None:
        # First publication stays invisible until all assets and checksums exist.
        release = gh("api", f"{api}/releases", payload={
            "tag_name": "main", "name": "Main build", "draft": True,
            "prerelease": True, "make_latest": "false",
        })

    # Upload binaries before metadata. Existing-channel replacement is not atomic;
    # consumers verify checksums and retry if they download during this interval.
    for name in sorted(EXPECTED):
        subprocess.run(["gh", "release", "upload", "main", str(dist / name),
                        "--repo", repo, "--clobber"], check=True)
    desired = EXPECTED | {"build.json", "SHA256SUMS"}
    # Paginate because a template can eventually select more than 30 targets.
    pages = gh("api", "--paginate", "--slurp", f"{api}/releases/{release['id']}/assets")
    for page in pages:
        for asset in page:
            if asset["name"] not in desired:
                gh("api", "--method", "DELETE", f"{api}/releases/assets/{asset['id']}")
    gh("api", "--method", "PATCH", f"{api}/git/refs/tags/main", payload={"sha": sha, "force": True})
    for name in ("build.json", "SHA256SUMS"):
        subprocess.run(["gh", "release", "upload", "main", str(dist / name),
                        "--repo", repo, "--clobber"], check=True)
    gh("api", "--method", "PATCH", f"{api}/releases/{release['id']}", payload={
        "name": "Main build", "draft": False, "prerelease": True, "make_latest": "false",
        "body": f"Rolling build from `{sha}`.\n\n[CI run]({run_url}). "
                "Download build.json and verify SHA256SUMS. Assets are replaced in place; "
                "retry checksum mismatches during updates. The manifest version is not a commit identifier.",
    })


if __name__ == "__main__":
    publish()
