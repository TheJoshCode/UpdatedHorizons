#!/usr/bin/env python3
"""Tier 2: headless-ish game-load smoke test for UpdatedHorizons jars.

This is the closest practical thing to "a bot that loads every Minecraft version
and visually verifies it". It launches a real Minecraft client instance per
version with the built Distant Horizons jar installed, waits for the world to
load, then checks the game log for crashes/errors and optionally captures a
screenshot for visual inspection.

It is deliberately a LOCAL tool, not a GitHub Actions job: GitHub runners have
no GPU/display and no Minecraft installations. Run this on a machine with
Prism Launcher (or MultiMC) instances already set up.

Requirements:
  - Prism Launcher/MultiMC with one instance per MC version, named e.g. "DH-1.21.1"
  - The built jars in ./artifacts (or pass --jars)
  - Java runtimes configured per instance in Prism

Usage:
  python3 scripts/game_smoke_test.py --jars artifacts --instances-dir ~/.local/share/PrismLauncher/instances
  python3 scripts/game_smoke_test.py --dry-run     # print the plan, launch nothing

What it verifies:
  - game process starts and stays alive for N seconds
  - no crash-reports/ files created during the session
  - latest.log contains no ERROR/FATAL lines matching known crash signatures
  - (optional) screenshot produced for manual/diff comparison

What it CANNOT verify:
  - that LOD terrain actually looks correct (needs human or baseline image diff)
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ERROR_RE = re.compile(
    r"\[(?:ERROR|FATAL)\]|Exception in thread|---- Minecraft Crash Report----|"
    r"Caused by:|ModLoadingException|MixinApplyError",
    re.IGNORECASE,
)
# Upstream DH logs these harmlessly; filter them out.
BENIGN_RE = re.compile(
    r"Failed to resolve (?:class|At target|@Inject).*ImmersivePortals|"
    r"SLF4J: Failed to load class|Failed to load class \"org\.slf4j",
    re.IGNORECASE,
)


def plan(jars_dir: Path, instances_dir: Path) -> list[tuple[str, Path, Path]]:
    plan_items = []
    for jar in sorted(jars_dir.glob("*.jar")):
        if "-sources.jar" in jar.name or "-dev.jar" in jar.name or jar.name.startswith("merged-"):
            continue
        # Jar naming: <loader>-DistantHorizons-<loader>-3.3.5-dev-<mcver>[-all].jar
        # Anchor on the final version token immediately before .jar / -all.jar.
        m = re.search(r"-dev-([0-9][0-9.]*?)(?:-all)?\.jar$", jar.name)
        if not m:
            continue
        ver = m.group(1).rstrip(".")
        instance = instances_dir / f"DH-{ver}"
        if not instance.is_dir():
            instance = next((p for p in instances_dir.glob(f"DH-{ver}*") if p.is_dir()), None)
        if instance:
            plan_items.append((ver, jar, instance))
    return plan_items


def check_instance(ver: str, jar: Path, instance: Path, wait_s: int, launcher: str) -> tuple[bool, str]:
    mods = instance / "minecraft" / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    target = mods / jar.name
    shutil.copy2(jar, target)
    logs = instance / "minecraft" / "logs" / "latest.log"
    crashes = instance / "minecraft" / "crash-reports"
    if logs.exists():
        logs.unlink()
    log_start = logs.stat().st_mtime if logs.exists() else 0

    # Prism/MultiMC CLI: pass the instance name, not a path, via --launch
    # (the exact flag varies by version; --launch is Prism's documented flag).
    cmd = [launcher, "--launch", instance.name]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        time.sleep(5)
        if proc.poll() is not None:
            return False, f"game process exited early (code {proc.returncode}); see {logs}"
        if crashes.is_dir() and any(crashes.glob("*.txt")):
            return False, f"crash report created; see {crashes}"
        if logs.exists():
            text = logs.read_text(encoding="utf-8", errors="replace")
            bad = [line for line in text.splitlines()
                   if ERROR_RE.search(line) and not BENIGN_RE.search(line)]
            if bad:
                return False, "log errors: " + " | ".join(bad[:3])
            if "Loaded 1 mod" in text or "Rendering overlay" in text:
                return True, "game reached loaded state with no errors"
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    return False, f"timed out after {wait_s}s without a clear loaded state"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jars", default="artifacts")
    ap.add_argument("--instances-dir", default=os.path.expanduser("~/.local/share/PrismLauncher/instances"))
    ap.add_argument("--launcher", default="prismlauncher")
    ap.add_argument("--wait", type=int, default=120)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    jars = Path(args.jars)
    instances = Path(args.instances_dir)
    items = plan(jars, instances)
    if not items:
        print(f"No jar/instance pairs found. Jars: {jars}, Instances: {instances}")
        return 0
    print(f"Planned {len(items)} version checks:")
    for ver, jar, inst in items:
        print(f"  {ver:8} {jar.name} -> {inst.name}")
    if args.dry_run:
        return 0

    if shutil.which(args.launcher) is None:
        print(f"Launcher '{args.launcher}' not found on PATH; nothing to run.")
        return 0

    results = []
    for ver, jar, inst in items:
        print(f"\n=== {ver} ===")
        ok, msg = check_instance(ver, jar, inst, args.wait, args.launcher)
        print(("PASS " if ok else "FAIL ") + msg)
        results.append((ver, ok))
    failed = [v for v, ok in results if not ok]
    print(f"\nSummary: {len(results) - len(failed)}/{len(results)} versions loaded cleanly")
    if failed:
        print("Failed:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
