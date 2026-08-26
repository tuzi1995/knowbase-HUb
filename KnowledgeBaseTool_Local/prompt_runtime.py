"""Published Prompt runtime for KnowBase Hub 8085.

The module deliberately keeps request data out of the control-plane bundle.  A
published bundle supplies immutable system instructions and templates; callers
render their dynamic fields locally and may explicitly override system_prompt
for an ad-hoc request.  Such an override is never reported as a production
match.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


SERVICE_ID = "knowbase_hub_8085"
BASE_URL = (os.environ.get("TOOLHUB_PROMPT_CENTER_URL") or "http://127.0.0.1:8000").rstrip("/")
TOKEN_ENV = "KNOWBASE_HUB_TOOLHUB_TOKEN"
TIMEOUT_SECONDS = float(os.environ.get("KNOWBASE_HUB_PROMPT_TIMEOUT_SECONDS") or 5)
ROOT = Path(__file__).resolve().parent
TOOLHUB_ROOT = ROOT.parents[2] / "toolhub"
DB_PATH = Path(os.environ.get("KNOWBASE_HUB_PROMPT_CENTER_DB_PATH") or TOOLHUB_ROOT / ".cache" / "prompt_version_center.db")
CACHE_DIR = ROOT / ".prompt_runtime_cache"


class PromptRuntimeError(RuntimeError):
    """Raised when a published Prompt cannot be resolved or verified."""


def component_hash(value: Any) -> str:
    content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _cache_path(prompt_id: str) -> Path:
    digest = hashlib.sha256(prompt_id.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _validate(prompt_id: str, prompt: Any) -> dict[str, Any]:
    if not isinstance(prompt, dict) or str(prompt.get("prompt_id") or "").strip() != prompt_id:
        raise PromptRuntimeError("ToolHub 返回的 8085 Prompt 资源标识无效")
    if not prompt.get("version_id") or not prompt.get("release_id"):
        raise PromptRuntimeError("ToolHub 返回的 8085 Prompt 缺少已发布版本信息")
    bundle = prompt.get("content_bundle")
    hashes = prompt.get("component_hashes")
    if not isinstance(bundle, dict) or not isinstance(hashes, dict):
        raise PromptRuntimeError("ToolHub 返回的 8085 Prompt 内容包不完整")
    for key in ("system_prompt", "user_prompt_template"):
        if not isinstance(bundle.get(key), str) or not bundle[key].strip():
            raise PromptRuntimeError(f"ToolHub 已发布 8085 Prompt 缺少组件：{key}")
        if component_hash(bundle[key]) != str(hashes.get(key) or ""):
            raise PromptRuntimeError(f"ToolHub 已发布 8085 Prompt 组件哈希校验失败：{key}")
    result = dict(prompt)
    result["runtime_prompt_hash"] = component_hash(bundle["system_prompt"])
    return result


def _read_cache(prompt_id: str) -> dict[str, Any]:
    try:
        payload = json.loads(_cache_path(prompt_id).read_text(encoding="utf-8"))
        if payload.get("cache_schema") != "knowbase-hub-8085-prompt-runtime-v1":
            raise ValueError("cache schema")
        return _validate(prompt_id, payload.get("prompt"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise PromptRuntimeError("ToolHub 不可用且没有有效的 8085 Prompt 缓存") from exc


def _write_cache(prompt_id: str, prompt: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(prompt_id)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"cache_schema": "knowbase-hub-8085-prompt-runtime-v1", "prompt": prompt}, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _read_local_published(prompt_id: str) -> dict[str, Any]:
    """Read the local production pointer; never fall back to latest_version_id."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            """SELECT p.release_id, p.version_id, v.prompt_hash, v.content_json,
                      v.source_version, v.observed_at
                 FROM prompt_release_pointers p
                 JOIN prompt_versions v ON v.version_id=p.version_id
                WHERE p.prompt_id=? AND p.environment='production'""",
            (prompt_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise PromptRuntimeError("8085 本地 Prompt 中心不可用") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass
    if not row:
        raise PromptRuntimeError("8085 Prompt 尚未发布生产版本")
    try:
        bundle = json.loads(row[3])
    except json.JSONDecodeError as exc:
        raise PromptRuntimeError("8085 已发布 Prompt 内容不是合法 JSON") from exc
    prompt = {
        "prompt_id": prompt_id,
        "release_id": row[0],
        "version_id": row[1],
        "prompt_hash": row[2],
        "content_bundle": bundle,
        "component_hashes": {key: component_hash(value) for key, value in bundle.items()},
        "source_version": row[4],
        "observed_at": row[5],
    }
    return _validate(prompt_id, prompt)


def resolve_published_prompt(prompt_id: str, *, execution_ref: str = "") -> dict[str, Any]:
    """Resolve an immutable production pointer and keep only verified cache."""
    token = str(os.environ.get(TOKEN_ENV) or "").strip()
    source = "control_plane"
    prompt: dict[str, Any] | None = None
    if token:
        try:
            response = requests.get(
                f"{BASE_URL}/api/prompt-center/runtime/{quote(prompt_id, safe='')}?environment=production",
                headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            prompt = _validate(prompt_id, response.json().get("prompt"))
            _write_cache(prompt_id, prompt)
        except (requests.RequestException, ValueError, PromptRuntimeError):
            source = "verified_cache"
    if prompt is None:
        try:
            prompt = _read_cache(prompt_id)
        except PromptRuntimeError:
            # A local production pointer is still immutable and is useful for
            # installs that run beside ToolHub without a service token.
            prompt = _read_local_published(prompt_id)
            source = "verified_cache"
    prompt = dict(prompt)
    prompt["resolution_source"] = source
    prompt["execution_ref"] = execution_ref or "unspecified"
    prompt["service_id"] = SERVICE_ID
    return prompt


def record_prompt_receipts(prompt: dict[str, Any], *, execution_ref: str) -> list[dict[str, Any]]:
    """Submit exact component receipts when a service token is configured.

    Missing credentials or a temporarily unavailable center defer the receipt;
    a published prompt mismatch still raises and prevents a false verification.
    """
    token = str(os.environ.get(TOKEN_ENV) or "").strip()
    if not token:
        return []
    base = prompt.get("content_bundle") or {}
    source = str(prompt.get("resolution_source") or "control_plane")
    receipts: list[dict[str, Any]] = []
    for key in ("system_prompt", "user_prompt_template"):
        idem = hashlib.sha256(f"{SERVICE_ID}|{prompt['prompt_id']}|{prompt['version_id']}|{execution_ref}|{key}".encode()).hexdigest()
        payload = {
            "idempotency_key": f"knowbase-8085-prompt-{idem}",
            "prompt_id": prompt["prompt_id"], "version_id": prompt["version_id"],
            "service_id": SERVICE_ID, "component_key": key,
            "runtime_prompt_hash": component_hash(base[key]),
            "resolution_source": source if source in {"control_plane", "verified_cache"} else "control_plane",
            "execution_ref": execution_ref, "environment": "production",
        }
        try:
            response = requests.post(f"{BASE_URL}/api/prompt-center/runtime-receipts", headers={"Authorization": f"Bearer {token}"}, json=payload, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            receipt = (response.json() or {}).get("receipt")
            if not isinstance(receipt, dict):
                raise PromptRuntimeError("8085 Prompt 回执响应无效")
            receipts.append(receipt)
        except requests.RequestException:
            # The execution remains bound to the published version; the next
            # run can submit the receipt after the center recovers.
            continue
    return receipts


def render_published_template(template: str, values: dict[str, Any]) -> str:
    """Render the simple {{name}} variables emitted by the 8085 adapter."""
    import re
    def replace(match: re.Match[str]) -> str:
        value = values.get(match.group(1).strip(), "")
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
    rendered = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", replace, str(template or ""))
    if "{{runtime_expression:" in rendered:
        raise PromptRuntimeError("8085 Prompt 含未支持的运行时表达式")
    return rendered

