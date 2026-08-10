"""SHA-256 verification for the committed versioned fixture set."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(fixtures_dir: Path) -> str:
    manifest_path = fixtures_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files")
    version = manifest.get("fixture_manifest_version")
    if not isinstance(files, dict) or not isinstance(version, str):
        raise ValueError("Fixture manifest is malformed")
    if set(files) != {"inventory.csv", "demand.csv", "supplier.csv"}:
        raise ValueError("Fixture manifest must contain exactly T1, T2 and T3 files")
    for name, expected in files.items():
        actual = sha256_file(fixtures_dir / name)
        if actual != expected:
            raise ValueError(f"Fixture hash mismatch: {name}")
    return version
