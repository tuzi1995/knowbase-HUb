"""Offline release-package checks; never import the server or connect to a DB."""

import contextlib
import importlib.util
import io
from pathlib import Path
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("package_deploy", ROOT / "🚀 启动脚本" / "package_deploy.py")
package_deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_deploy)


def test_package_contains_required_runtime_and_no_local_state(tmp_path):
    with contextlib.redirect_stdout(io.StringIO()):
        result = package_deploy.package_project(output_dir=tmp_path)
    with zipfile.ZipFile(result) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert set(package_deploy.RUNTIME_FILES) <= names
        assert {"link_viewer/" + name for name in package_deploy.FRONTEND_FILES} <= names
        assert "requirements.txt" in names
        assert "link_viewer/scroll-performance.css" in names
        assert "link_viewer/platform_intro.css" in names
        assert not names.intersection(package_deploy.EXCLUDED_RUNTIME_FILES)
        assert not any("instance" in name or "secret_key" in name or "node_modules" in name for name in names)
        assert not any("test_" in name or name.endswith(".mjs") or "package-lock" in name for name in names)
        assert "link_viewer/index.prod.html" not in names
        assert "link_viewer/build.js" not in names
        assert "link_viewer/app_v8.min.js" not in names
        assert not {"product_catalog.json", "model_mappings.json", "product_release_intents.json"} & names
        assert "config_templates/product_catalog.example.json" in names


def test_missing_required_module_prevents_archive_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(package_deploy, "RUNTIME_FILES", package_deploy.RUNTIME_FILES + ("not_present.py",))
    with pytest.raises(FileNotFoundError, match="not_present.py"):
        package_deploy.package_project(output_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_unlisted_local_import_blocks_release(monkeypatch):
    monkeypatch.setattr(package_deploy, "RUNTIME_FILES", tuple(
        name for name in package_deploy.RUNTIME_FILES if name != "runtime_safety.py"
    ))
    with pytest.raises(ValueError, match="runtime_safety.py"):
        package_deploy.validate_runtime_inputs(ROOT)


def test_unlisted_page_asset_blocks_release(monkeypatch):
    monkeypatch.setattr(package_deploy, "FRONTEND_FILES", tuple(
        name for name in package_deploy.FRONTEND_FILES if name != "scroll-performance.css"
    ))
    with pytest.raises(ValueError, match="scroll-performance.css"):
        package_deploy.validate_runtime_inputs(ROOT)


def test_cloud_rollback_backup_covers_packaged_runtime_modules():
    launcher = (ROOT / "KnowledgeBaseTool_Local" / "mac脚本" / "发布8085至云端.command").read_text(encoding="utf-8")
    backup_loop = launcher.split("runtime_items=()", 1)[1].split("done", 1)[0]
    for name in package_deploy.RUNTIME_FILES:
        assert name in backup_loop.split(), f"rollback backup omits {name}"
