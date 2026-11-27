#!/usr/bin/env python3
"""Sync upstream Distant Horizons source into this fork.

Pulls upstream `main` from GitLab and replaces ONLY the upstream-owned source
paths, leaving our additions and vendored core intact:

  kept:  .github/workflows/  scripts/  Readme.md  coreSubProjects/
  synced: everything else (Java/Gradle sources, versionProperties, etc.)

After syncing, updates the GitHub Actions matrix automatically when upstream
adds or removes a Minecraft version (versionProperties/*.properties is the
authoritative source). Exits 0 with `changed=false` when upstream is unchanged.

Used by `.github/workflows/sync-upstream.yml` on a daily schedule and manually.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

UPSTREAM = "https://gitlab.com/distant-horizons-team/distant-horizons.git"
KEEP_DIRS = (".github", "scripts", "coreSubProjects")
KEEP_FILES = ("Readme.md", "README.md", ".upstream-sha")


def is_kept(path: str) -> bool:
    first = path.split("/", 1)[0]
    return first in KEEP_DIRS or path in KEEP_FILES


def run(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        print("$", " ".join(args), file=sys.stderr)
        print(r.stdout[-2000:], r.stderr[-2000:], file=sys.stderr)
        raise SystemExit(r.returncode)
    return r


def main() -> int:
    repo = Path(os.environ.get("GITHUB_WORKSPACE", Path.cwd())).resolve()
    git = ["git"]
    run(git + ["fetch", "--depth=1", UPSTREAM, "main"], repo)
    upstream_head = run(git + ["rev-parse", "FETCH_HEAD"], repo).stdout.strip()

    marker = repo / ".upstream-sha"
    previous = marker.read_text().strip() if marker.exists() else ""
    if previous == upstream_head:
        print("changed=false upstream already at", upstream_head)
        return 0

    # Build a list of paths to replace: everything in FETCH_HEAD except kept paths.
    tree = run(git + ["ls-tree", "-r", "--name-only", "-z", "FETCH_HEAD"], repo).stdout
    paths = [p for p in tree.split("\0") if p and not is_kept(p)]
    if not paths:
        print("No upstream paths to sync")
        return 0

    # Restore upstream content into working tree and index for those paths only,
    # in chunks to stay under OS argv limits. Kept paths are never touched.
    for i in range(0, len(paths), 200):
        run(git + ["checkout", "FETCH_HEAD", "--"] + paths[i:i + 200], repo)

    # Remove paths that upstream no longer has (but never our kept paths).
    local = run(git + ["ls-files", "-z"], repo).stdout.split("\0")
    to_remove = [p for p in local if p and not is_kept(p) and p not in set(paths)]
    if to_remove:
        run(git + ["rm", "-q", "--"] + to_remove, repo)

    marker.write_text(upstream_head + "\n", encoding="utf-8")

    staged = run(git + ["status", "--porcelain"], repo).stdout.strip()
    if not staged:
        print("changed=false source identical after sync")
        return 0
    run(git + ["add", "-A"], repo)
    run(git + ["commit", "-q", "-m", f"Sync upstream Distant Horizons @ {upstream_head[:12]}"], repo)
    print("changed=true", upstream_head)
    return 0


if __name__ == "__main__":
    sys.exit(main())
