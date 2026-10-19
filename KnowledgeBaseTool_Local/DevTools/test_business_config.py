import json
from pathlib import Path

import pytest

from business_config import prepare_migration, resolve_business_config_path


def sources(tmp_path):
    base, legacy = tmp_path / "base", tmp_path / "legacy"
    base.mkdir()
    legacy.mkdir()
    (legacy / "product_catalog.json").write_text('{"分类":["A","B","C"]}\n', encoding="utf-8")
    (legacy / "model_mappings.json").write_text('{"Z":["B"],"A":["A"]}\n', encoding="utf-8")
    (base / "product_release_intents.json").write_text('{"B":{"release_status":"pending_release"}}\n')
    return base, legacy


def test_preview_does_not_write_and_apply_preserves_effective_sources(tmp_path):
    base, legacy = sources(tmp_path)
    dest = tmp_path / "candidate"
    before = {p: p.read_bytes() for folder in (base, legacy) for p in folder.iterdir()}
    plan = prepare_migration(base, legacy, dest)
    assert not dest.exists()
    assert plan["activated"] is False
    prepare_migration(base, legacy, dest, apply=True)
    assert (dest / "model_mappings.json").read_bytes() == (legacy / "model_mappings.json").read_bytes()
    assert (dest / "product_release_intents.json").read_bytes() == (base / "product_release_intents.json").read_bytes()
    assert json.loads((dest / "model_mappings.json.order.json").read_text()) == ["Z", "A"]
    assert all(p.read_bytes() == content for p, content in before.items())
    with pytest.raises(FileExistsError):
        prepare_migration(base, legacy, dest, apply=True)


def test_invalid_json_cannot_create_a_candidate(tmp_path):
    base, legacy = sources(tmp_path)
    (legacy / "model_mappings.json").write_text('{"partial":')
    with pytest.raises(ValueError):
        prepare_migration(base, legacy, tmp_path / "candidate", apply=True)
    assert not (tmp_path / "candidate").exists()


def test_missing_explicit_config_never_reads_legacy_data(tmp_path):
    base, legacy = sources(tmp_path)
    with pytest.raises(FileNotFoundError, match="未回退"):
        resolve_business_config_path("product_catalog.json", base, legacy, configured="missing")
    assert resolve_business_config_path("product_catalog.json", base, legacy, configured="") == str(legacy / "product_catalog.json")


def test_completed_candidate_is_used_without_overwriting_it(tmp_path):
    base, legacy = sources(tmp_path)
    dest = tmp_path / "candidate"
    prepare_migration(base, legacy, dest, apply=True)
    (legacy / "product_catalog.json").write_text('{"changed": []}')
    path = resolve_business_config_path("product_catalog.json", base, legacy, configured=str(dest))
    assert json.loads(Path(path).read_text()) == {"分类": ["A", "B", "C"]}
