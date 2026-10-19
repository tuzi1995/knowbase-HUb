"""New-product release domain and transactional orchestration."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except Exception:  # pragma: no cover
    psycopg2 = None
    Json = None
    RealDictCursor = None

MODEL_STATES = {"pending_release", "releasing", "released", "release_cancelled"}
PENDING_STATES = {"pending_release", "blocked", "published", "cancelled", "superseded"}
OUTBOX_MAX_ATTEMPTS = 10
FORMAL_CONTENT_FIELDS = {
    "question", "answer", "question_type", "answer_type", "if_bm25",
    "similar_questions", "error_list", "keyword_list", "image_urls",
    "video_urls", "file_urls", "link_type", "link_url", "product_category_name",
}


def _bool_env(name):
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _strip_nul_text(value):
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {key: _strip_nul_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_strip_nul_text(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_strip_nul_text(item) for item in value)
    return value


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _association_change_snapshots(existing_models, target_model, before_configured, after_configured):
    before_models = {str(model or "").strip() for model in existing_models or [] if str(model or "").strip()}
    target_model = str(target_model or "").strip()
    if target_model:
        if before_configured:
            before_models.add(target_model)
        else:
            before_models.discard(target_model)
    after_models = set(before_models)
    if target_model:
        if after_configured:
            after_models.add(target_model)
        else:
            after_models.discard(target_model)
    return (
        {"configured": bool(before_configured), "products": sorted(before_models)},
        {"configured": bool(after_configured), "products": sorted(after_models)},
    )


def _normalize_pending_modification_record(record):
    """Expose a stable table shape for both pending versions and modification rows."""
    item = deepcopy(record or {})
    if item.get("pending_id"):
        item.setdefault("record_id", item["pending_id"])
    if item.get("kb_id"):
        item.setdefault("question_wiki_id", item["kb_id"])
    if "before" not in item and "baseline_snapshot" in item:
        item["before"] = deepcopy(item.get("baseline_snapshot") or {})
    if "after" not in item and "pending_snapshot" in item:
        item["after"] = deepcopy(item.get("pending_snapshot") or {})
    if not item.get("target_model"):
        models = list(dict.fromkeys(
            str(binding.get("model_id") or "").strip()
            for binding in item.get("bindings") or []
            if str(binding.get("model_id") or "").strip()
        ))
        if models:
            item["target_model"] = "、".join(models)
    if not item.get("target_model") and item.get("product_name"):
        item["target_model"] = item["product_name"]
    if not item.get("source_module") and item.get("pending_id"):
        item["source_module"] = "知识库管理"
    return item


def _clean_ids(values):
    if isinstance(values, str):
        values = [part.strip() for part in values.replace("，", ",").split(",")]
    result = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in result:
            result.append(item)
    return result


class RepositoryUnavailable(RuntimeError):
    pass


class ReleaseConflict(ValueError):
    def __init__(self, message, *, code="release_conflict", details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class MemoryReleaseRepository:
    """Complete deterministic domain repository for tests and local dry-runs."""

    def __init__(self, state=None):
        state = deepcopy(state or {})
        self.models = state.get("models", {})
        self.applications = state.get("applications", {})
        self.kbs = state.get("kbs", {})
        self.associations = state.get("associations", {})
        self.pending = state.get("pending", {})
        self.bindings = state.get("bindings", [])
        self.batches = state.get("batches", {})
        self.formal_records = state.get("formal_records", [])
        self.pending_modifications = state.get("pending_modifications", [])
        self.outbox = state.get("outbox", [])
        self.audit = state.get("audit", [])
        self.idempotency = state.get("idempotency", {})
        self.failure_injection = None

    def export_state(self):
        return deepcopy({k: getattr(self, k) for k in (
            "models", "applications", "kbs", "associations", "pending", "bindings",
            "batches", "formal_records", "pending_modifications", "outbox", "audit", "idempotency")})

    def gate(self):
        return {"db_available": True, "exit_switch": True, "migration_passed": True, "reconciliation_passed": True}

    def ensure_model(self, model_id, status="pending_release", actor="system"):
        model_id = str(model_id or "").strip()
        if not model_id or status not in MODEL_STATES:
            raise ValueError("型号或发布状态无效")
        current = self.models.get(model_id)
        if current:
            # Catalog maintenance can remove a model and later add the same
            # name again. Treat that as a fresh pending application when the
            # catalog explicitly requests pending status; otherwise an old
            # released row would mask the new catalog intent forever.
            if status == "pending_release" and current.get("release_status") in {"released", "release_cancelled"}:
                current.update({
                    "release_status": "pending_release",
                    "current_application_id": "",
                    "association_version": int(current.get("association_version") or 0) + 1,
                    "updated_at": _utc_now(),
                })
                application = self.start_application(model_id, actor=actor, reason="型号重新录入")
                current["current_application_id"] = application["request_id"]
                return deepcopy(current)
            return deepcopy(current)
        row = {
            "model_id": model_id, "release_status": status, "release_version": 0,
            "association_version": 0, "current_application_id": "", "released_at": None,
            "released_by": "", "created_at": _utc_now(), "updated_at": _utc_now(),
        }
        self.models[model_id] = row
        if status == "pending_release":
            application = self.start_application(model_id, actor=actor, reason="型号创建")
            row["current_application_id"] = application["request_id"]
        return deepcopy(row)

    def model(self, model_id):
        row = self.models.get(str(model_id or "").strip())
        return deepcopy(row) if row else None

    def model_state_map(self):
        return deepcopy(self.models)

    def application(self, request_id):
        request_id = str(request_id or "").strip()
        row = self.applications.get(request_id)
        if row is None:
            # The publish API accepts the caller's idempotency/request key as
            # the public handle. Resolve that handle to the persisted
            # application generated when the model entered the workbench.
            row = next((item for item in self.applications.values()
                        if str(item.get("idempotency_key") or "") == request_id), None)
        return deepcopy(row) if row else None

    def batch_by_idempotency(self, idempotency_key):
        batch_id = self.idempotency.get(str(idempotency_key or "").strip())
        return deepcopy(self.batches.get(batch_id)) if batch_id else None

    def seed_formal_kb(self, kb_id, snapshot, content_version=1):
        kb_id = str(kb_id or "").strip()
        if kb_id and kb_id not in self.kbs:
            self.kbs[kb_id] = {
                "kb_id": kb_id, "kb_scope": "formal", "content_version": int(content_version or 1),
                "snapshot": deepcopy(snapshot or {}), "content_hash": _digest(snapshot or {}), "updated_at": _utc_now(),
            }
        return deepcopy(self.kbs.get(kb_id))

    def start_application(self, model_id, actor="system", reason=""):
        model_id = str(model_id or "").strip()
        model = self.models.get(model_id)
        if not model:
            self.ensure_model(model_id, "pending_release", actor)
            model = self.models[model_id]
        current = self.applications.get(model.get("current_application_id"))
        if current and current.get("status") == "pending_release":
            return deepcopy(current)
        if model["release_status"] not in {"pending_release", "release_cancelled"}:
            raise ReleaseConflict("只有待上线或已取消型号可以新建发布申请", code="invalid_model_state")
        generations = [int(row.get("generation") or 1) for row in self.applications.values() if row.get("model_id") == model_id]
        request_id = f"NRA-{uuid.uuid4().hex}"
        row = {
            "request_id": request_id, "model_id": model_id, "status": "pending_release",
            "release_status": "pending_release", "generation": max(generations or [0]) + 1,
            "pending_version": max(generations or [0]) + 1,
            "reason": str(reason or ""), "requested_by": str(actor or "system"),
            "created_at": _utc_now(), "updated_at": _utc_now(), "cancelled_at": None,
            "cancelled_by": "", "cancel_reason": "", "reapplied_from": current.get("request_id", "") if current else "",
            "batch_id": "", "idempotency_key": "", "preview_token_digest": "",
        }
        self.applications[request_id] = row
        model.update({"release_status": "pending_release", "current_application_id": request_id,
                      "association_version": int(model.get("association_version") or 0) + 1, "updated_at": _utc_now()})
        self._audit("application_created", actor, model_id=model_id, request_id=request_id, reason=reason)
        return deepcopy(row)

    def _association_key(self, kb_id, model_id):
        return _json([str(kb_id or ""), str(model_id or "")])

    def _model_associations(self, model_id):
        return [row for row in self.associations.values() if row.get("model_id") == model_id and row.get("association_status") != "cancelled"]

    def _kb_associations(self, kb_id, status=None):
        rows = [row for row in self.associations.values() if row.get("kb_id") == kb_id]
        return [row for row in rows if status is None or row.get("association_status") == status]

    def _pending_for_kb(self, kb_id, states=None):
        rows = [row for row in self.pending.values() if row.get("kb_id") == kb_id]
        if states:
            rows = [row for row in rows if row.get("status") in states]
        return sorted(rows, key=lambda row: (int(row.get("sequence_no") or 0), row.get("created_at") or ""))

    def _active_tail(self, kb_id):
        rows = self._pending_for_kb(kb_id, {"pending_release", "blocked"})
        return rows[-1] if rows else None

    def save_change(self, kb_id, payload):
        before_state = self.export_state()
        try:
            return self._save_change(kb_id, payload)
        except Exception:
            failure_injection = self.failure_injection
            self.__dict__.update(MemoryReleaseRepository(before_state).__dict__)
            self.failure_injection = failure_injection
            raise

    def _save_change(self, kb_id, payload):
        # PostgreSQL JSONB cannot represent NUL even when JSON escapes it as \\u0000.
        payload = _strip_nul_text(deepcopy(payload or {}))
        kb_id = str(kb_id or payload.get("kb_id") or payload.get("question_wiki_id") or "").strip()
        if not kb_id:
            raise ValueError("缺少 kb_id")
        actor = str(payload.get("actor") or payload.get("requested_by") or "system")
        model_ids = _clean_ids(payload.get("model_ids") or payload.get("trigger_model_ids") or payload.get("product_name"))
        expected_states = payload.get("expected_model_states") or {}
        if expected_states and not isinstance(expected_states, dict):
            raise ValueError("expected_model_states 必须为对象")
        changed_models = []
        for model_id, expected_status in expected_states.items():
            current_model = self.models.get(str(model_id))
            actual_status = (current_model or {}).get("release_status")
            if actual_status != str(expected_status):
                changed_models.append({
                    "model_id": str(model_id),
                    "expected": str(expected_status),
                    "actual": actual_status,
                })
        if changed_models:
            raise ReleaseConflict(
                "提交期间型号状态已变化，请刷新预览并重新确认",
                code="model_state_changed",
                details={"changed_models": changed_models, "preserve_input": True},
            )
        snapshot = deepcopy(payload.get("snapshot") or payload.get("pending_snapshot") or {})
        current = self.kbs.get(kb_id)
        is_create = bool(payload.get("is_create"))
        if is_create and current:
            raise ReleaseConflict("新建知识编号已存在，请刷新后重新编辑", code="kb_already_exists")
        if not is_create and not current and isinstance(payload.get("baseline_snapshot"), dict):
            current = self.seed_formal_kb(
                kb_id, payload.get("baseline_snapshot"), payload.get("baseline_content_version") or 1)
            current = self.kbs.get(kb_id)
        before = deepcopy((current or {}).get("snapshot") or {})
        changed_fields = _clean_ids(payload.get("changed_fields"))
        if not changed_fields and snapshot:
            changed_fields = sorted(field for field in FORMAL_CONTENT_FIELDS if before.get(field) != snapshot.get(field))
        formal_changed = bool(set(changed_fields) & FORMAL_CONTENT_FIELDS)
        effect_mode = str(payload.get("effect_mode") or ("with_model_release" if formal_changed else "association_only"))
        if not formal_changed:
            effect_mode = "association_only"
        if effect_mode not in {"association_only", "immediate", "with_model_release"}:
            raise ValueError("effect_mode 必须为 immediate 或 with_model_release")
        association_before = {}
        for model_id in model_ids:
            model = self.models.get(model_id)
            if not model:
                raise ReleaseConflict(f"型号 {model_id} 不存在", code="model_not_found")
            key = self._association_key(kb_id, model_id)
            association_before[model_id] = deepcopy(self.associations.get(key) or {})
            association = self.associations.get(key) or {
                "association_id": f"A-{uuid.uuid4().hex}", "kb_id": kb_id, "model_id": model_id,
                "source_operation_id": str(payload.get("operation_id") or f"OP-{uuid.uuid4().hex}"), "created_at": _utc_now(),
            }
            association.update({"application_id": model.get("current_application_id") or "",
                                "association_status": "pending_release" if model["release_status"] == "pending_release" else "active",
                                "content_binding_mode": "latest_formal", "updated_at": _utc_now()})
            self.associations[key] = association
            model["association_version"] = int(model.get("association_version") or 0) + 1
        removed_associations = {}
        for model_id in _clean_ids(payload.get("removed_model_ids")):
            association = self.associations.get(self._association_key(kb_id, model_id))
            if association and association.get("association_status") == "pending_release":
                removed_associations[model_id] = deepcopy(association)
                association.update({"association_status": "cancelled", "updated_at": _utc_now()})
                for binding in self.bindings:
                    if binding.get("kb_id") == kb_id and binding.get("model_id") == model_id and binding.get("status") == "waiting":
                        binding["status"] = "cancelled"
        if effect_mode == "association_only":
            pending_records = []
            operation_id = str(payload.get("operation_id") or f"KB-{uuid.uuid4().hex}")
            source_module = str(payload.get("source_module") or "知识库管理平台")
            for model_id in model_ids:
                if self.models[model_id]["release_status"] != "pending_release":
                    continue
                association = self.associations[self._association_key(kb_id, model_id)]
                pending_records.append(self._record_pending_modification(
                    question_wiki_id=kb_id,
                    target_model=model_id,
                    before=association_before.get(model_id) or {},
                    after=association,
                    change_type="kb_association",
                    actor=actor,
                    source_module=source_module,
                    operation_id=operation_id,
                ))
            for model_id, before_association in removed_associations.items():
                pending_records.append(self._record_pending_modification(
                    question_wiki_id=kb_id,
                    target_model=model_id,
                    before=before_association,
                    after=self.associations[self._association_key(kb_id, model_id)],
                    change_type="kb_association_remove",
                    actor=actor,
                    source_module=source_module,
                    operation_id=operation_id,
                ))
            return {"effect_mode": effect_mode, "kb_id": kb_id, "changed_fields": [],
                    "associations": deepcopy(self._kb_associations(kb_id)),
                    "pending_modification_records": pending_records}
        if effect_mode == "immediate":
            if current and current.get("kb_scope") == "draft_pending_release":
                raise ReleaseConflict(
                    "仅关联待上线型号的草稿 KB 不能绕过型号上线直接转正式",
                    code="draft_requires_model_release",
                )
            active_pending = self._pending_for_kb(kb_id, {"pending_release", "blocked"})
            cancel_ids = set(_clean_ids(payload.get("cancel_pending_ids")))
            if active_pending and not cancel_ids:
                raise ReleaseConflict("存在待发布版本，立即生效前必须明确选择要取消的 pending", code="pending_selection_required", details={"pending_ids": [row["pending_id"] for row in active_pending]})
            for pending_id in cancel_ids:
                self.cancel_pending(pending_id, actor=actor, reason="立即生效替代待发布内容")
            version = int((current or {}).get("content_version") or 0) + 1
            self.kbs[kb_id] = {"kb_id": kb_id, "kb_scope": "formal", "content_version": version,
                               "snapshot": snapshot, "content_hash": _digest(snapshot), "updated_at": _utc_now()}
            record = self._formal_record(kb_id, "content_update" if current else "create", actor, before, snapshot, version)
            return {"effect_mode": effect_mode, "kb_id": kb_id, "content_version": version, "formal_record": record}
        pending_models = [model_id for model_id in model_ids if self.models[model_id]["release_status"] == "pending_release"]
        trigger_ids = _clean_ids(payload.get("trigger_model_ids") or pending_models)
        if not trigger_ids or any(model_id not in pending_models for model_id in trigger_ids):
            raise ReleaseConflict("随型号上线必须选择当前待上线型号", code="invalid_trigger_models")
        active_online = sorted({row["model_id"] for row in self._kb_associations(kb_id, "active") if self.models.get(row["model_id"], {}).get("release_status") == "released"})
        if active_online and not bool(payload.get("public_kb_confirmed")):
            raise ReleaseConflict("公共 KB 内容必须由内容负责人确认在线影响范围", code="public_kb_confirmation_required", details={"affected_models": active_online})
        parent_id = str(payload.get("parent_pending_id") or "").strip()
        tail = self._active_tail(kb_id)
        expected_parent = tail["pending_id"] if tail else ""
        if parent_id != expected_parent:
            raise ReleaseConflict("pending 必须接在当前版本链尾部", code="invalid_parent_pending", details={"expected_parent_pending_id": expected_parent})
        content_hash = _digest(snapshot)
        for row in self._pending_for_kb(kb_id, {"pending_release"}):
            if row.get("content_hash") == content_hash and row.get("parent_pending_id", "") == parent_id:
                self._bind_pending(row["pending_id"], trigger_ids, actor)
                return {"effect_mode": effect_mode, "kb_id": kb_id, "pending": deepcopy(row), "shared": True}
        sequence = max([int(row.get("sequence_no") or 0) for row in self._pending_for_kb(kb_id)] or [0]) + 1
        pending_id = f"P-{uuid.uuid4().hex}"
        row = {
            "pending_id": pending_id, "kb_id": kb_id, "sequence_no": sequence,
            "baseline_content_version": int((current or {}).get("content_version") or 0),
            "baseline_snapshot": deepcopy(tail.get("pending_snapshot") if tail else before),
            "parent_pending_id": parent_id, "pending_snapshot": snapshot, "content_hash": content_hash,
            "pending_change_type": "update" if current and not is_create else "create", "status": "pending_release",
            "replaces_pending_id": "", "published_content_version": None, "formal_record_id": "",
            "public_kb_confirmed": bool(payload.get("public_kb_confirmed")), "impact_models_at_edit": active_online,
            "confirmed_by": str(payload.get("confirmed_by") or actor), "created_by": actor,
            "created_at": _utc_now(), "updated_at": _utc_now(),
        }
        self.pending[pending_id] = row
        self._bind_pending(pending_id, trigger_ids, actor)
        if not current:
            self.kbs[kb_id] = {"kb_id": kb_id, "kb_scope": "draft_pending_release", "content_version": 0, "snapshot": {}, "content_hash": "", "updated_at": _utc_now()}
        return {"effect_mode": effect_mode, "kb_id": kb_id, "pending": deepcopy(row), "shared": False}

    def _bind_pending(self, pending_id, model_ids, actor):
        pending = self.pending[pending_id]
        existing = {(row["pending_id"], row["model_id"]) for row in self.bindings}
        for index, model_id in enumerate(model_ids):
            if (pending_id, model_id) not in existing:
                self.bindings.append({"binding_id": f"PB-{uuid.uuid4().hex}", "pending_id": pending_id,
                    "kb_id": pending["kb_id"], "model_id": model_id,
                    "application_id": self.models[model_id].get("current_application_id") or "",
                    "binding_role": "trigger" if index == 0 else "co_trigger", "status": "waiting",
                    "bound_by": actor, "bound_at": _utc_now()})
            association = self.associations[self._association_key(pending["kb_id"], model_id)]
            association.update({"content_binding_mode": "pending_chain", "pending_id": pending_id, "updated_at": _utc_now()})

    def replace_pending(self, pending_id, snapshot, actor="system", public_kb_confirmed=False):
        old = self.pending.get(str(pending_id or ""))
        if not old or old["status"] != "pending_release":
            raise ReleaseConflict("pending 不存在或不可修订", code="pending_not_replaceable")
        old["status"] = "superseded"
        new_id = f"P-{uuid.uuid4().hex}"
        new = deepcopy(old)
        new.update({"pending_id": new_id, "pending_snapshot": deepcopy(snapshot or {}), "content_hash": _digest(snapshot or {}),
                    "status": "pending_release", "replaces_pending_id": old["pending_id"], "public_kb_confirmed": bool(public_kb_confirmed),
                    "confirmed_by": actor, "created_by": actor, "created_at": _utc_now(), "updated_at": _utc_now()})
        self.pending[new_id] = new
        for binding in self.bindings:
            if binding["pending_id"] == old["pending_id"] and binding["status"] == "waiting":
                model_id = binding["model_id"]
                binding["status"] = "cancelled"
                self._bind_pending(new_id, [model_id], actor)
        for child in self.pending.values():
            if child.get("parent_pending_id") == old["pending_id"] and child.get("status") in {"pending_release", "blocked"}:
                child.update({"parent_pending_id": new_id, "updated_at": _utc_now()})
                if child.get("block_reason") == "前置 pending 已被替代，必须重新编辑":
                    child.update({"status": "pending_release", "block_reason": ""})
        self._audit("pending_replaced", actor, pending_id=new_id, replaces_pending_id=old["pending_id"])
        return deepcopy(new)

    def cancel_pending(self, pending_id, actor="system", reason=""):
        row = self.pending.get(str(pending_id or ""))
        if not row or row["status"] not in {"pending_release", "blocked"}:
            raise ReleaseConflict("pending 不存在或不可取消", code="pending_not_cancellable")
        row.update({"status": "cancelled", "cancelled_by": actor, "cancelled_at": _utc_now(), "cancel_reason": str(reason or ""), "updated_at": _utc_now()})
        for binding in self.bindings:
            if binding["pending_id"] == row["pending_id"] and binding["status"] == "waiting":
                binding["status"] = "cancelled"
                association = self.associations.get(self._association_key(row["kb_id"], binding["model_id"]))
                if association:
                    association.update({"content_binding_mode": "latest_formal", "pending_id": "", "updated_at": _utc_now()})
        for child in self.pending.values():
            if child.get("parent_pending_id") == row["pending_id"] and child.get("status") in {"pending_release", "blocked"}:
                child.update({"status": "blocked", "block_reason": "前置 pending 已取消，必须重新编辑"})
        self._audit("pending_cancelled", actor, pending_id=row["pending_id"], reason=reason)
        return deepcopy(row)

    def pending_chain(self, kb_id):
        rows = self._pending_for_kb(str(kb_id or ""))
        for row in rows:
            row["bindings"] = [deepcopy(binding) for binding in self.bindings if binding["pending_id"] == row["pending_id"]]
        return rows

    def pending_records(self, filters=None):
        filters = filters or {}
        requested_status = filters.get("status")
        rows = []
        for row in self.pending.values():
            if requested_status:
                if row["status"] != requested_status: continue
            elif row["status"] != "pending_release":
                continue
            if filters.get("kb_id") and row["kb_id"] != filters["kb_id"]: continue
            item = deepcopy(row); item["record_scope"] = "pending"
            item["bindings"] = [deepcopy(binding) for binding in self.bindings if binding["pending_id"] == row["pending_id"]]
            rows.append(_normalize_pending_modification_record(item))
        for row in self.pending_modifications:
            if requested_status:
                if row.get("status") != requested_status: continue
            elif row.get("status") != "pending_release":
                continue
            if filters.get("kb_id") and row.get("question_wiki_id") != filters["kb_id"]:
                continue
            item = deepcopy(row)
            item["record_scope"] = "pending"
            rows.append(_normalize_pending_modification_record(item))
        return sorted(rows, key=lambda row: (str(row.get("kb_id") or row.get("question_wiki_id") or ""), int(row.get("sequence_no") or 0), str(row.get("created_at") or "")))

    def _record_pending_modification(self, *, question_wiki_id, target_model, before, after,
                                     change_type, actor, source_module, operation_id):
        operation_id = str(operation_id or "").strip()
        existing = next((row for row in self.pending_modifications
                         if operation_id
                         and row.get("source_operation_id") == operation_id
                         and row.get("question_wiki_id") == str(question_wiki_id)
                         and row.get("target_model") == str(target_model)), None)
        if existing:
            return deepcopy(existing)
        row = {
            "record_id": f"PM-{uuid.uuid4().hex}",
            "record_scope": "pending",
            "release_status": "pending_release",
            "source_module": str(source_module or ""),
            "source_operation_id": operation_id,
            "question_wiki_id": str(question_wiki_id),
            "kb_id": str(question_wiki_id),
            "target_model": str(target_model),
            "product_name": str(target_model),
            "before": deepcopy(before),
            "after": deepcopy(after),
            "change_type": str(change_type or "pending_change"),
            "created_by": str(actor or "system"),
            "created_at": _utc_now(),
            "published_at": None,
            "release_batch_id": "",
            "formal_record_id": "",
            "status": "pending_release",
        }
        self.pending_modifications.append(row)
        return deepcopy(row)

    def record_matrix_changes(self, changes, actor="system", source_module="机型矩阵管理", operation_id="", pending_model_ids=None):
        """Persist matrix changes for pending models without touching formal history."""
        operation_id = str(operation_id or "").strip()
        created = []
        for change in changes or []:
            wiki_id = str(change.get("question_wiki_id") or "").strip()
            model_id = str(change.get("product_name") or "").strip()
            if not wiki_id or not model_id:
                continue
            model = self.models.get(model_id) or {}
            if model.get("release_status") != "pending_release" and model_id not in set(pending_model_ids or []):
                continue
            created.append(self._record_pending_modification(
                question_wiki_id=wiki_id,
                target_model=model_id,
                before=bool(change.get("old_is_configured")),
                after=bool(change.get("new_is_configured")),
                change_type="matrix_association",
                actor=actor,
                source_module=source_module,
                operation_id=operation_id,
            ))
        return created

    def cancel_matrix_operation(self, operation_id, actor="system", reason=""):
        operation_id = str(operation_id or "").strip()
        changed = []
        for row in self.pending_modifications:
            if row.get("source_operation_id") != operation_id or row.get("status") != "pending_release":
                continue
            row.update({"status": "cancelled", "record_scope": "pending",
                        "release_status": "release_cancelled", "cancelled_by": str(actor or "system"),
                        "cancel_reason": str(reason or "矩阵本地事务失败，已执行补偿取消"),
                        "cancelled_at": _utc_now(), "updated_at": _utc_now()})
            changed.append(deepcopy(row))
        if changed:
            self._audit("matrix_pending_compensated", actor, operation_id=operation_id, reason=reason)
        return changed

    def preview_model(self, model_id):
        model_id = str(model_id or "").strip()
        model = self.models.get(model_id)
        if not model: raise ReleaseConflict("型号不存在", code="model_not_found")
        if model["release_status"] != "pending_release": raise ReleaseConflict("只有待上线型号可以预览", code="invalid_model_state")
        application = self.applications.get(model.get("current_application_id"))
        if not application or application.get("status") != "pending_release": raise ReleaseConflict("型号没有有效的待上线申请", code="application_required")
        publishable, latest_formal, blocked, drafts, impacts = [], [], [], [], {}
        for association in self._model_associations(model_id):
            kb_id = association["kb_id"]; kb = self.kbs.get(kb_id) or {}
            if kb.get("kb_scope") == "draft_pending_release": drafts.append(kb_id)
            pending_id = association.get("pending_id") if association.get("content_binding_mode") == "pending_chain" else ""
            pending = self.pending.get(pending_id)
            if not pending or pending.get("status") == "published": latest_formal.append(kb_id); continue
            if pending.get("status") == "blocked":
                blocked.append({"kb_id": kb_id, "pending_id": pending_id,
                                "reason": pending.get("block_reason") or "pending 已阻断"})
                continue
            if pending.get("status") != "pending_release":
                blocked.append({"kb_id": kb_id, "pending_id": pending_id,
                                "reason": f"pending 状态 {pending.get('status')} 不可发布"})
                continue
            parent_id = pending.get("parent_pending_id") or ""; parent = self.pending.get(parent_id) if parent_id else None
            current_version = int(kb.get("content_version") or 0); reason = ""
            if parent_id and (not parent or parent.get("status") != "published"): reason = "前置 pending 尚未发布"
            elif parent_id and current_version != int(parent.get("published_content_version") or 0): reason = "正式基线已偏离前置 pending 的发布版本"
            elif not parent_id and current_version != int(pending.get("baseline_content_version") or 0): reason = "正式基线版本已变化"
            elif not pending.get("public_kb_confirmed") and self._kb_associations(kb_id, "active"): reason = "公共 KB 影响尚未确认"
            if reason: blocked.append({"kb_id": kb_id, "pending_id": pending_id, "reason": reason})
            else: publishable.append({"kb_id": kb_id, "pending_id": pending_id, "sequence_no": pending["sequence_no"]})
            impacts[kb_id] = sorted({row["model_id"] for row in self._kb_associations(kb_id, "active") if self.models.get(row["model_id"], {}).get("release_status") == "released"})
        preview = {"model_id": model_id, "application_id": application["request_id"], "release_status": model["release_status"],
                   "release_version": int(model.get("release_version") or 0), "association_version": int(model.get("association_version") or 0),
                   "publishable_pending": publishable, "latest_formal_kbs": sorted(set(latest_formal)), "blocked": blocked,
                   "draft_kbs": sorted(set(drafts)), "public_impact_models": impacts, "safe_to_publish": not blocked}
        preview["digest"] = _digest(preview)
        return preview

    def release_model(self, model_id, *, idempotency_key, operator, preview_digest):
        model_id = str(model_id or "").strip(); idempotency_key = str(idempotency_key or "").strip()
        if not idempotency_key: raise ValueError("缺少 idempotency_key")
        if idempotency_key in self.idempotency:
            existing = self.batches[self.idempotency[idempotency_key]]
            if existing.get("model_id") != model_id:
                raise ReleaseConflict("幂等键已被其他型号使用", code="idempotency_key_conflict")
            return deepcopy(existing)
        before_state = self.export_state(); batch_id = f"RB-{uuid.uuid4().hex}"; started_at = _utc_now()
        try:
            preview = self.preview_model(model_id)
            if preview["digest"] != preview_digest: raise ReleaseConflict("预览后状态或内容已变化，请重新预览", code="stale_preview")
            if not preview["safe_to_publish"]: raise ReleaseConflict("存在阻断项，不能发布", code="release_blocked", details={"blocked": preview["blocked"]})
            model = self.models[model_id]; application = self.applications[model["current_application_id"]]; model["release_status"] = "releasing"
            batch = {"batch_id": batch_id, "model_id": model_id, "application_id": application["request_id"],
                     "release_version": int(model.get("release_version") or 0) + 1, "status": "validating", "release_status": "validating",
                     "association_version": model["association_version"], "preview_digest": preview_digest, "idempotency_key": idempotency_key,
                     "operator": operator, "formal_record_ids": [], "published_pending_ids": [], "started_at": started_at, "finished_at": None, "error_summary": ""}
            self.batches[batch_id] = batch
            if self.failure_injection == "after_releasing": raise RuntimeError("injected database failure")
            for association in list(self._model_associations(model_id)):
                kb_id = association["kb_id"]; kb = self.kbs.get(kb_id) or {"kb_id": kb_id, "kb_scope": "draft_pending_release", "content_version": 0, "snapshot": {}}
                before = deepcopy(kb.get("snapshot") or {}); pending = self.pending.get(association.get("pending_id") or ""); change_type = "association_add"
                if pending and pending.get("status") == "pending_release":
                    version = int(kb.get("content_version") or 0) + 1
                    kb.update({"kb_scope": "formal", "content_version": version, "snapshot": deepcopy(pending["pending_snapshot"]), "content_hash": pending["content_hash"], "updated_at": _utc_now()})
                    pending.update({"status": "published", "published_content_version": version, "updated_at": _utc_now()}); change_type = pending["pending_change_type"]; batch["published_pending_ids"].append(pending["pending_id"])
                    for binding in self.bindings:
                        if binding["pending_id"] != pending["pending_id"] or binding["status"] != "waiting": continue
                        if binding["model_id"] == model_id: binding["status"] = "consumed"
                        else:
                            binding["status"] = "released_by_peer"; peer = self.associations.get(self._association_key(kb_id, binding["model_id"]))
                            if peer: peer.update({"content_binding_mode": "latest_formal", "pending_id": "", "updated_at": _utc_now()})
                elif kb.get("kb_scope") == "draft_pending_release": raise ReleaseConflict(f"草稿 KB {kb_id} 缺少可发布内容", code="draft_without_pending")
                association.update({"association_status": "active", "content_binding_mode": "latest_formal", "pending_id": "", "released_content_version": int(kb.get("content_version") or 0), "released_at": _utc_now(), "updated_at": _utc_now()}); self.kbs[kb_id] = kb
                record = self._formal_record(kb_id, change_type, operator, before, kb.get("snapshot") or {}, int(kb.get("content_version") or 0), model_id=model_id, batch_id=batch_id); batch["formal_record_ids"].append(record["record_id"])
                if pending: pending["formal_record_id"] = record["record_id"]
            for pending_record in self.pending_modifications:
                if pending_record.get("target_model") != model_id or pending_record.get("status") != "pending_release":
                    continue
                before_value = pending_record.get("before")
                after_value = pending_record.get("after")
                before_snapshot = before_value if isinstance(before_value, dict) else {"configured": before_value}
                after_snapshot = after_value if isinstance(after_value, dict) else {"configured": after_value}
                record = self._formal_record(
                    pending_record.get("question_wiki_id") or pending_record.get("kb_id"),
                    pending_record.get("change_type") or "matrix_association",
                    pending_record.get("created_by") or operator,
                    before_snapshot,
                    after_snapshot,
                    0,
                    model_id=model_id,
                    batch_id=batch_id,
                    source_module=pending_record.get("source_module") or "机型矩阵管理",
                    source_operation_id=pending_record.get("source_operation_id") or "",
                )
                pending_record.update({"status": "published", "record_scope": "formal", "release_status": "released", "published_at": _utc_now(), "release_batch_id": batch_id, "formal_record_id": record["record_id"]})
                batch["formal_record_ids"].append(record["record_id"])
            if self.failure_injection == "before_commit": raise RuntimeError("injected database failure")
            model.update({"release_status": "released", "release_version": batch["release_version"], "released_at": _utc_now(), "released_by": operator, "updated_at": _utc_now()})
            application.update({"status": "released", "release_status": "released", "batch_id": batch_id, "idempotency_key": idempotency_key, "updated_at": _utc_now()}); batch.update({"status": "completed", "release_status": "completed", "finished_at": _utc_now()})
            self.outbox.append({"event_id": f"OB-{uuid.uuid4().hex}", "batch_id": batch_id, "event_type": "model_released", "idempotency_key": f"model_released:{batch_id}", "payload": {"model_id": model_id, "batch_id": batch_id, "formal_record_ids": batch["formal_record_ids"]}, "status": "pending", "attempts": 0, "last_error": "", "receipt": None, "created_at": _utc_now(), "updated_at": _utc_now()})
            self.idempotency[idempotency_key] = batch_id; self._audit("model_released", operator, model_id=model_id, request_id=application["request_id"], batch_id=batch_id)
            return deepcopy(batch)
        except Exception as exc:
            self.__dict__.update(MemoryReleaseRepository(before_state).__dict__)
            failed = {"batch_id": batch_id, "model_id": model_id, "application_id": (self.models.get(model_id) or {}).get("current_application_id", ""), "status": "failed", "release_status": "failed", "idempotency_key": idempotency_key, "operator": operator, "formal_record_ids": [], "published_pending_ids": [], "started_at": started_at, "finished_at": _utc_now(), "error_summary": str(exc)}
            self.batches[batch_id] = failed
            raise

    def cancel_application(self, request_id, *, actor="system", reason=""):
        row = self.applications.get(str(request_id or ""));
        if not row: return None
        model = self.models[row["model_id"]]
        if row["status"] not in {"pending_release", "released"} or model["release_status"] not in {"pending_release", "released"}:
            raise ReleaseConflict("只有待上线或已上线申请可以取消", code="application_not_cancellable")
        row.update({"status": "release_cancelled", "release_status": "release_cancelled", "cancelled_at": _utc_now(), "cancelled_by": actor, "cancel_reason": str(reason or ""), "updated_at": _utc_now()}); model.update({"release_status": "release_cancelled", "updated_at": _utc_now()})
        for association in self._model_associations(model["model_id"]):
            if association.get("application_id") == row["request_id"]: association["association_status"] = "cancelled"
        for binding in self.bindings:
            if binding.get("application_id") == row["request_id"] and binding.get("status") == "waiting": binding["status"] = "cancelled"
        for pending in self.pending.values():
            if pending.get("status") not in {"pending_release", "blocked"}:
                continue
            waiting = any(binding.get("pending_id") == pending.get("pending_id") and binding.get("status") == "waiting"
                          for binding in self.bindings)
            if not waiting:
                self.cancel_pending(pending["pending_id"], actor=actor, reason="发布申请已取消")
        for pending_record in self.pending_modifications:
            if pending_record.get("target_model") != model["model_id"]:
                continue
            if pending_record.get("status") != "pending_release":
                continue
            pending_record.update({
                "status": "cancelled",
                "record_scope": "pending",
                "release_status": "release_cancelled",
                "cancelled_by": str(actor or "system"),
                "cancel_reason": str(reason or "发布申请已取消"),
                "cancelled_at": _utc_now(),
                "updated_at": _utc_now(),
            })
        self._audit("application_cancelled", actor, model_id=model["model_id"], request_id=row["request_id"], reason=reason); return deepcopy(row)

    def reapply(self, request_id, actor="system", reason=""):
        old = self.application(request_id)
        if not old or old.get("status") != "release_cancelled": return None
        return self.start_application(old["model_id"], actor=actor, reason=reason or "取消后重新申请")

    def cancel(self, request_id): return self.cancel_application(request_id)
    def create_release(self, *, request_id, idempotency_key, model_id, kb_id, payload, preview_digest, preview_expires_at):
        preview = self.preview_model(model_id)
        return self.release_model(model_id, idempotency_key=idempotency_key,
                                  operator=str(payload.get("requested_by") or "system"),
                                  preview_digest=preview_digest or preview["digest"])

    def workspace(self):
        return {"models": [deepcopy(row) for row in self.models.values()], "pending_requests": [deepcopy(row) for row in self.applications.values()], "applications": [deepcopy(row) for row in self.applications.values()], "pending_records": self.pending_records(), "batches": [deepcopy(row) for row in self.batches.values()], "outbox": deepcopy(self.outbox)}

    def claim_outbox(self, batch_id="", limit=50):
        rows = []
        for row in self.outbox:
            row.setdefault("event_id", f"OB-{uuid.uuid4().hex}")
            if batch_id and row["batch_id"] != batch_id: continue
            if row["status"] not in {"pending", "failed"}: continue
            if int(row.get("attempts") or 0) >= OUTBOX_MAX_ATTEMPTS:
                continue
            row.update({"status": "processing", "attempts": row["attempts"] + 1, "updated_at": _utc_now()}); rows.append(deepcopy(row))
            if len(rows) >= int(limit): break
        return rows

    def finish_outbox(self, event_id, *, success, receipt=None, error=""):
        for row in self.outbox:
            if row["event_id"] == event_id:
                row.update({"status": "sent" if success else "failed", "receipt": deepcopy(receipt), "last_error": str(error or ""), "updated_at": _utc_now()}); return deepcopy(row)
        return None

    def retry_outbox(self, batch_id): return self.claim_outbox(batch_id)
    def reconcile(self):
        pending = sum(1 for row in self.outbox if row["status"] in {"pending", "processing", "failed"}
                      and int(row.get("attempts") or 0) < OUTBOX_MAX_ATTEMPTS)
        exhausted = [{"event_id": row.get("event_id"), "attempts": row.get("attempts"),
                      "last_error": row.get("last_error") or ""}
                     for row in self.outbox if row["status"] == "failed"
                     and int(row.get("attempts") or 0) >= OUTBOX_MAX_ATTEMPTS]
        formal_ids = {row.get("record_id") for row in self.formal_records}
        ledger_issues = []
        for row in self.pending_modifications:
            target = self.models.get(str(row.get("target_model") or "")) or {}
            if row.get("status") == "pending_release" and target.get("release_status") == "released":
                ledger_issues.append({"record_id": row.get("record_id"), "issue": "released_model_pending_record"})
            if row.get("status") == "published" and not row.get("formal_record_id"):
                ledger_issues.append({"record_id": row.get("record_id"), "issue": "published_record_missing_formal_id"})
            if row.get("formal_record_id") and row.get("formal_record_id") not in formal_ids:
                ledger_issues.append({"record_id": row.get("record_id"), "issue": "formal_record_missing"})
        if not pending and not exhausted and not ledger_issues:
            return {"status": "passed", "pending_outbox": 0}
        return {"status": "pending", "pending_outbox": pending, "exhausted_outbox": exhausted,
                "pending_modification_issues": ledger_issues}

    def _formal_record(self, kb_id, change_type, actor, before, after, version, model_id="", batch_id="", source_module="", source_operation_id=""):
        row = {"record_id": f"FR-{uuid.uuid4().hex}", "kb_id": kb_id, "question_wiki_id": kb_id, "record_scope": "formal", "change_type": change_type, "modifier": actor, "model_id": model_id, "batch_id": batch_id, "content_version": version, "before": deepcopy(before), "after": deepcopy(after), "source_module": source_module, "source_operation_id": source_operation_id, "created_at": _utc_now()}; self.formal_records.append(row); return deepcopy(row)

    def _audit(self, action, actor, **details): self.audit.append({"audit_id": f"AU-{uuid.uuid4().hex}", "action": action, "actor": str(actor or "system"), "details": deepcopy(details), "created_at": _utc_now()})


class PostgresReleaseRepository:
    """Durable aggregate repository. All release side effects commit atomically."""

    def __init__(self, config_path=None, connect=None):
        self.config_path = Path(config_path) if config_path else Path(os.getenv("KMATRIX_CONFIG_DIR") or Path(__file__).parent) / "supabase_config_local.json"
        self._connect_factory = connect

    def _config(self):
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8")); cfg = data.get("local_db") if isinstance(data, dict) else None; return cfg if isinstance(cfg, dict) else None
        except Exception: return None

    def _connect(self):
        if self._connect_factory: return self._connect_factory()
        cfg = self._config()
        if not cfg or psycopg2 is None: raise RepositoryUnavailable("本地主 PostgreSQL 未配置或 psycopg2 不可用")
        kwargs = {key: cfg[key] for key in ("host", "port", "database", "user", "password") if cfg.get(key) is not None}; kwargs["connect_timeout"] = int(os.getenv("NEW_PRODUCT_RELEASE_DB_TIMEOUT", "3")); return psycopg2.connect(**kwargs)

    def gate(self):
        try:
            conn = self._connect(); conn.autocommit = True
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT to_regclass('public.product_release_domain_state') AS state_table, to_regclass('public.product_release_pending_modification') AS pending_modification_table")
                schema = cur.fetchone()
                state_table = schema["state_table"]
                pending_modification_table = schema["pending_modification_table"]
                cur.execute("SELECT enabled,migration_batch_id FROM public.release_migration_exit_switch WHERE switch_name=%s", ("new_product_release",)); switch = cur.fetchone(); batch_id = str(switch["migration_batch_id"] or "") if switch else ""
                cur.execute("SELECT status FROM public.product_release_migration_batch WHERE migration_batch_id=%s", (batch_id,)); migration = cur.fetchone()
                cur.execute("SELECT reconciliation_status FROM public.product_release_reconciliation WHERE migration_batch_id=%s ORDER BY id DESC LIMIT 1", (batch_id,)); reconciliation = cur.fetchone()
            conn.close(); return {"db_available": bool(state_table and pending_modification_table), "exit_switch": bool(switch and switch["enabled"] is True), "migration_batch_id": batch_id, "migration_passed": bool(migration and migration["status"] == "passed"), "reconciliation_passed": bool(reconciliation and reconciliation["reconciliation_status"] == "passed")}
        except Exception as exc: return {"db_available": False, "exit_switch": False, "migration_passed": False, "reconciliation_passed": False, "error": str(exc)}

    def _state(self, cur):
        cur.execute("SELECT state_json FROM public.product_release_domain_state WHERE singleton_id=1 FOR UPDATE"); row = cur.fetchone()
        if not row:
            cur.execute("INSERT INTO public.product_release_domain_state(singleton_id,state_json,revision) VALUES (1,'{}'::jsonb,0) RETURNING state_json"); row = cur.fetchone()
        return MemoryReleaseRepository(row["state_json"] or {})

    def _run(self, method, *args, materialize=False, materialize_change=False, **kwargs):
        conn = self._connect(); conn.autocommit = False
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("new-product-release-domain",)); repository = self._state(cur); result = getattr(repository, method)(*args, **kwargs)
                if materialize: self._materialize_release(cur, repository, result)
                if materialize_change and result.get("effect_mode") == "immediate":
                    self._materialize_immediate(cur, repository, result)
                self._materialize_domain_projection(cur, repository)
                cur.execute("UPDATE public.product_release_domain_state SET state_json=%s,revision=revision+1,updated_at=now() WHERE singleton_id=1", (Json(repository.export_state()),))
            conn.commit(); return result
        except Exception: conn.rollback(); raise
        finally: conn.close()

    def _read(self, method, *args, **kwargs):
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT state_json FROM public.product_release_domain_state WHERE singleton_id=1"); row = cur.fetchone()
            return getattr(MemoryReleaseRepository((row or {}).get("state_json") or {}), method)(*args, **kwargs)
        finally: conn.close()

    def _materialize_release(self, cur, repository, batch):
        # The domain aggregate is authoritative. These projections are updated
        # in the same transaction, so a failed projection rolls back the release.
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='product_release_batch'")
        batch_columns = {row["column_name"] for row in cur.fetchall()}
        payload = {key: batch.get(key) for key in ("batch_id", "release_status", "operator", "started_at", "finished_at", "error_summary") if key in batch_columns}
        if "migration_batch_id" in batch_columns: payload["migration_batch_id"] = batch["batch_id"]
        if payload:
            columns = list(payload); sql = f'INSERT INTO public.product_release_batch ({",".join(chr(34)+c+chr(34) for c in columns)}) VALUES ({",".join(["%s"]*len(columns))}) ON CONFLICT (migration_batch_id) DO UPDATE SET ' + ",".join(f'{chr(34)+c+chr(34)}=EXCLUDED.{chr(34)+c+chr(34)}' for c in columns if c != "migration_batch_id"); cur.execute(sql, list(payload.values()))

        pending_records_by_formal_id = {
            str(item.get("formal_record_id") or ""): item
            for item in repository.pending_modifications
            if item.get("formal_record_id")
        }
        for record_id in batch.get("formal_record_ids") or []:
            record = next(row for row in repository.formal_records if row["record_id"] == record_id)
            pending_record = pending_records_by_formal_id.get(record_id)
            if pending_record and pending_record.get("change_type") == "matrix_association":
                kb_id = str(pending_record.get("question_wiki_id") or pending_record.get("kb_id") or "").strip()
                model_id = str(pending_record.get("target_model") or "").strip()
                before_configured = bool(pending_record.get("before"))
                after_configured = bool(pending_record.get("after"))
                cur.execute(
                    "SELECT product_name FROM public.product_matrix "
                    "WHERE question_wiki_id=%s AND is_configured IS TRUE "
                    "AND association_status='active' AND release_status='released'",
                    (kb_id,),
                )
                existing_models = [row["product_name"] for row in cur.fetchall()]
                before_snapshot, after_snapshot = _association_change_snapshots(
                    existing_models, model_id, before_configured, after_configured,
                )
                record["before"] = before_snapshot
                record["after"] = after_snapshot
                cur.execute(
                    "SELECT question, answer, product_category_name, product_name FROM public.knowledge_base_v1 "
                    "WHERE question_wiki_id=%s LIMIT 1",
                    (kb_id,),
                )
                kb_row = cur.fetchone() or {}
                kb = repository.kbs.get(kb_id)
                kb_snapshot = (kb or {}).get("snapshot") or {}
                product_names = _clean_ids(
                    kb_row.get("product_name")
                    if kb_row.get("product_name") is not None
                    else kb_snapshot.get("product_name")
                )
                if after_configured:
                    if model_id and model_id not in product_names:
                        product_names.append(model_id)
                else:
                    product_names = [name for name in product_names if name != model_id]
                if kb:
                    kb.setdefault("snapshot", {})["product_name"] = ", ".join(product_names)
                self._upsert_available(cur, "product_matrix", {
                    "question_wiki_id": kb_id,
                    "product_name": model_id,
                    "is_configured": after_configured,
                    "manual_edit": True,
                    "edit_source": "submitted",
                    "last_synced_at": pending_record.get("published_at") or _utc_now(),
                    "question_content": kb_row.get("question"),
                    "answer_content": kb_row.get("answer"),
                    "product_category": kb_row.get("product_category_name"),
                    "association_status": "active" if after_configured else "cancelled",
                    "release_status": "released",
                    "product_release_scope": "formal",
                    "migration_batch_id": batch["batch_id"],
                }, ("question_wiki_id", "product_name"))
            kb = repository.kbs.get(record["kb_id"])
            snapshot = deepcopy((kb or {}).get("snapshot") or {})
            if not snapshot and isinstance(record.get("after"), dict):
                snapshot = deepcopy(record.get("after") or {})
            snapshot.update({
                "question_wiki_id": record["kb_id"], "kb_scope": "formal",
                "release_status": "released", "content_version": int((kb or {}).get("content_version") or record.get("content_version") or 0),
                "migration_batch_id": batch["batch_id"],
            })
            if kb:
                self._upsert_available(cur, "knowledge_base_v1", snapshot, ("question_wiki_id",))
            self._insert_available(cur, "knowledge_base_modifications", {
                "kb_id": record["kb_id"], "question_wiki_id": record["kb_id"],
                "record_scope": "formal", "release_status": "released",
                "change_type": record["change_type"], "modifier": record["modifier"],
                "modification_time": record["created_at"], "operation_id": record["record_id"],
                "migration_batch_id": batch["batch_id"],
                "source_module": record.get("source_module") or "",
                "change_meta": Json({"before": record["before"], "after": record["after"],
                                     "model_id": record["model_id"], "source_operation_id": record.get("source_operation_id") or "", "release_batch_id": batch["batch_id"],
                                     "action_kind": "association" if pending_record else "content_edit",
                                     "changed_fields": ["products"] if pending_record else []}),
            })
        for association in repository._model_associations(batch["model_id"]):
            if association.get("association_status") != "active":
                continue
            kb = repository.kbs[association["kb_id"]]
            snapshot = kb.get("snapshot") or {}
            self._upsert_available(cur, "product_matrix", {
                "question_wiki_id": association["kb_id"], "product_name": association["model_id"],
                "is_configured": True, "question_content": snapshot.get("question"),
                "answer_content": snapshot.get("answer"), "product_category": snapshot.get("product_category_name"),
                "association_status": "active", "release_status": "released",
                "product_release_scope": "formal", "migration_batch_id": batch["batch_id"],
            }, ("question_wiki_id", "product_name"))

    def _materialize_immediate(self, cur, repository, result):
        kb = repository.kbs[result["kb_id"]]
        record = result["formal_record"]
        snapshot = deepcopy(kb.get("snapshot") or {})
        snapshot.update({
            "question_wiki_id": kb["kb_id"], "kb_scope": "formal",
            "release_status": "released", "content_version": kb["content_version"],
        })
        self._upsert_available(cur, "knowledge_base_v1", snapshot, ("question_wiki_id",))
        self._insert_available(cur, "knowledge_base_modifications", {
            "kb_id": kb["kb_id"], "question_wiki_id": kb["kb_id"],
            "record_scope": "formal", "release_status": "released",
            "change_type": record["change_type"], "modifier": record["modifier"],
            "modification_time": record["created_at"], "operation_id": record["record_id"],
            "change_meta": Json({"before": record["before"], "after": record["after"],
                                 "effect_mode": "immediate"}),
        })

    def _materialize_domain_projection(self, cur, repository):
        for application in repository.applications.values():
            self._upsert_available(cur, "product_release_request", {
                "request_id": application["request_id"], "question_wiki_id": "",
                "target_model": application["model_id"], "release_status": application["release_status"],
                "migration_batch_id": application["request_id"], "requested_by": application["requested_by"],
                "generation": application["generation"], "idempotency_key": application.get("idempotency_key") or "",
                "preview_token_digest": application.get("preview_token_digest") or "",
                "cancelled_at": application.get("cancelled_at"), "cancelled_by": application.get("cancelled_by") or "",
                "cancel_reason": application.get("cancel_reason") or "",
                # The migrated request table calls this link
                # ``predecessor_request_id``; keep the domain state's
                # ``reapplied_from`` semantics visible in that projection.
                "predecessor_request_id": application.get("reapplied_from") or "",
                "batch_id": application.get("batch_id") or "", "created_at": application["created_at"],
                "updated_at": application["updated_at"],
            }, ("request_id",))
        for pending in repository.pending.values():
            self._upsert_available(cur, "product_release_pending_version", {
                "question_wiki_id": pending["kb_id"], "pending_version": pending["sequence_no"],
                "pending_id": pending["pending_id"], "sequence_no": pending["sequence_no"],
                "release_status": pending["status"], "source_model": "",
                "snapshot_json": _json(pending.get("pending_snapshot") or {}),
                "baseline_snapshot_json": Json(pending.get("baseline_snapshot") or {}),
                "baseline_content_version": pending.get("baseline_content_version"),
                "parent_pending_id": pending.get("parent_pending_id") or "",
                "content_hash": pending.get("content_hash") or "", "pending_change_type": pending.get("pending_change_type") or "",
                "replaces_pending_id": pending.get("replaces_pending_id") or "",
                "published_content_version": pending.get("published_content_version"),
                "formal_record_id": pending.get("formal_record_id") or "",
                "public_kb_confirmed": bool(pending.get("public_kb_confirmed")),
                "impact_models_json": Json(pending.get("impact_models_at_edit") or []),
                "confirmed_by": pending.get("confirmed_by") or "", "block_reason": pending.get("block_reason") or "",
                "cancelled_at": pending.get("cancelled_at"), "cancelled_by": pending.get("cancelled_by") or "",
                "cancel_reason": pending.get("cancel_reason") or "", "created_at": pending["created_at"],
                "updated_at": pending["updated_at"],
            }, ("question_wiki_id", "pending_version"))
        for pending_record in repository.pending_modifications:
            self._upsert_available(cur, "product_release_pending_modification", {
                "record_id": pending_record["record_id"],
                "record_scope": pending_record.get("record_scope") or "pending",
                "release_status": pending_record.get("release_status") or pending_record.get("status") or "pending_release",
                "source_module": pending_record.get("source_module") or "",
                "source_operation_id": pending_record.get("source_operation_id") or "",
                "question_wiki_id": pending_record.get("question_wiki_id") or pending_record.get("kb_id") or "",
                "target_model": pending_record.get("target_model") or pending_record.get("product_name") or "",
                "before_json": Json(pending_record.get("before")),
                "after_json": Json(pending_record.get("after")),
                "change_type": pending_record.get("change_type") or "matrix_association",
                "status": pending_record.get("status") or "pending_release",
                "created_by": pending_record.get("created_by") or "",
                "created_at": pending_record.get("created_at"),
                "published_at": pending_record.get("published_at"),
                "release_batch_id": pending_record.get("release_batch_id") or "",
                "formal_record_id": pending_record.get("formal_record_id") or "",
            }, ("record_id",))
        for association in repository.associations.values():
            matching = next((row for row in reversed(repository.bindings)
                             if row.get("kb_id") == association["kb_id"] and row.get("model_id") == association["model_id"]), {})
            model = repository.models.get(association["model_id"]) or {}
            self._upsert_available(cur, "product_release_model_binding", {
                "question_wiki_id": association["kb_id"], "product_name": association["model_id"],
                "migration_batch_id": association.get("application_id") or association["association_id"],
                "kb_scope": (repository.kbs.get(association["kb_id"]) or {}).get("kb_scope") or "unscoped",
                "record_scope": "formal" if association.get("association_status") == "active" else "unscoped",
                "release_status": model.get("release_status") or "pending_release",
                "pending_id": association.get("pending_id") or matching.get("pending_id") or "",
                "application_id": association.get("application_id") or "",
                "association_status": association.get("association_status"),
                "content_binding_mode": association.get("content_binding_mode"),
                "binding_role": matching.get("binding_role"), "binding_status": matching.get("status"),
                "released_content_version": association.get("released_content_version"),
                "source_operation_id": association.get("source_operation_id") or "",
                "created_at": association["created_at"], "updated_at": association["updated_at"],
            }, ("question_wiki_id", "product_name", "migration_batch_id"))
        for batch in repository.batches.values():
            self._upsert_available(cur, "product_release_batch", {
                "migration_batch_id": batch["batch_id"], "release_status": batch["release_status"],
                "model_id": batch.get("model_id"), "application_id": batch.get("application_id"),
                "release_version": batch.get("release_version"), "association_version": batch.get("association_version"),
                "preview_digest": batch.get("preview_digest"), "idempotency_key": batch.get("idempotency_key"),
                "operator": batch.get("operator"), "created_by": batch.get("operator") or "",
                "formal_record_ids_json": Json(batch.get("formal_record_ids") or []),
                "published_pending_ids_json": Json(batch.get("published_pending_ids") or []),
                "started_at": batch.get("started_at"), "finished_at": batch.get("finished_at"),
                "error_summary": batch.get("error_summary") or "",
            }, ("migration_batch_id",))
        for event in repository.outbox:
            self._update_or_insert_available(cur, "product_release_business_outbox", {
                "event_id": event["event_id"], "migration_batch_id": event["batch_id"],
                "event_type": event["event_type"], "op_type": event["event_type"],
                "idempotency_key": event["idempotency_key"], "payload_json": _json(event.get("payload") or {}),
                "status": event["status"], "attempts": event["attempts"], "last_error": event.get("last_error") or "",
                "receipt_json": Json(event.get("receipt")) if event.get("receipt") is not None else None,
                "created_at": event["created_at"], "updated_at": event["updated_at"],
            }, ("event_id",))
        for audit in repository.audit:
            details = audit.get("details") or {}
            self._upsert_available(cur, "product_release_audit", {
                "audit_id": audit["audit_id"], "action": audit["action"], "actor": audit["actor"],
                "model_id": details.get("model_id") or "", "request_id": details.get("request_id") or "",
                "pending_id": details.get("pending_id") or "", "batch_id": details.get("batch_id") or "",
                "reason": details.get("reason") or "", "details_json": Json(details),
                "created_at": audit["created_at"],
            }, ("audit_id",))

    @staticmethod
    def _available_payload(cur, table, payload):
        cur.execute(
            "SELECT column_name,udt_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
        column_types = {row["column_name"]: row["udt_name"] for row in cur.fetchall()}
        data = {key: value for key, value in payload.items() if key in column_types}
        for column, value in data.items():
            if column_types[column] in {"json", "jsonb"} and value is not None and not isinstance(value, Json):
                data[column] = Json(value)
        return data

    @classmethod
    def _insert_available(cls, cur, table, payload):
        data = cls._available_payload(cur, table, payload)
        if not data:
            return
        columns = list(data)
        cur.execute(
            f'INSERT INTO public."{table}" ({",".join(chr(34)+c+chr(34) for c in columns)}) VALUES ({",".join(["%s"]*len(columns))})',
            [data[column] for column in columns],
        )

    @classmethod
    def _upsert_available(cls, cur, table, payload, conflict_columns):
        data = cls._available_payload(cur, table, payload)
        if not data or any(column not in data for column in conflict_columns):
            return
        columns = list(data)
        updates = [column for column in columns if column not in conflict_columns]
        sql = (
            f'INSERT INTO public."{table}" ({",".join(chr(34)+c+chr(34) for c in columns)}) '
            f'VALUES ({",".join(["%s"]*len(columns))}) ON CONFLICT '
            f'({",".join(chr(34)+c+chr(34) for c in conflict_columns)}) DO UPDATE SET '
            + ",".join(f'{chr(34)+c+chr(34)}=EXCLUDED.{chr(34)+c+chr(34)}' for c in updates)
        )
        cur.execute(sql, [data[column] for column in columns])

    @classmethod
    def _update_or_insert_available(cls, cur, table, payload, key_columns):
        data = cls._available_payload(cur, table, payload)
        if not data or any(column not in data for column in key_columns):
            return
        update_columns = [column for column in data if column not in key_columns]
        where = " AND ".join(f'{chr(34)+column+chr(34)}=%s' for column in key_columns)
        if update_columns:
            cur.execute(
                f'UPDATE public."{table}" SET ' + ",".join(f'{chr(34)+column+chr(34)}=%s' for column in update_columns) + f' WHERE {where}',
                [data[column] for column in update_columns] + [data[column] for column in key_columns],
            )
            if cur.rowcount:
                return
        cls._insert_available(cur, table, data)

    def _record_release_failure(self, model_id, idempotency_key, operator, error):
        conn = self._connect(); conn.autocommit = False
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("new-product-release-domain",))
                repository = self._state(cur)
                model = repository.models.get(str(model_id or "")) or {}
                batch_id = f"RB-{uuid.uuid4().hex}"
                failed = {
                    "batch_id": batch_id, "model_id": str(model_id or ""),
                    "application_id": model.get("current_application_id") or "", "status": "failed",
                    "release_status": "failed", "idempotency_key": str(idempotency_key or ""),
                    "operator": str(operator or "system"), "formal_record_ids": [], "published_pending_ids": [],
                    "started_at": _utc_now(), "finished_at": _utc_now(), "error_summary": str(error),
                }
                repository.batches[batch_id] = failed
                repository._audit("model_release_failed", operator, model_id=model_id, batch_id=batch_id,
                                  reason=str(error))
                self._materialize_domain_projection(cur, repository)
                cur.execute("UPDATE public.product_release_domain_state SET state_json=%s,revision=revision+1,updated_at=now() WHERE singleton_id=1", (Json(repository.export_state()),))
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()

    def ensure_model(self, *args, **kwargs): return self._run("ensure_model", *args, **kwargs)
    def model(self, *args, **kwargs): return self._read("model", *args, **kwargs)
    def model_state_map(self): return self._read("model_state_map")
    def application(self, *args, **kwargs): return self._read("application", *args, **kwargs)
    def batch_by_idempotency(self, *args, **kwargs): return self._read("batch_by_idempotency", *args, **kwargs)
    def seed_formal_kb(self, *args, **kwargs): return self._run("seed_formal_kb", *args, **kwargs)
    def start_application(self, *args, **kwargs): return self._run("start_application", *args, **kwargs)
    def save_change(self, *args, **kwargs): return self._run("save_change", *args, materialize_change=True, **kwargs)
    def replace_pending(self, *args, **kwargs): return self._run("replace_pending", *args, **kwargs)
    def cancel_pending(self, *args, **kwargs): return self._run("cancel_pending", *args, **kwargs)
    def record_matrix_changes(self, *args, **kwargs): return self._run("record_matrix_changes", *args, **kwargs)
    def cancel_matrix_operation(self, *args, **kwargs): return self._run("cancel_matrix_operation", *args, **kwargs)
    def pending_chain(self, *args, **kwargs): return self._read("pending_chain", *args, **kwargs)
    def pending_records(self, *args, **kwargs):
        records = self._read("pending_records", *args, **kwargs)
        try:
            conn = self._connect()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                filters = args[0] if args and isinstance(args[0], dict) else kwargs.get("filters") or {}
                clauses = ["status = 'pending_release'"]
                params = []
                if filters.get("kb_id"):
                    clauses.append("question_wiki_id = %s")
                    params.append(filters["kb_id"])
                if filters.get("status"):
                    clauses[0] = "status = %s"
                    params = [filters["status"]] + params
                cur.execute("SELECT * FROM public.product_release_pending_modification WHERE " + " AND ".join(clauses) + " ORDER BY created_at DESC", params)
                existing_ids = {str(item.get("record_id") or "") for item in records}
                for row in cur.fetchall():
                    item = dict(row)
                    if str(item.get("record_id") or "") in existing_ids:
                        continue
                    item["record_scope"] = "pending"
                    item["before"] = item.pop("before_json", None)
                    item["after"] = item.pop("after_json", None)
                    records.append(_normalize_pending_modification_record(item))
            conn.close()
        except Exception as exc:
            raise RepositoryUnavailable(f"待上线修改账本读取失败: {exc}") from exc
        return [_normalize_pending_modification_record(row) for row in records]
    def preview_model(self, *args, **kwargs): return self._read("preview_model", *args, **kwargs)
    def release_model(self, model_id, *, idempotency_key, operator, preview_digest):
        try:
            return self._run("release_model", model_id, idempotency_key=idempotency_key,
                             operator=operator, preview_digest=preview_digest, materialize=True)
        except Exception as exc:
            self._record_release_failure(model_id, idempotency_key, operator, exc)
            raise
    def create_release(self, *, request_id, idempotency_key, model_id, kb_id, payload, preview_digest, preview_expires_at):
        return self.release_model(
            model_id,
            idempotency_key=idempotency_key,
            operator=str((payload or {}).get("requested_by") or (payload or {}).get("actor") or "system"),
            preview_digest=preview_digest,
        )
    def cancel_application(self, *args, **kwargs): return self._run("cancel_application", *args, **kwargs)
    def reapply(self, *args, **kwargs): return self._run("reapply", *args, **kwargs)
    def workspace(self):
        workspace = self._read("workspace")
        workspace["pending_modification_records"] = self.pending_records()
        return workspace
    def claim_outbox(self, *args, **kwargs): return self._run("claim_outbox", *args, **kwargs)
    def finish_outbox(self, *args, **kwargs): return self._run("finish_outbox", *args, **kwargs)
    def retry_outbox(self, *args, **kwargs): return self.claim_outbox(*args, **kwargs)
    def reconcile(self): return self._read("reconcile")


class ProductReleaseService:
    def __init__(self, repository=None, token_ttl_seconds=600, clock=None, token_secret=None, downstream_dispatcher=None):
        self._enabled = _bool_env("NEW_PRODUCT_RELEASE_ENABLED"); self.repository = repository or PostgresReleaseRepository(); self.token_ttl_seconds = int(token_ttl_seconds); self.clock = clock or time.time
        self.token_secret = str(token_secret or os.getenv("NEW_PRODUCT_RELEASE_TOKEN_SECRET") or os.getenv("KMATRIX_SECRET_KEY") or ""); self.downstream_dispatcher = downstream_dispatcher; self._catalog_provider = None; self._catalog_status_setter = None

    def set_catalog_hooks(self, pending_provider=None, status_setter=None, model_provider=None): self._catalog_provider = model_provider or pending_provider; self._catalog_status_setter = status_setter
    def set_downstream_dispatcher(self, dispatcher): self.downstream_dispatcher = dispatcher
    @property
    def enabled(self): return self._enabled
    def set_enabled(self, value): self._enabled = bool(value)

    def _catalog_rows(self):
        if not self._catalog_provider: return []
        try: return [dict(row) for row in (self._catalog_provider() or []) if isinstance(row, dict)]
        except Exception: return []

    def _catalog_row(self, model_id):
        model_id = str(model_id or "").strip(); return next((row for row in self._catalog_rows() if str(row.get("model_id") or row.get("model") or "").strip() == model_id), None)

    def pending_catalog_models(self): return [row for row in self._catalog_rows() if row.get("release_status") == "pending_release"]

    def _sync_catalog_status(self, model_id, status, *, transition_token=None):
        if not self._catalog_status_setter: return True
        return bool(self._catalog_status_setter(model_id, status, transition_token=transition_token))

    def _gate(self, require_reconciliation=True):
        gate = self.repository.gate(); reasons = []
        if not self._enabled: reasons.append("NEW_PRODUCT_RELEASE_ENABLED 未设置为 1")
        if not gate.get("db_available"): reasons.append("本机 PostgreSQL 不可用或发布表尚未迁移")
        if not gate.get("exit_switch"): reasons.append("数据库统一正式出口开关（exit switch）未开启")
        if not gate.get("migration_passed"): reasons.append("migration batch 未通过")
        if require_reconciliation and not gate.get("reconciliation_passed"): reasons.append("reconciliation 未通过")
        return self._enabled and not reasons, gate, reasons

    def capabilities(self):
        ready, gate, reasons = self._gate(); recovery_ready, _, recovery_reasons = self._gate(require_reconciliation=False)
        downstream_configured = bool(self.downstream_dispatcher and str(os.getenv("NEW_PRODUCT_RELEASE_DOWNSTREAM_URL") or "").strip())
        return {"ok": True, "enabled": ready, "status": "enabled" if ready else "disabled", "read_only": not ready, "block_reason": "；".join(reasons), "block_reasons": reasons, "recovery_enabled": recovery_ready, "recovery_block_reasons": recovery_reasons, "gates": {"capability_flag": self._enabled, "downstream_configured": downstream_configured, **gate}, "features": {"publish": ready, "cancel": ready, "reapply": ready, "preview": ready, "content_changes": ready, "outbox_retry": recovery_ready, "reconcile": recovery_ready}}

    def workspace_state(self):
        ready, gate, reasons = self._gate(); recovery_ready, _, recovery_reasons = self._gate(require_reconciliation=False)
        try: workspace = self.repository.workspace() if gate.get("db_available") else {"pending_requests": [], "outbox": []}
        except Exception as exc: workspace = {"pending_requests": [], "outbox": []}; reasons.append(f"工作区读取失败: {exc}")
        workspace.update({"ok": True, "enabled": ready, "read_only": not ready, "block_reason": "；".join(reasons), "recovery_enabled": recovery_ready, "recovery_block_reasons": recovery_reasons, "pending_models": self.pending_catalog_models()}); return workspace

    def register_model(self, model_id, *, status="pending_release", actor="system"):
        """Register a catalog model when the release domain is available.

        Catalog maintenance is also used before the release migration is
        installed.  In that state the release feature is already read-only,
        so its optional projection must not make the catalog save fail.
        The catalog's local release intent remains the source of truth until
        the release domain can be reconciled.
        """
        model_id = str(model_id or "").strip()
        try:
            gate = self.repository.gate()
        except Exception as exc:
            return {
                "model_id": model_id,
                "release_status": status,
                "persistence": "deferred",
                "reason": str(exc),
            }
        if not gate.get("db_available"):
            return {
                "model_id": model_id,
                "release_status": status,
                "persistence": "deferred",
                "reason": gate.get("error") or "发布域数据库尚未就绪",
            }
        return self.repository.ensure_model(model_id, status=status, actor=actor)
    def create_application(self, model_id, *, actor="system", reason=""):
        row = self.repository.start_application(model_id, actor=actor, reason=reason); self._sync_catalog_status(model_id, "pending_release", transition_token="new_application"); return {"ok": True, "request": row}

    def save_change(self, kb_id, payload):
        ready, _, reasons = self._gate()
        if not ready: return self._blocked("save_change", "；".join(reasons))
        try: return {"ok": True, **self.repository.save_change(kb_id, payload)}
        except ReleaseConflict as exc: return self._blocked("save_change", str(exc), 409, code=exc.code, details=exc.details)
        except ValueError as exc: return self._blocked("save_change", str(exc), 400)
        except Exception as exc: return self._blocked("save_change", f"数据库事务失败: {exc}", 503)

    def record_matrix_changes(self, changes, *, actor="system", source_module="机型矩阵管理", operation_id="", pending_model_ids=None):
        ready, _, reasons = self._gate()
        if not ready:
            return self._blocked("record_matrix_changes", "；".join(reasons))
        try:
            records = self.repository.record_matrix_changes(
                changes, actor=actor, source_module=source_module, operation_id=operation_id,
                pending_model_ids=pending_model_ids,
            )
            return {"ok": True, "records": records, "pending_count": len(records)}
        except Exception as exc:
            return self._blocked("record_matrix_changes", f"待上线修改记录写入失败: {exc}", 503)

    def compensate_matrix_operation(self, operation_id, *, actor="system", reason=""):
        ready, _, reasons = self._gate(require_reconciliation=False)
        if not ready:
            return self._blocked("compensate_matrix_operation", "；".join(reasons))
        try:
            return {"ok": True, "records": self.repository.cancel_matrix_operation(
                operation_id, actor=actor, reason=reason)}
        except Exception as exc:
            return self._blocked("compensate_matrix_operation", f"待上线账本补偿失败: {exc}", 503)

    def replace_pending(self, pending_id, payload):
        ready, _, reasons = self._gate()
        if not ready: return self._blocked("replace_pending", "；".join(reasons))
        try: return {"ok": True, "pending": self.repository.replace_pending(pending_id, payload.get("snapshot") or {}, actor=payload.get("actor") or "system", public_kb_confirmed=bool(payload.get("public_kb_confirmed")))}
        except ReleaseConflict as exc: return self._blocked("replace_pending", str(exc), 409, code=exc.code, details=exc.details)

    def cancel_pending(self, pending_id, payload):
        ready, _, reasons = self._gate()
        if not ready: return self._blocked("cancel_pending", "；".join(reasons))
        try: return {"ok": True, "pending": self.repository.cancel_pending(pending_id, actor=payload.get("actor") or "system", reason=payload.get("reason") or "")}
        except ReleaseConflict as exc: return self._blocked("cancel_pending", str(exc), 409, code=exc.code, details=exc.details)

    def preview_model(self, model_id, preview_token=None):
        ready, _, reasons = self._gate()
        if not ready: return self._blocked("preview", "；".join(reasons))
        model_id = str(model_id or "").strip(); catalog = self._catalog_row(model_id)
        if self._catalog_provider and (not catalog or catalog.get("release_status") != "pending_release"): return self._blocked("preview", "该型号不是待上线状态", 409)
        try:
            if not self.repository.model(model_id): self.repository.ensure_model(model_id, "pending_release", "system")
            preview = self.repository.preview_model(model_id); digest = preview["digest"]; token = preview_token or self._issue_token(model_id, digest)
            if preview_token and not self._verify_token(preview_token, model_id, digest): return self._blocked("preview", "preview_token 无效或已过期", 400)
            preview.update({"preview_token": token, "preview_digest": digest, "expires_at": int(self.clock()) + self.token_ttl_seconds}); return {"ok": True, "preview": preview}
        except ReleaseConflict as exc: return self._blocked("preview", str(exc), 409, code=exc.code, details=exc.details)
        except Exception as exc: return self._blocked("preview", f"预览失败: {exc}", 503)

    def publish(self, payload=None, model_id=None):
        payload = dict(payload or {}); ready, _, reasons = self._gate()
        if not ready: return self._blocked("publish", "；".join(reasons))
        model_id = str(model_id or payload.get("model_id") or payload.get("trigger_model") or "").strip(); token = str(payload.get("preview_token") or "")
        try:
            key = str(payload.get("idempotency_key") or payload.get("request_id") or "").strip()
            existing = self.repository.batch_by_idempotency(key) if key else None
            if existing:
                if existing.get("model_id") != model_id:
                    return self._blocked("publish", "幂等键已被其他型号使用", 409, code="idempotency_key_conflict")
                request = {"request_id": key, "model_id": model_id,
                           "status": "released", "release_status": "released", "batch_id": existing["batch_id"]}
                return {"ok": True, "idempotent": True, "request": request, "batch": existing,
                        "outbox": [], "message": "重复请求已返回原发布结果"}
            try:
                token_claims = self._token_claims(token)
            except Exception:
                return self._blocked("publish", "preview_token 无效", 400, code="invalid_preview_token")
            if token_claims.get("model_id") != model_id:
                return self._blocked("publish", "预览令牌摘要不匹配当前型号", 400, code="preview_token_mismatch")
            if int(token_claims.get("exp", 0)) < int(self.clock()):
                return self._blocked("publish", "预览令牌已过期，请重新预览", 400, code="preview_token_expired")
            catalog = self._catalog_row(model_id)
            if self._catalog_provider and (not catalog or catalog.get("release_status") != "pending_release"):
                return self._blocked("publish", "该型号不是待上线状态", 409)
            preview = self.repository.preview_model(model_id)
            if token_claims.get("digest") != preview["digest"]:
                return self._blocked("publish", "预览摘要不匹配当前型号内容，请重新预览", 409, code="preview_digest_mismatch")
            if not self._verify_token(token, model_id, preview["digest"]): return self._blocked("publish", "preview_token 无效或已过期", 400)
            if preview.get("public_impact_models") and not bool(payload.get("public_kb_confirmed")): return self._blocked("publish", "必须复核公共 KB 的实时在线影响范围", 400)
            key = key or f"release:{model_id}:{uuid.uuid4().hex}"; operator = str(payload.get("requested_by") or payload.get("actor") or "system")
            current_application = self.repository.model(model_id) or {}
            request_id = str(payload.get("request_id") or current_application.get("current_application_id") or "").strip()
            create_release = getattr(self.repository, "create_release", None)
            if create_release:
                batch = create_release(
                    request_id=request_id, idempotency_key=key, model_id=model_id,
                    kb_id=str(payload.get("target_kb") or payload.get("kb_id") or ""),
                    payload=payload, preview_digest=preview["digest"],
                    preview_expires_at=int(token_claims.get("exp", 0)),
                )
            else:
                batch = self.repository.release_model(model_id, idempotency_key=key,
                                                      operator=operator, preview_digest=preview["digest"])
            catalog_synced = self._sync_catalog_status(model_id, "released", transition_token=batch["batch_id"])
            # Keep the business event in the outbox until the explicit retry
            # action or configured worker acknowledges downstream delivery.
            outbox = [row for row in self.repository.workspace().get("outbox", [])
                      if row.get("batch_id") == batch["batch_id"]]
            request = {"request_id": request_id, "model_id": model_id, "status": "released", "release_status": "released", "batch_id": batch["batch_id"]}
            result = {"ok": True, "idempotent": False, "request": request, "batch": batch,
                      "outbox": outbox, "message": "型号上线事务已提交"}
            if not catalog_synced:
                result["warnings"] = ["型号已在数据库完成发布，但目录镜像回写失败，需要对账修复"]
            return result
        except ReleaseConflict as exc: return self._blocked("publish", str(exc), 409, code=exc.code, details=exc.details)
        except Exception as exc: return self._blocked("publish", f"数据库事务失败，型号保持待上线，发布保持未提交: {exc}", 503)

    def cancel(self, request_id, model_id=None, payload=None):
        payload = payload or {}; ready, _, reasons = self._gate()
        if not ready: return self._blocked("cancel", "；".join(reasons))
        try:
            application = self.repository.application(str(request_id or ""))
            if model_id and application and application.get("model_id") != str(model_id):
                return self._blocked("cancel", "申请不属于 URL 中的型号", 409, code="model_request_mismatch")
            application_id = str((application or {}).get("request_id") or request_id or "")
            row = self.repository.cancel_application(application_id, actor=payload.get("actor") or "system", reason=payload.get("reason") or "")
            if not row: return self._blocked("cancel", f"找不到请求 {request_id}", 404)
            row["status"] = "cancelled"
            self._sync_catalog_status(row["model_id"], "release_cancelled", transition_token="cancel_application"); return {"ok": True, "request": row}
        except ReleaseConflict as exc: return self._blocked("cancel", str(exc), 409, code=exc.code, details=exc.details)
        except Exception as exc: return self._blocked("cancel", f"数据库事务失败: {exc}", 503)

    def reapply(self, request_id, model_id=None, payload=None):
        payload = payload or {}; ready, _, reasons = self._gate()
        if not ready: return self._blocked("reapply", "；".join(reasons))
        try:
            application = self.repository.application(str(request_id or ""))
            if model_id and application and application.get("model_id") != str(model_id):
                return self._blocked("reapply", "申请不属于 URL 中的型号", 409, code="model_request_mismatch")
            application_id = str((application or {}).get("request_id") or request_id or "")
            row = self.repository.reapply(application_id, actor=payload.get("actor") or "system", reason=payload.get("reason") or "")
            if not row: return self._blocked("reapply", "请求不存在或尚未处于取消终态", 409)
            row["reapplied_from"] = str(request_id or application_id)
            row["pending_version"] = row.get("generation", 1)
            self._sync_catalog_status(row["model_id"], "pending_release", transition_token="new_application"); return {"ok": True, "request": row}
        except ReleaseConflict as exc: return self._blocked("reapply", str(exc), 409, code=exc.code, details=exc.details)
        except Exception as exc: return self._blocked("reapply", f"数据库事务失败: {exc}", 503)

    def dispatch_outbox(self, batch_id=""):
        claimed = self.repository.claim_outbox(str(batch_id or "")); results = []
        for event in claimed:
            try:
                if not self.downstream_dispatcher or not str(os.getenv("NEW_PRODUCT_RELEASE_DOWNSTREAM_URL") or "").strip():
                    # Local deployments have no external receiver. A local
                    # acknowledgement keeps the release transaction complete;
                    # a configured dispatcher still receives the real event.
                    results.append(self.repository.finish_outbox(
                        event.get("event_id"), success=True,
                        receipt={"mode": "local", "status": "accepted"},
                    ))
                    continue
                receipt = self.downstream_dispatcher(deepcopy(event)); results.append(self.repository.finish_outbox(event["event_id"], success=True, receipt=receipt or {}))
            except Exception as exc:
                event_id = event.get("event_id")
                if event_id:
                    results.append(self.repository.finish_outbox(event_id, success=False, error=str(exc)))
                else:
                    results.append({**event, "status": "failed", "last_error": str(exc)})
        return results

    def retry_outbox(self, batch_id):
        ready, _, reasons = self._gate(require_reconciliation=False)
        if not ready: return self._blocked("outbox_retry", "；".join(reasons))
        rows = self.dispatch_outbox(str(batch_id or "")); return {"ok": True, "outbox": rows} if rows else self._blocked("outbox_retry", "未找到可恢复的 outbox 任务", 404)

    def reconcile(self):
        ready, _, reasons = self._gate(require_reconciliation=False)
        if not ready: return self._blocked("reconcile", "；".join(reasons))
        try: return {"ok": True, **self.repository.reconcile()}
        except Exception as exc: return self._blocked("reconcile", f"数据库事务失败: {exc}", 503)

    def _issue_token(self, model_id, digest):
        body = {"model_id": model_id, "digest": digest, "exp": int(self.clock()) + self.token_ttl_seconds, "nonce": secrets.token_hex(8)}; encoded = base64.urlsafe_b64encode(_json(body).encode()).decode().rstrip("="); return encoded + "." + self._sign(encoded)

    def _verify_token(self, token, model_id, digest):
        try:
            body = self._token_claims(token); return body.get("model_id") == model_id and body.get("digest") == digest and int(body.get("exp", 0)) > int(self.clock())
        except Exception: return False

    def _token_claims(self, token):
        encoded, signature = str(token).split(".", 1)
        if not hmac.compare_digest(signature, self._sign(encoded)): raise ValueError("invalid preview token signature")
        return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode())

    def _sign(self, value):
        if not self.token_secret: raise RuntimeError("preview token signing secret is not configured")
        return hmac.new(self.token_secret.encode(), value.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _blocked(action, reason, status=403, *, code=None, details=None):
        return {"ok": False, "action": action, "status_code": status, "read_only": True, "code": code or action + "_blocked", "details": details or {}, "block_reason": reason, "message": reason}


def build_service(repository=None):
    return ProductReleaseService(repository=repository)
