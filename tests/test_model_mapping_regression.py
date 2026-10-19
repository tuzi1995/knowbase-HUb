import json
import plistlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "KnowledgeBaseTool_Local"))
import server  # noqa: E402


def test_mapping_normalization_preserves_data_when_catalog_cannot_match(tmp_path, monkeypatch):
    mapping_path = tmp_path / "model_mappings.json"
    source = {"历史分类": ["旧型号"]}
    mapping_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(server, "MODEL_MAPPINGS_FILE", str(mapping_path))
    monkeypatch.setattr(server, "parse_product_catalog", lambda: {})

    assert server.get_model_mappings() == source
    assert json.loads(mapping_path.read_text(encoding="utf-8")) == source


def test_launcher_keeps_shared_config_as_default():
    launcher = (ROOT / "KnowledgeBaseTool_Local" / "run_server.sh").read_text(encoding="utf-8")
    assert 'KMATRIX_CONFIG_DIR="${KMATRIX_CONFIG_DIR:-$SCRIPT_DIR/../⚙️ 配置文件}"' in launcher

    plist_path = ROOT / "KnowledgeBaseTool_Local" / "mac脚本" / "com.guoying.kmatrix-8085.plist"
    plist = plistlib.loads(plist_path.read_bytes())
    env = plist["EnvironmentVariables"]
    assert env["KMATRIX_BASE_DIR"].endswith("/KnowledgeBaseTool_Local")
    assert env["KMATRIX_CONFIG_DIR"].endswith("/⚙️ 配置文件")
