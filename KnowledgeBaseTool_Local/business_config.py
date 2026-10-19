"""Business JSON locations and an offline, non-destructive migration tool."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


BUSINESS_FILES = (
    "product_catalog.json", "model_mappings.json", "product_release_intents.json",
)
ORDER_FILE = "model_mappings.json.order.json"


def resolve_business_config_path(filename, base_dir, legacy_config_dir, configured=None):
    """An explicit business directory never falls back to legacy state."""
    configured = os.environ.get("KMATRIX_BUSINESS_CONFIG_DIR", "") if configured is None else configured
    if str(configured).strip():
        directory = Path(str(configured)).expanduser()
        if not directory.is_absolute():
            directory = Path(base_dir) / directory
        path = directory.resolve() / filename
        if not path.is_file():
            raise FileNotFoundError(f"实例业务配置缺失: {path}；请先完成迁移，未回退到旧配置。")
        validate_json(filename, path.read_bytes())
        return str(path)
    external = Path(legacy_config_dir) / filename
    if external.exists():
        return str(external)
    return str(Path(base_dir) / filename)


def validate_json(filename, content):
    value = json.loads(content)
    expected = list if filename == ORDER_FILE else dict
    if not isinstance(value, expected):
        raise ValueError(f"{filename} 应为 JSON {expected.__name__}")
    return value


def _digest(content):
    return hashlib.sha256(content).hexdigest()


def prepare_migration(base_dir, source_dir, destination, apply=False):
    """Copy effective legacy files verbatim; never edit/delete the originals.

    apply only creates a new candidate directory. It does not modify startup
    configuration, databases, services or a previously prepared destination.
    """
    base_dir, source_dir, destination = map(lambda p: Path(p).resolve(), (base_dir, source_dir, destination))
    if destination.exists():
        raise FileExistsError(f"目标目录已存在，拒绝覆盖: {destination}")
    records = []
    contents = {}
    for filename in BUSINESS_FILES:
        candidates = [source_dir / filename, base_dir / filename]
        source = next((p for p in candidates if p.is_file()), None)
        if source is None and filename != "product_release_intents.json":
            raise FileNotFoundError(f"缺少业务配置: {filename}")
        content = source.read_bytes() if source else b"{}\n"
        validate_json(filename, content)
        contents[filename] = content
        records.append({"name": filename, "source": str(source) if source else None,
                        "sha256": _digest(content), "generated": source is None})
    mapping_source = Path(next(r["source"] for r in records if r["name"] == "model_mappings.json"))
    order_source = mapping_source.with_name(ORDER_FILE)
    order = order_source.read_bytes() if order_source.is_file() else (
        json.dumps(list(validate_json("model_mappings.json", contents["model_mappings.json"])),
                   ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    validate_json(ORDER_FILE, order)
    contents[ORDER_FILE] = order
    records.append({"name": ORDER_FILE, "source": str(order_source) if order_source.is_file() else None,
                    "sha256": _digest(order), "generated": not order_source.is_file()})
    manifest = {"schema": "kmatrix-business-config-v1", "destination": str(destination),
                "files": records, "activated": False}
    if not apply:
        return manifest
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".business-config-", dir=destination.parent))
    try:
        for filename, content in contents.items():
            (temporary / filename).write_bytes(content)
            if _digest((temporary / filename).read_bytes()) != _digest(content):
                raise RuntimeError(f"迁移校验失败: {filename}")
        for record in records:
            if record["source"] and _digest(Path(record["source"]).read_bytes()) != record["sha256"]:
                raise RuntimeError(f"源文件在复制期间发生变化，请重试: {record['name']}")
        (temporary / "migration-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        # rename without overwrite; an existing nonempty target is rejected.
        if destination.exists():
            raise FileExistsError(f"目标目录已存在，拒绝覆盖: {destination}")
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return manifest


def main():
    parser = argparse.ArgumentParser(description="离线复制业务 JSON，默认只预览；不会切换运行实例。")
    parser.add_argument("--base-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--apply", action="store_true", help="仅创建候选目录，不启动或切换服务")
    args = parser.parse_args()
    report = prepare_migration(args.base_dir, args.source_dir, args.destination, apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
