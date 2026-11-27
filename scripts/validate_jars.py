#!/usr/bin/env python3
"""Validate Distant Horizons jars produced by a build.

Checks structural integrity that a Minecraft client would require before a mod
can even load: valid zip, correct loader metadata, declared MC version matches
the requested version, mixin config present, entrypoint classes present, and
metadata version/mod id correct.

This is a load-integrity check, NOT gameplay/render verification: it cannot
prove the mod renders terrain correctly. That requires a real game client.

Usage:
  python3 scripts/validate_jars.py --mc-ver 1.21.1 --artifacts-dir artifacts
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from pathlib import Path

METADATA_BY_LOADER = {
    "fabric": ["fabric.mod.json"],
    "forge": ["META-INF/mods.toml"],
    "neoforge": ["META-INF/neoforge.mods.toml"],
    "forge17": ["mcmod.info"],
    "forge112": ["mcmod.info"],
}
ENTRYPOINTS = {
    "fabric": "com/seibel/distanthorizons/fabric/FabricMain.class",
    # NeoForge uses "NeoforgeMain" (lower-case f) upstream.
    "neoforge": "com/seibel/distanthorizons/neoforge/NeoforgeMain.class",
}
MIN_CLASS_COUNT = 50  # a real DH jar has thousands; catch empty/stub jars


def normalize(v: str) -> str:
    """Upstream abbreviates 26.3.0 as 26.3 in jar names and metadata."""
    parts = v.split(".")
    if v.startswith("26.") and len(parts) == 3:
        return ".".join(parts[:2])
    return v


def check_jar(path: Path, mc_ver: str, loader: str) -> list[str]:
    errors: list[str] = []
    name = path.name
    if path.stat().st_size < 100_000:
        errors.append(f"{name}: suspiciously small ({path.stat().st_size} bytes)")
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return [f"{name}: not a valid zip/jar"]
    with z:
        bad = z.testzip()
        if bad:
            errors.append(f"{name}: corrupt zip entry {bad}")
        names = set(z.namelist())
        classes = [n for n in names if n.endswith(".class")]
        if len(classes) < MIN_CLASS_COUNT:
            errors.append(f"{name}: only {len(classes)} classes (expected >{MIN_CLASS_COUNT})")

        meta_names = METADATA_BY_LOADER.get(loader)
        if not meta_names:
            errors.append(f"{name}: unknown loader {loader}")
            return errors
        found_meta = next((m for m in meta_names if m in names), None)
        if not found_meta:
            errors.append(f"{name}: missing {meta_names[0]} (loader metadata)")
        else:
            text = z.read(found_meta).decode("utf-8", errors="replace")
            if "distanthorizons" not in text.lower():
                errors.append(f"{name}: {found_meta} does not declare mod id 'distanthorizons'")
            if "3.3.5" not in text and not re.search(r'"version"\s*:\s*"3\.3\.5', text):
                errors.append(f"{name}: {found_meta} missing expected mod version")
            declared = normalize(mc_ver)
            if found_meta == "fabric.mod.json":
                try:
                    data = json.loads(text)
                    mc_dep = data.get("depends", {}).get("minecraft", "")
                    if declared not in str(mc_dep):
                        errors.append(f"{name}: fabric.mod.json minecraft dep {mc_dep!r} lacks {declared}")
                except json.JSONDecodeError as e:
                    errors.append(f"{name}: invalid fabric.mod.json: {e}")
            elif found_meta in ("META-INF/mods.toml", "META-INF/neoforge.mods.toml"):
                if not re.search(r'\[\[dependencies\.distanthorizons\]\]', text):
                    errors.append(f"{name}: {found_meta} missing distanthorizons dependency block")
                if declared not in text and mc_ver not in text:
                    errors.append(f"{name}: {found_meta} does not mention MC {mc_ver}/{declared}")
            else:  # mcmod.info
                if declared not in text and mc_ver not in text:
                    errors.append(f"{name}: mcmod.info does not declare MC {mc_ver}/{declared}")

        mixins = [n for n in names if n.endswith("mixins.json")]
        if not mixins:
            errors.append(f"{name}: no mixin config found")
        else:
            for m in mixins:
                try:
                    mdata = json.loads(z.read(m).decode("utf-8", errors="replace"))
                    if "mixins" not in mdata and "client" not in mdata:
                        errors.append(f"{name}: {m} has no mixin lists")
                except json.JSONDecodeError as e:
                    errors.append(f"{name}: invalid {m}: {e}")

        ep = ENTRYPOINTS.get(loader)
        if ep and ep not in names:
            errors.append(f"{name}: entrypoint class {ep} missing")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mc-ver", required=True)
    ap.add_argument("--artifacts-dir", required=True)
    args = ap.parse_args()

    d = Path(args.artifacts_dir)
    if not d.is_dir():
        print(f"artifacts dir missing: {d}")
        return 1
    jars = sorted(d.glob("*.jar"))
    if not jars:
        print(f"no jars in {d}")
        return 1

    failures = 0
    checked = 0
    for jar in jars:
        # prefix is added by CI: "<loader>-<original filename>"
        loader = jar.name.split("-", 1)[0]
        if loader == "merged":
            # merged Forgix jar: validate structurally, skip loader-specific metadata
            try:
                with zipfile.ZipFile(jar) as z:
                    if len([n for n in z.namelist() if n.endswith("mixins.json")]) == 0:
                        print(f"WARN merged jar has no mixin config: {jar.name}")
                checked += 1
            except zipfile.BadZipFile:
                print(f"FAIL merged jar is corrupt: {jar.name}")
                failures += 1
            continue
        errs = check_jar(jar, args.mc_ver, loader)
        checked += 1
        if errs:
            failures += len(errs)
            for e in errs:
                print("FAIL", e)
        else:
            print(f"OK   {jar.name}")

    print(f"Validated {checked} jars for MC {args.mc_ver}: {failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
