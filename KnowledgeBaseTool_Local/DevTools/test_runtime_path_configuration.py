import importlib
from pathlib import Path

import scoring_logic
import server


def test_runtime_path_resolver_supports_relative_and_absolute_overrides(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KMATRIX_TEST_PATH", "classified/instance")
    assert server._resolve_runtime_path(
        "KMATRIX_TEST_PATH", "unused", relative_to=str(tmp_path)
    ) == str(tmp_path / "classified" / "instance")

    absolute = tmp_path / "absolute" / "data.db"
    monkeypatch.setenv("KMATRIX_TEST_PATH", str(absolute))
    assert server._resolve_runtime_path("KMATRIX_TEST_PATH", "unused") == str(absolute)


def test_scoring_config_prefers_config_dir_and_keeps_legacy_fallback(monkeypatch, tmp_path) -> None:
    base = tmp_path / "code"
    config = tmp_path / "config"
    base.mkdir()
    config.mkdir()
    legacy_ai = base / "ai_config.json"
    legacy_ai.write_text("{}", encoding="utf-8")
    configured_scoring = config / "scoring_config.json"
    configured_scoring.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("KMATRIX_BASE_DIR", str(base))
    monkeypatch.setenv("KMATRIX_CONFIG_DIR", str(config))
    reloaded = importlib.reload(scoring_logic)

    assert Path(reloaded.SCORING_CONFIG_FILE) == configured_scoring
    assert Path(reloaded.AI_CONFIG_FILE) == legacy_ai

    monkeypatch.delenv("KMATRIX_BASE_DIR")
    monkeypatch.delenv("KMATRIX_CONFIG_DIR")
    importlib.reload(scoring_logic)
