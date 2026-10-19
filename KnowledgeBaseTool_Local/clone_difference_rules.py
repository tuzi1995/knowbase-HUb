"""Validated difference rules for matrix clone review batches."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


ALLOWED_DETECTION_METHODS = {"parameter_check", "manual_difference_ai"}

_FEATURE_ALIASES = (
    ("max_suction", "最大吸力", ("最大吸力", "吸力")),
    ("mop_washing_temperature", "洗布温度", ("洗布温度", "洗拖布温度", "拖布清洗温度")),
    ("hot_water_mopping", "拖地水温", ("拖地水温", "热力高温", "高温去渍", "热水拖地", "常温拖地")),
    ("mop_pressure", "拖地压力", ("拖地压力", "下压力")),
    ("spray_hole_count", "喷淋孔数", ("孔喷淋", "喷淋孔", "喷淋")),
    ("object_recognition_count", "物体识别数量", ("物体识别", "识别障碍物", "可识别障碍物")),
    ("body_height", "机身高度", ("机身高度", "整机高度", "超薄机身", "机身")),
    ("obstacle_crossing_height", "越障高度", ("越障高度", "越障", "门槛")),
    ("battery_capacity", "电池容量", ("电池容量", "电池")),
    ("water_tank_capacity", "水箱容量", ("水箱容量", "水箱")),
    ("dust_box_capacity", "尘盒容量", ("尘盒容量", "尘盒")),
    ("dust_bag_capacity", "尘袋容量", ("尘袋容量", "尘袋")),
    ("cleaning_solution_capacity", "清洁液盒容量", ("清洁液盒容量", "清洁液盒")),
    ("roller_cover", "滚筒罩", ("滚筒罩",)),
    ("voice_control", "语音控制", ("语音控制", "语控")),
    ("power_cord", "电源线", ("电源线", "插座")),
    ("dirt_detection", "脏污检测", ("脏污检测",)),
    ("disposable_filter", "一次性滤网", ("一次性滤网",)),
)

_SEMANTIC_TOKEN_GROUPS = (
    ("检测", "识别", "感知", "监测", "指示", "显示"),
    ("脏污", "污渍", "污垢"),
)
_FEATURE_ACTION_TOKENS = _SEMANTIC_TOKEN_GROUPS[0]
_FEATURE_STATE_SUFFIXES = ("程度", "状态", "等级", "传感器")
_FEATURE_NAME_SUFFIXES = ("功能", "系统", "能力")
_FEATURE_TERM_LIMIT = 80

_VALUE_PATTERN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?\+?)\s*(?P<unit>pa|kpa|mm|cm|mah|ml|l|kg|g|rpm|db|℃|°c|n|孔|种)?",
    re.IGNORECASE,
)

# Dimensions must stay together. Extracting each number separately turns
# `265mm*232mm*1100mm` into the misleading rule `265mm -> 232mm`.
_DIMENSION_PATTERN = re.compile(
    r"(?P<value>(?:\d+(?:\.\d+)?\s*(?:mm|cm)?\s*[x×*]\s*){1,2}"
    r"\d+(?:\.\d+)?\s*(?:mm|cm))",
    re.IGNORECASE,
)

_MODEL_CLAUSE_PATTERN = re.compile(
    r"(?:^|\s)(?P<model>[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff ._-]*?)\s*[：:]"
)

_FEATURE_ACTION_PATTERN = re.compile(
    r"(?P<action>不再支持|取消|移除|去掉|删除|新增|增加|添加|恢复)\s*"
    r"(?P<feature>[A-Za-z0-9\u4e00-\u9fff _-]{2,40}?)(?=$|[，,。；;])"
)
_REMOVED_FEATURE_ACTIONS = {"不再支持", "取消", "移除", "去掉", "删除"}

_FEATURE_UNITS = {
    "max_suction": {"pa", "kpa"},
    "mop_washing_temperature": {"℃", "°c"},
    "mop_pressure": {"n"},
    "spray_hole_count": {"孔"},
    "object_recognition_count": {"种"},
    "body_height": {"mm", "cm"},
    "obstacle_crossing_height": {"mm", "cm"},
    "battery_capacity": {"mah"},
    "water_tank_capacity": {"ml", "l"},
    "dust_box_capacity": {"ml", "l"},
    "dust_bag_capacity": {"ml", "l"},
    "cleaning_solution_capacity": {"ml", "l"},
}


def _semantic_term_variants(values: list[str] | tuple[str, ...]) -> list[str]:
    terms: list[str] = []

    def add(value: str) -> None:
        normalized = re.sub(r"\s+", "", str(value or "")).strip()
        if len(normalized) >= 2 and normalized not in terms and len(terms) < _FEATURE_TERM_LIMIT:
            terms.append(normalized)

    for value in values:
        add(value)
    for group in _SEMANTIC_TOKEN_GROUPS:
        for term in list(terms):
            for token in group:
                if token not in term:
                    continue
                for replacement in group:
                    add(term.replace(token, replacement))
    for term in list(terms):
        base = next((term[:-len(suffix)] for suffix in _FEATURE_NAME_SUFFIXES if term.endswith(suffix)), term)
        for action in _FEATURE_ACTION_TOKENS:
            if base.endswith(action) and len(base) > len(action) + 1:
                add(action + base[:-len(action)])
            elif base.startswith(action) and len(base) > len(action) + 1:
                add(base[len(action):] + action)
    return terms


def _feature_entity_roots(terms: list[str]) -> list[str]:
    roots = []
    for term in terms:
        base = next((term[:-len(suffix)] for suffix in _FEATURE_NAME_SUFFIXES if term.endswith(suffix)), term)
        for action in _FEATURE_ACTION_TOKENS:
            if base.endswith(action):
                base = base[:-len(action)]
                break
            if base.startswith(action):
                base = base[len(action):]
                break
        if len(base) >= 2 and base not in roots:
            roots.append(base)
    return roots


def difference_feature_terms(
    feature_id: str,
    feature_name: str = "",
    feature_description: str = "",
) -> list[str]:
    """Derive shared semantic terms from a feature name and its catalog description."""
    normalized_id = str(feature_id or "").strip()
    normalized_name = str(feature_name or "").strip()
    seeds = [normalized_name] if normalized_name else []
    for known_id, known_name, aliases in _FEATURE_ALIASES:
        if normalized_id == known_id or normalized_name == known_name:
            seeds.extend([known_name, *aliases])
            break
    terms = _semantic_term_variants(seeds)
    description = re.sub(r"\s+", "", str(feature_description or ""))
    description_terms = []
    for root in _feature_entity_roots(terms):
        for suffix in _FEATURE_STATE_SUFFIXES:
            candidate = root + suffix
            if candidate in description:
                description_terms.append(candidate)
    return _semantic_term_variants([*terms, *description_terms])


def normalize_detection_methods(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    methods: list[str] = []
    for raw in value:
        method = str(raw or "").strip()
        if method in ALLOWED_DETECTION_METHODS and method not in methods:
            methods.append(method)
    return methods


def _feature_for_text(text: str) -> tuple[str, str, list[str]]:
    lowered = text.lower()
    for feature_id, feature_name, aliases in _FEATURE_ALIASES:
        terms = difference_feature_terms(feature_id, feature_name)
        if any(term.lower() in lowered for term in terms):
            return feature_id, feature_name, terms
    return "manual_difference", "用户输入差异", []


def _explicit_feature_for_line(line: str, target_model: str) -> tuple[str, str, list[str]]:
    match = re.match(r"^\s*(?:\d+\s*[.、．)]\s*)?(?P<label>[^：:]{1,80})\s*[：:]", line)
    label = str(match.group("label") if match else "").strip()
    if label and _normalized_model_name(target_model) not in _normalized_model_name(label):
        # The field label is the strongest signal. Looking across the whole
        # line first can mistake context such as "污水箱" or "电池类型"
        # for a different canonical feature.
        feature_id, feature_name, aliases = _feature_for_text(label)
        # "电池" is an alias for capacity in free-form model clauses, but a
        # labelled field such as "电池类型" is a distinct user-defined field.
        if feature_id == "battery_capacity" and "容量" not in label:
            feature_id = "manual_difference"
        if feature_id != "manual_difference":
            return feature_id, feature_name, aliases
        manual_feature_id = "manual_feature_" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:12]
        return manual_feature_id, label, [label]

    feature_id, feature_name, aliases = _feature_for_text(line)
    if feature_id != "manual_difference":
        return feature_id, feature_name, aliases
    if not label or _normalized_model_name(target_model) in _normalized_model_name(label):
        return feature_id, feature_name, aliases
    manual_feature_id = "manual_feature_" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:12]
    return manual_feature_id, label, [label]


def _explicit_context_for_line(line: str, feature_name: str) -> str:
    """Extract an explicit operating context from a labelled field.

    Context is deliberately limited to explicit mode/scene words. Inferring a
    context from arbitrary prose would recreate the cross-pairing problem this
    parser is intended to prevent.
    """
    match = re.match(r"^\s*(?:\d+\s*[.、．)]\s*)?(?P<label>[^：:]{1,80})\s*[：:]", line)
    label = str(match.group("label") if match else "")
    if not label:
        return ""
    contexts = (
        "自动模式", "强力模式", "轻拖模式", "吸水模式", "静音烘干", "极速烘干",
        "自动", "强力", "轻拖", "吸水", "静音",
    )
    found = []
    for context in sorted(contexts, key=len, reverse=True):
        if context in label and not any(context in existing for existing in found):
            found.append(context)
    return "、".join(dict.fromkeys(found))


def _text_mentions_feature(text: str, aliases: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in _semantic_term_variants(aliases))


def _normalized_value(value: str, unit: str) -> str:
    return f"{value}{unit}".replace(" ", "").lower()


def _normalized_model_name(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _model_clauses(segment: str) -> list[tuple[str, str]]:
    matches = list(_MODEL_CLAUSE_PATTERN.finditer(segment))
    clauses = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(segment)
        clauses.append((match.group("model").strip(), segment[match.end():end].strip()))
    return clauses


def _feature_value(feature_id: str, text: str) -> tuple[str, str]:
    if feature_id == "hot_water_mopping":
        temperature = re.search(r"\d+(?:\.\d+)?\s*(?:℃|°c)", text, re.IGNORECASE)
        if temperature:
            value = re.sub(r"\s+", "", temperature.group(0))
            if "热力高温" in text:
                value += "热力高温"
            return value, value.lower()
        for phrase in ("常温拖地", "热水拖地", "热力高温"):
            if phrase in text:
                return phrase, phrase.lower()
        return "", ""

    expected_units = _FEATURE_UNITS.get(feature_id)
    if not expected_units:
        return "", ""
    for match in _VALUE_PATTERN.finditer(text):
        unit = str(match.group("unit") or "").strip()
        if unit.lower() in expected_units:
            value = f"{match.group('value')}{unit}"
            return value, _normalized_value(match.group("value"), unit)
    return "", ""


def _value_entries(text: str) -> list[tuple[str, str, int]]:
    """Return numeric values while treating compound dimensions as one value."""
    entries: list[tuple[str, str, int]] = []
    dimension_spans: list[tuple[int, int]] = []
    for match in _DIMENSION_PATTERN.finditer(text):
        raw_value = re.sub(r"\s+", "", match.group("value"))
        entries.append((raw_value, raw_value.lower(), match.start()))
        dimension_spans.append((match.start(), match.end()))
    for match in _VALUE_PATTERN.finditer(text):
        if not match.group("unit"):
            continue
        if any(start < match.end() and match.start() < end for start, end in dimension_spans):
            continue
        raw_value = f"{match.group('value')}{match.group('unit')}"
        entries.append((raw_value, _normalized_value(match.group("value"), match.group("unit")), match.start()))
    return sorted(entries, key=lambda entry: entry[2])


def _model_clause_value(clause: str, model_name: str) -> str:
    model = str(model_name or '').strip()
    if not model:
        return ''
    pattern = re.escape(model).replace(r'\ ', r'\s*')
    match = re.search(pattern, clause, re.IGNORECASE)
    if not match:
        return ''
    return clause[match.end():].strip(' \t：:，,。；;-').removeprefix('为').removeprefix('是').strip()


def _strip_feature_prefix(value: str, feature_name: str, aliases: list[str]) -> str:
    result = str(value or '').strip()
    for term in sorted({feature_name, *aliases}, key=len, reverse=True):
        if result.lower().startswith(str(term).lower()):
            return result[len(term):].strip(' \t：:，,。；;-').removeprefix('为').removeprefix('是').strip()
    return result


def _paired_model_clause_rules(
    line: str,
    target_model: str,
    source_model: str,
) -> list[dict[str, Any]]:
    """Parse one feature whose target/source clauses are labelled by model name."""
    target = str(target_model or '').strip()
    source = str(source_model or '').strip()
    if not target or not source or _normalized_model_name(target) == _normalized_model_name(source):
        return []

    matches = []
    for role, model in (('target', target), ('source', source)):
        pattern = re.escape(model).replace(r'\ ', r'\s*')
        match = re.search(pattern, line, re.IGNORECASE)
        if not match:
            return []
        matches.append((match.start(), match.end(), role))
    matches.sort()

    clauses: dict[str, str] = {}
    for index, (_, end, role) in enumerate(matches):
        clause_end = matches[index + 1][0] if index + 1 < len(matches) else len(line)
        clauses[role] = line[end:clause_end].strip(' \t：:，,。；;-')

    feature_id, feature_name, aliases = _explicit_feature_for_line(line, target_model)
    # A model summary such as `P20 有 4 种模式、4000mAh` contains several
    # unrelated values.  With no field label there is no defensible pairing;
    # leave it for the warning/AI path instead of manufacturing one rule.
    if feature_id == "manual_difference" and not re.match(
        r"^\s*(?:\d+\s*[.、．)]\s*)?[^：:]{1,80}\s*[：:]", line
    ):
        return []
    source_value = _strip_feature_prefix(clauses.get('source', ''), feature_name, aliases)
    target_value = _strip_feature_prefix(clauses.get('target', ''), feature_name, aliases)
    if not source_value or not target_value:
        return []

    # Simple scalar fields are more useful as canonical values. Compound
    # clauses (for example two obstacle heights) stay intact as user evidence.
    if feature_id in {'max_suction', 'battery_capacity', 'mop_washing_temperature'}:
        source_scalar, source_normalized = _feature_value(feature_id, source_value)
        target_scalar, target_normalized = _feature_value(feature_id, target_value)
        if source_scalar and target_scalar:
            source_value, target_value = source_scalar, target_scalar
        else:
            source_normalized = re.sub(r'\s+', '', source_value).lower()
            target_normalized = re.sub(r'\s+', '', target_value).lower()
    else:
        source_normalized = re.sub(r'\s+', '', source_value).lower()
        target_normalized = re.sub(r'\s+', '', target_value).lower()
    if source_normalized == target_normalized:
        return []
    return [_difference_rule(
        target_model=target_model,
        feature_id=feature_id,
        feature_name=feature_name,
        aliases=aliases,
        source_value=source_value,
        source_normalized=source_normalized,
        target_value=target_value,
        target_normalized=target_normalized,
        evidence_quote=line.strip(),
        context=_explicit_context_for_line(line, feature_name),
    )]


def _semicolon_model_pair_rules(
    line: str,
    target_model: str,
    source_model: str = '',
) -> list[dict[str, Any]]:
    """Parse `target value; source value` lines without requiring model colons."""
    target = str(target_model or "").strip()
    clauses = [part.strip() for part in re.split(r"[；;]", line) if part.strip()]
    if not target or len(clauses) < 2:
        return []
    target_index = next(
        (index for index, clause in enumerate(clauses)
         if _normalized_model_name(target) in _normalized_model_name(clause)),
        None,
    )
    if target_index is None:
        return []
    target_entries = _value_entries(clauses[target_index])
    source_clause = next((
        clause for index, clause in enumerate(clauses)
        if index != target_index
        and (
            not source_model
            or _normalized_model_name(source_model) in _normalized_model_name(clause)
        )
    ), '')
    source_entries = _value_entries(source_clause)
    has_explicit_label = bool(re.match(
        r"^\s*(?:\d+\s*[.、．)]\s*)?[^：:]{1,80}\s*[：:]", line
    ))
    if not has_explicit_label and (len(target_entries) > 1 or len(source_entries) > 1):
        return []
    # A model-labelled clause should describe one feature. If both sides have
    # multiple unrelated values, leave it to the labelled-clause parser rather
    # than guessing a cross-product of values.
    feature_id, feature_name, aliases = _explicit_feature_for_line(line, target_model)
    if feature_id == "manual_difference" and not has_explicit_label:
        return []
    if len(target_entries) == 1 and len(source_entries) == 1:
        source_value, source_normalized, _ = source_entries[0]
        target_value, target_normalized, _ = target_entries[0]
    elif source_model:
        source_value = _model_clause_value(source_clause, source_model)
        target_value = _model_clause_value(clauses[target_index], target_model)
        source_normalized = re.sub(r'\s+', '', source_value).lower()
        target_normalized = re.sub(r'\s+', '', target_value).lower()
        if not source_value or not target_value:
            return []
    else:
        return []
    if source_normalized == target_normalized:
        return []
    return [_difference_rule(
        target_model=target_model,
        feature_id=feature_id,
        feature_name=feature_name,
        aliases=aliases,
        source_value=source_value,
        source_normalized=source_normalized,
        target_value=target_value,
        target_normalized=target_normalized,
        evidence_quote=line.strip(),
        context=_explicit_context_for_line(line, feature_name),
    )]


def _canonical_action_feature(value: str) -> tuple[str, str, list[str]]:
    feature_name = re.sub(r"功能$", "", str(value or "").strip()).strip()
    for feature_id, known_name, aliases in _FEATURE_ALIASES:
        terms = difference_feature_terms(feature_id, known_name)
        if feature_name in terms:
            return feature_id, known_name, terms
    feature_id = "manual_feature_" + hashlib.sha256(feature_name.encode("utf-8")).hexdigest()[:12]
    return feature_id, feature_name, [feature_name]


def _feature_action_rules(segment: str, target_model: str) -> list[dict[str, Any]]:
    normalized_target = _normalized_model_name(target_model)
    if normalized_target and normalized_target not in _normalized_model_name(segment):
        return []
    rules = []
    for match in _FEATURE_ACTION_PATTERN.finditer(segment):
        feature_id, feature_name, aliases = _canonical_action_feature(match.group("feature"))
        if not feature_name:
            continue
        removed = match.group("action") in _REMOVED_FEATURE_ACTIONS
        source_value, target_value = ("支持", "不支持") if removed else ("不支持", "支持")
        rules.append(_difference_rule(
            target_model=target_model,
            feature_id=feature_id,
            feature_name=feature_name,
            aliases=aliases,
            source_value=source_value,
            source_normalized=source_value,
            target_value=target_value,
            target_normalized=target_value,
            evidence_quote=segment,
            context=_explicit_context_for_line(segment, feature_name),
        ))
    return rules


def _paired_boolean_feature_rules(line: str, target_model: str) -> list[dict[str, Any]]:
    target = str(target_model or "").strip()
    target_start = line.lower().find(target.lower()) if target else -1
    if target_start < 0:
        return []
    clause_start = target_start + len(target)
    clause_end_match = re.search(r"[；;。]", line[clause_start:])
    clause_end = clause_start + clause_end_match.start() if clause_end_match else len(line)
    target_clause = line[clause_start:clause_end]
    other_text = line[:target_start] + line[clause_end:]
    positive = re.search(
        r"(?<!不)支持\s*(?P<feature>[A-Za-z0-9\u4e00-\u9fff _-]{2,40}?)(?=$|[，,。；;])",
        target_clause,
    )
    negative = re.search(
        r"不支持\s*(?P<feature>[A-Za-z0-9\u4e00-\u9fff _-]{2,40}?)(?=$|[，,。；;])",
        target_clause,
    )
    if positive and "不支持" in other_text:
        source_value, target_value = "不支持", "支持"
        feature_text = positive.group("feature")
    elif negative and re.search(r"(?<!不)支持", other_text):
        source_value, target_value = "支持", "不支持"
        feature_text = negative.group("feature")
    else:
        return []
    feature_id, feature_name, aliases = _canonical_action_feature(feature_text)
    return [_difference_rule(
        target_model=target_model,
        feature_id=feature_id,
        feature_name=feature_name,
        aliases=aliases,
        source_value=source_value,
        source_normalized=source_value,
        target_value=target_value,
        target_normalized=target_value,
        evidence_quote=line.strip(),
        context=_explicit_context_for_line(line, feature_name),
    )]


def _difference_rule(
    *,
    target_model: str,
    feature_id: str,
    feature_name: str,
    aliases: list[str],
    source_value: str,
    source_normalized: str,
    target_value: str,
    target_normalized: str,
    evidence_quote: str,
    context: str = "",
) -> dict[str, Any]:
    rule = {
        "target_model": str(target_model or "").strip(),
        "feature_id": feature_id,
        "feature_name": feature_name,
        "context": str(context or "").strip(),
        "source_value": source_value,
        "target_value": target_value,
        "source_normalized_value": source_normalized,
        "target_normalized_value": target_normalized,
        "difference_type": "value_changed",
        "source_search_terms": list(dict.fromkeys([source_value, source_normalized, feature_name, *aliases])),
        "target_search_terms": list(dict.fromkeys([target_value, target_normalized, feature_name, *aliases])),
        "kb_intents": [f"{feature_name}是多少", feature_name],
        "confidence": 1.0,
        "evidence_sources": ["user_input"],
        "evidence_quote": evidence_quote,
        "source_quality_status": "user_asserted",
        "target_quality_status": "user_asserted",
        "status": "needs_confirmation",
        "parse_engine": "deterministic_model_clause_v2",
    }
    rule["rule_key"] = _rule_id_payload(rule)
    return rule


def _rule_id_payload(rule: dict[str, Any]) -> str:
    raw = "|".join(
        str(rule.get(key) or "").strip().lower()
        for key in ("target_model", "feature_id", "context", "source_value", "target_value")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def parse_manual_difference_text(
    text: str,
    *,
    target_model: str = "",
    source_model: str = "",
) -> list[dict[str, Any]]:
    """Parse explicit old/new numeric statements without inventing facts."""
    original = str(text or "").strip()
    if not original:
        return []
    segments = [part.strip() for part in re.split(r"[；;\n]+", original) if part.strip()]
    rules: list[dict[str, Any]] = []
    paired_model_lines: list[str] = []
    for line in (part.strip() for part in original.splitlines() if part.strip()):
        paired_model_rules = _paired_model_clause_rules(line, target_model, source_model)
        if paired_model_rules:
            rules.extend(paired_model_rules)
            paired_model_lines.append(line)
            continue
        semicolon_rules = _semicolon_model_pair_rules(line, target_model, source_model)
        if semicolon_rules:
            rules.extend(semicolon_rules)
            continue
        rules.extend(_paired_boolean_feature_rules(line, target_model))
    for segment in segments:
        rules.extend(_feature_action_rules(segment, target_model))
        if any(segment in line for line in paired_model_lines):
            continue
        clauses = _model_clauses(segment)
        normalized_target_model = _normalized_model_name(target_model)
        target_clause = next(
            (clause for model, clause in clauses if _normalized_model_name(model) == normalized_target_model),
            "",
        )
        source_clause = next(
            (clause for model, clause in clauses if _normalized_model_name(model) != normalized_target_model),
            "",
        )
        if target_clause and source_clause:
            for feature_id, feature_name, aliases in _FEATURE_ALIASES:
                if not (
                    _text_mentions_feature(target_clause, aliases)
                    and _text_mentions_feature(source_clause, aliases)
                ):
                    continue
                source_value, source_normalized = _feature_value(feature_id, source_clause)
                target_value, target_normalized = _feature_value(feature_id, target_clause)
                if not source_value or not target_value or source_normalized == target_normalized:
                    continue
                rules.append(_difference_rule(
                    target_model=target_model,
                    feature_id=feature_id,
                    feature_name=feature_name,
                    aliases=list(aliases),
                    source_value=source_value,
                    source_normalized=source_normalized,
                    target_value=target_value,
                    target_normalized=target_normalized,
                    evidence_quote=segment,
                    context=_explicit_context_for_line(segment, feature_name),
                ))
            continue

        values = _value_entries(segment)
        if len(values) < 2:
            continue
        # A model introduction often contains several unrelated values (for
        # example cleaning-mode count, drying time, and battery capacity).
        # Without an explicit field label there is no defensible way to pair
        # those values, so leave the segment for the user/AI instead of
        # manufacturing a rule that later appears as a source conflict.
        has_explicit_label = bool(re.match(
            r"^\s*(?:\d+\s*[.、．)]\s*)?[^：:]{1,80}\s*[：:]", segment
        ))
        has_model_mention = any(
            _normalized_model_name(model) in _normalized_model_name(segment)
            for model in (target_model, source_model)
            if str(model or "").strip()
        )
        # A model clause with several values is not an old/new pair. Paired
        # full lines were handled above; unpaired model summaries stay for
        # review instead of crossing values in the fallback parser.
        if has_model_mention and not has_explicit_label:
            continue
        feature_id, feature_name, aliases = _feature_for_text(segment)
        source_entry, target_entry = values[0], values[1]
        target_start = segment.lower().find(str(target_model or "").strip().lower())
        if target_start >= 0:
            target_candidates = [entry for entry in values if entry[2] >= target_start + len(str(target_model or "").strip())]
            if target_candidates:
                target_entry = target_candidates[0]
                source_entry = next((entry for entry in values if entry is not target_entry), source_entry)
        source_value, source_normalized = source_entry[:2]
        target_value, target_normalized = target_entry[:2]
        if source_normalized == target_normalized:
            continue
        rules.append(_difference_rule(
            target_model=target_model,
            feature_id=feature_id,
            feature_name=feature_name,
            aliases=aliases,
            source_value=source_value,
            source_normalized=source_normalized,
            target_value=target_value,
            target_normalized=target_normalized,
            evidence_quote=segment,
            context=_explicit_context_for_line(segment, feature_name),
        ))
    return rules


def parse_manual_difference_text_with_warnings(
    text: str,
    *,
    target_model: str = "",
    source_model: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Parse rules and retain explicit evidence for skipped ambiguous text."""
    original = str(text or "").strip()
    rules = parse_manual_difference_text(
        original,
        target_model=target_model,
        source_model=source_model,
    )
    warnings: list[dict[str, str]] = []
    parsed_evidence = {str(rule.get("evidence_quote") or "").strip() for rule in rules}
    paired_model_lines = [
        line.strip()
        for line in original.splitlines()
        if line.strip() and _paired_model_clause_rules(line.strip(), target_model, source_model)
    ]
    for segment in (part.strip() for part in re.split(r"[；;\n]+", original) if part.strip()):
        if segment in parsed_evidence or any(segment in line for line in paired_model_lines):
            continue
        values = _value_entries(segment)
        if len(values) < 2:
            continue
        has_label = bool(re.match(r"^\s*(?:\d+\s*[.、．)]\s*)?[^：:]{1,80}\s*[：:]", segment))
        mentions_model = any(
            _normalized_model_name(model) in _normalized_model_name(segment)
            for model in (target_model, source_model)
            if str(model or "").strip()
        )
        if mentions_model and not has_label:
            warnings.append({
                "code": "ambiguous_model_summary",
                "message": "检测到多个机型数值，但缺少明确字段标签，已跳过自动配对。",
                "evidence": segment[:240],
            })
        elif not has_label and len(values) > 2:
            warnings.append({
                "code": "ambiguous_value_group",
                "message": "同一段文字包含多个数值且没有字段标签，已跳过自动配对。",
                "evidence": segment[:240],
            })
    return rules, warnings


