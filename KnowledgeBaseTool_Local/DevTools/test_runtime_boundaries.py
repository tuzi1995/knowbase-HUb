import json
import plistlib
from pathlib import Path

import server


def test_json_config_writes_are_atomic_and_leave_no_temp_file(tmp_path, monkeypatch):
    target = tmp_path / "product_catalog.json"
    target.write_text('{"old": true}\n', encoding="utf-8")
    monkeypatch.setattr(server, "PRODUCT_CATALOG_FILE", str(target))

    server.save_product_catalog({"新分类": ["P30"]})

    assert json.loads(target.read_text(encoding="utf-8")) == {"新分类": ["P30"]}
    assert list(tmp_path.glob(".product_catalog.json.*.tmp")) == []


def test_production_launchers_do_not_embed_downstream_token():
    root = Path(__file__).resolve().parents[1]
    plist = plistlib.loads((root / "mac脚本" / "com.guoying.kmatrix-8085.plist").read_bytes())
    environment = plist.get("EnvironmentVariables", {})
    assert "NEW_PRODUCT_RELEASE_DOWNSTREAM_TOKEN" not in environment

    qa_launcher = (root / "mac脚本" / "启动18085-本地测试实例.command").read_text(encoding="utf-8")
    assert "qa-bridge-token-20261010" not in qa_launcher
    assert 'LOCAL_ENV_FILE="$BASE/.kmatrix.qa.env"' in qa_launcher
    bridge = (root.parent / "启动18787-qa桥接.command").read_text(encoding="utf-8")
    assert 'ENV_FILE="$ROOT/KnowledgeBaseTool_Local/.kmatrix.qa.env"' in bridge
