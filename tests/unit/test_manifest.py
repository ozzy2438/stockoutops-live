from pathlib import Path

from stockoutops.evidence.manifest import verify_manifest


def test_fixture_manifest_matches_all_three_committed_files() -> None:
    assert verify_manifest(Path("fixtures/v1")) == "v1-2026-08-10"