def validate_ai_difference_rules(
    raw: Any,
    *,
    source_text: str,
    target_model: str = "",
) -> list[dict[str, Any]]:
    """Accept only AI rules whose old/new facts are present in the user's text."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                return []
            try:
                raw = json.loads(match.group(0))
            except json.JSONDecodeError:
                return []
    candidates = raw.get("rules") if isinstance(raw, dict) else raw
    if not isinstance(candidates, list):
        return []
    original = str(source_text or "")
    validated: list[dict[str, Any]] = []
    for candidate in candidates[:30]:
        if not isinstance(candidate, dict):
            continue
        feature_id = str(candidate.get("feature_id") or "").strip()
        feature_name = str(candidate.get("feature_name") or "").strip()
        source_value = str(candidate.get("source_value") or "").strip()
        target_value = str(candidate.get("target_value") or "").strip()
        evidence_quote = str(candidate.get("evidence_quote") or "").strip()
        if not feature_id or not feature_name or not source_value or not target_value:
            continue
        if _normalized_value(source_value, "") == _normalized_value(target_value, ""):
            continue
        if source_value not in original or target_value not in original:
            continue
        if evidence_quote and evidence_quote not in original:
            continue
        rule = {
            "target_model": str(target_model or candidate.get("target_model") or "").strip(),
            "feature_id": feature_id,
            "feature_name": feature_name,
            "context": str(candidate.get("context") or "").strip(),
            "source_value": source_value,
            "target_value": target_value,
            "source_normalized_value": str(candidate.get("source_normalized_value") or source_value).lower(),
            "target_normalized_value": str(candidate.get("target_normalized_value") or target_value).lower(),
            "difference_type": str(candidate.get("difference_type") or "value_changed"),
            "source_search_terms": [str(item).strip() for item in candidate.get("source_search_terms") or [] if str(item).strip()],
            "target_search_terms": [str(item).strip() for item in candidate.get("target_search_terms") or [] if str(item).strip()],
            "kb_intents": [str(item).strip() for item in candidate.get("kb_intents") or [] if str(item).strip()],
            "confidence": max(0.0, min(float(candidate.get("confidence") or 0.0), 1.0)),
            "evidence_sources": ["user_input", "configured_ai"],
            "evidence_quote": evidence_quote or original,
            "source_quality_status": "user_asserted",
            "target_quality_status": "user_asserted",
            "status": "needs_confirmation",
            "parse_engine": "configured_ai",
        }
        rule["rule_key"] = _rule_id_payload(rule)
        validated.append(rule)
    return validated


def merge_difference_rules(*rule_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge equivalent rules without confusing ambiguity with source conflict.

    Multiple assertions from the same user input are ambiguous, but they are
    not an independent-source conflict. ``source_conflict`` is reserved for
    disagreements involving the parameter catalog (the independently sourced
    evidence). This keeps the review gate explainable and lets the reviewer
    resolve same-source ambiguity explicitly.
    """
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    feature_targets: dict[tuple[str, str, str], set[tuple[str, str]]] = {}
    feature_sources: dict[tuple[str, str, str], set[str]] = {}
    for group in rule_groups:
        for raw in group or []:
            rule = dict(raw)
            feature_key = (
                str(rule.get("target_model") or ""),
                str(rule.get("feature_id") or ""),
                str(rule.get("context") or "").strip(),
            )
            values = (str(rule.get("source_value") or ""), str(rule.get("target_value") or ""))
            feature_targets.setdefault(feature_key, set()).add(values)
            feature_sources.setdefault(feature_key, set()).update(rule.get("evidence_sources") or [])
            exact_key = (feature_key[0], str(rule.get("rule_key") or _rule_id_payload(rule)))
            if exact_key not in merged:
                merged[exact_key] = rule
                continue
            current = merged[exact_key]
            sources = list(current.get("evidence_sources") or [])
            for source in rule.get("evidence_sources") or []:
                if source not in sources:
                    sources.append(source)
            current["evidence_sources"] = sources
            current["confidence"] = max(float(current.get("confidence") or 0), float(rule.get("confidence") or 0))
    for rule in merged.values():
        feature_key = (
            str(rule.get("target_model") or ""),
            str(rule.get("feature_id") or ""),
            str(rule.get("context") or "").strip(),
        )
        values = feature_targets.get(feature_key) or set()
        sources = feature_sources.get(feature_key) or set()
        if len(values) > 1 and "parameter_check" in sources:
            rule["status"] = "source_conflict"
            rule["difference_type"] = "source_conflict"
        elif len(values) > 1:
            rule["status"] = "needs_confirmation"
            rule["difference_type"] = "value_changed"
    return list(merged.values())
