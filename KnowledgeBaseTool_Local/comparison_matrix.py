"""Product image ledger. KB writes go through the existing unified update route.

The ledger uses the platform SQLite database; KB content remains in its configured
main database. A durable per-KB intent bridges the two stores and permits recovery.
"""
import csv
import hashlib
import io
import itertools
import json
import re
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from flask import jsonify, request, Response
from flask_login import current_user
from sqlalchemy import update

TAG = '产品对比图'


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def unpack(value, default=None):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return value if value is not None else default


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def pair_key(category, models):
    return digest([category, sorted(models)])


def image_list(value):
    result = unpack(value, None)
    if not isinstance(result, list) or any(not isinstance(v, str) or not v.strip() or v.strip().lower() == 'null' for v in result):
        raise ValueError('image_urls 必须是无空元素的 JSON 链接数组，请先在知识库修复格式')
    # The unified write route trims URL values. Refuse noncanonical arrays rather
    # than silently modifying unselected elements when replacing one position.
    if any(v != v.strip() for v in result):
        raise ValueError('图片数组包含首尾空白，请先在知识库修复格式')
    return result


def define_models(db):
    class ComparisonBatch(db.Model):
        __tablename__ = 'comparison_image_batch'
        id = db.Column(db.String(36), primary_key=True)
        name = db.Column(db.Text, nullable=False)
        note = db.Column(db.Text, default='')
        actor = db.Column(db.Text, nullable=False)
        created_at = db.Column(db.Text, nullable=False)

    class ComparisonAsset(db.Model):
        __tablename__ = 'comparison_image_asset'
        id = db.Column(db.String(36), primary_key=True)
        url = db.Column(db.Text, nullable=False, unique=True)
        link_id = db.Column(db.Text)
        batch_id = db.Column(db.String(36))
        category = db.Column(db.Text, default='')
        models_json = db.Column(db.Text, default='[]')
        confirmed_by = db.Column(db.Text, default='')
        confirmed_at = db.Column(db.Text)
        historical = db.Column(db.Boolean, default=False)
        created_at = db.Column(db.Text, nullable=False)

    class ComparisonCell(db.Model):
        __tablename__ = 'comparison_image_cell'
        id = db.Column(db.String(64), primary_key=True)
        category = db.Column(db.Text, nullable=False)
        pair_json = db.Column(db.Text, nullable=False)
        active_asset_id = db.Column(db.String(36))
        latest_decision_id = db.Column(db.String(36))

    class ComparisonDecision(db.Model):
        __tablename__ = 'comparison_image_decision'
        id = db.Column(db.String(36), primary_key=True)
        cell_id = db.Column(db.String(64), nullable=False, index=True)
        asset_id = db.Column(db.String(36))
        action = db.Column(db.String(20), nullable=False)
        targets_json = db.Column(db.Text, default='[]')
        status = db.Column(db.String(30), nullable=False)
        actor = db.Column(db.Text, nullable=False)
        created_at = db.Column(db.Text, nullable=False)
        started = db.Column(db.Boolean, default=False)

    class ComparisonExecution(db.Model):
        __tablename__ = 'comparison_image_execution'
        id = db.Column(db.String(64), primary_key=True)
        kb_id = db.Column(db.Text, nullable=False)
        payload_json = db.Column(db.Text, nullable=False)
        decision_ids_json = db.Column(db.Text, nullable=False)
        status = db.Column(db.String(30), nullable=False)
        result_json = db.Column(db.Text, default='{}')
        actor = db.Column(db.Text, nullable=False)
        created_at = db.Column(db.Text, nullable=False)
        updated_at = db.Column(db.Text, nullable=False)

    return ComparisonBatch, ComparisonAsset, ComparisonCell, ComparisonDecision, ComparisonExecution


def register_routes(app, db, models, s):
    Batch, Asset, Cell, Decision, Execution = models

    def actor():
        return current_user.username if current_user.is_authenticated else 'system'

    def client():
        c = s.get_supabase_client()
        if c is None:
            raise ValueError('本地主库未配置')
        return c

    def read_kb(c, kb_id):
        rows = c.select_all('knowledge_base_v1', filters={'question_wiki_id': f'eq.{kb_id}'},
                            order_by='question_wiki_id', page_size=1) or []
        if not rows:
            raise ValueError(f'KB {kb_id} 已不存在或不在可编辑范围')
        return rows[0]

    def sources():
        c = client()
        links = c.select_all('link_previews', columns='id,url,kb_id,tags,type,created_at') or []
        tagged = [v for v in links if TAG in (unpack(v.get('tags'), []) or [])]
        urls = {v['url'] for v in tagged}
        urls.update(v.url for v in Asset.query.all())
        refs = {url: [] for url in urls}
        # Associations explain a link's KB context; only actual media positions
        # become executable references. Read the same physical V1 as link sync.
        rows = c.select_all('knowledge_base_v1', columns='question_wiki_id,product_name,image_urls,link_url,content_version',
                            order_by='question_wiki_id', use_formal=False) or []
        by_id = {str(row['question_wiki_id']): row for row in rows}
        associations = {url: {} for url in urls}
        for link in links:
            if link['url'] not in associations:
                continue
            raw_ids = unpack(link.get('kb_id'), link.get('kb_id'))
            if not isinstance(raw_ids, list):
                raw_ids = re.split(r'[,，;；\s]+', str(raw_ids or ''))
            for value in raw_ids:
                kb_id = str(value).strip()
                if kb_id:
                    kb = by_id.get(kb_id)
                    associations[link['url']][kb_id] = {
                        'kb_id': kb_id, 'kb_models': (kb.get('product_name') or '') if kb else '',
                        'kb_exists': kb is not None, 'reference_verified': False}
        for row in rows:
            fields = [('link_url', 0, row.get('link_url'))]
            try:
                fields += [('image_urls', i, url) for i, url in enumerate(image_list(row.get('image_urls')))]
            except ValueError:
                pass
            for field, position, url in fields:
                if isinstance(url, str) and url in refs:
                    associations[url][str(row['question_wiki_id'])] = {
                        'kb_id': str(row['question_wiki_id']), 'kb_models': row.get('product_name') or '',
                        'kb_exists': True, 'reference_verified': True}
                    refs[url].append({'kb_id': str(row['question_wiki_id']), 'field': field, 'position': position,
                                      'old_url': url, 'base_version': int(row.get('content_version') or 1),
                                      'kb_models': row.get('product_name') or ''})
        return tagged, refs, associations

    def validate_models(values):
        if not isinstance(values, list) or len(values) < 2 or any(not isinstance(v, str) for v in values):
            raise ValueError('请从型号目录选择至少两个不同型号')
        if len(set(values)) != len(values):
            raise ValueError('图片覆盖型号不能重复')
        catalog = s.parse_product_catalog()
        categories = []
        for value in values:
            found = [name for name, entries in catalog.items() if value in entries]
            if len(found) != 1:
                raise ValueError(f'型号不存在或品类不唯一：{value}')
            categories.extend(found)
        if len(set(categories)) != 1:
            raise ValueError('请选择同一品类的图片型号，跨品类图片请拆分录入')
        return categories[0]

    def asset_dict(a, refs, tagged_urls, associations):
        covered = unpack(a.models_json, [])
        related = refs.get(a.url, [])
        active = Cell.query.filter_by(active_asset_id=a.id).count()
        batch = db.session.get(Batch, a.batch_id) if a.batch_id else None
        return {'id': a.id, 'url': a.url, 'link_id': a.link_id, 'category': a.category,
                'models': covered, 'confirmed_by': a.confirmed_by, 'historical': a.historical,
                'batch_id': a.batch_id, 'batch_name': batch.name if batch else '历史初始化',
                'created_at': a.created_at, 'references': related,
                'kb_associations': list(associations.get(a.url, {}).values()), 'tagged': a.url in tagged_urls,
                'status': '使用中' if active else ('候选' if a.confirmed_by else '待补全')}

    def cell_dict(cell):
        decision = db.session.get(Decision, cell.latest_decision_id) if cell.latest_decision_id else None
        active = db.session.get(Asset, cell.active_asset_id) if cell.active_asset_id else None
        return {'id': cell.id, 'category': cell.category, 'pair': unpack(cell.pair_json, []),
                'active_asset_id': cell.active_asset_id, 'active_url': active.url if active else None,
                'decision_id': decision.id if decision else None,
                'status': decision.status if decision else '待确认',
                'action': decision.action if decision else None,
                'pending_asset_id': decision.asset_id if decision else None}

    def checked_targets(asset, pair, targets, refs):
        if not isinstance(targets, list) or not targets:
            raise ValueError('请选择至少一个明确的 KB 旧链接位置；本期不自动新增 KB 图片')
        allowed = []
        for old in Asset.query.filter(Asset.confirmed_by != '').all():
            if old.category == asset.category and set(pair) <= set(unpack(old.models_json, [])):
                allowed += refs.get(old.url, [])
        clean = []
        for t in targets:
            if not isinstance(t, dict):
                raise ValueError('替换目标格式无效')
            wanted = {k: t.get(k) for k in ('kb_id', 'field', 'position', 'old_url', 'base_version')}
            if not any(all(ref.get(k) == value for k, value in wanted.items()) for ref in allowed):
                raise ValueError('目标版本或旧链接已变化，或旧图型号未经人工确认，请刷新格子后重新确认')
            if wanted['old_url'] == asset.url:
                raise ValueError('新旧链接相同，请选择保持旧图或历史登记')
            if wanted in clean:
                raise ValueError('替换目标不能重复')
            clean.append(wanted)
        return clean

    def response_error(fn):
        from functools import wraps
        @wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except ValueError as exc:
                db.session.rollback()
                return jsonify(success=False, message=str(exc)), 400
            except Exception:
                db.session.rollback()
                app.logger.exception('comparison matrix request failed')
                return jsonify(success=False, message='操作失败，已保存的执行意图可在执行清单中恢复；请检查服务日志'), 500
        return wrapped

    def route(path, methods):
        def decorator(fn):
            app.route('/api/comparison-matrix' + path, methods=methods)(s.login_required(response_error(fn)))
            return fn
        return decorator

    @route('/overview', ['GET'])
    def comparison_overview():
        tagged, refs, associations = sources()
        urls = {v['url'] for v in tagged}
        assets = [asset_dict(a, refs, urls, associations) for a in Asset.query.order_by(Asset.created_at).all()]
        return jsonify(success=True, catalog=s.parse_product_catalog(), assets=assets,
                       cells=[cell_dict(c) for c in Cell.query.all()],
                       uninitialized=[v for v in tagged if not any(a['url'] == v['url'] for a in assets)])

    @route('/initialize', ['POST'])
    def comparison_initialize():
        tagged, refs, associations = sources()
        added = 0
        for link in tagged:
            if Asset.query.filter_by(url=link['url']).first():
                continue
            db.session.add(Asset(id=str(uuid.uuid4()), url=link['url'], link_id=str(link['id']),
                                 historical=True, created_at=now()))
            added += 1
        db.session.commit()
        return jsonify(success=True, added=added, pending_model_confirmation=Asset.query.filter_by(confirmed_by='').count(),
                       missing_references=[v['url'] for v in tagged if not refs.get(v['url'])])

    @route('/batches', ['POST'])
    def comparison_add_batch():
        data = request.get_json(silent=True) or {}
        images = data.get('images')
        if not isinstance(images, list) or not images:
            raise ValueError('批次至少包含一张图片')
        validated = []
        seen = set()
        for image in images:
            url = str(image.get('url') or '').strip()
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                raise ValueError('图片必须是 HTTP/HTTPS 链接')
            if url in seen or Asset.query.filter_by(url=url).first():
                raise ValueError(f'重复图片链接：{url}')
            seen.add(url)
            category = validate_models(image.get('models'))
            validated.append((url, category, image['models']))
        c = client()
        links = c.select_all('link_previews', columns='id,url,tags,created_at,kb_id') or []
        batch = Batch(id=str(uuid.uuid4()), name=str(data.get('name') or '新图批次'), note=str(data.get('note') or ''),
                      actor=actor(), created_at=now())
        db.session.add(batch)
        for url, category, covered in validated:
            existing = next((v for v in links if v['url'] == url), None)
            # Reuse the normal link API payload and write semantics, preserving tags.
            tags = list(unpack(existing.get('tags'), []) or []) if existing else []
            if TAG not in tags:
                tags.append(TAG)
            payload = s._normalize_link_preview_payload({'id': str(existing['id']) if existing else str(uuid.uuid4()),
                                                         'url': url, 'type': 'image', 'tags': tags,
                                                         'kb_id': existing.get('kb_id') if existing else None,
                                                         'createdAt': existing.get('created_at') if existing else now()})
            resp = c.upsert('link_previews', [payload], on_conflict='id')
            if resp is None or resp.status_code >= 400:
                raise ValueError('链接保存失败，请重试；已有链接不会删除')
            a = Asset(id=str(uuid.uuid4()), url=url, link_id=payload['id'], batch_id=batch.id,
                      category=category, models_json=dump(covered), confirmed_by=actor(), confirmed_at=now(), created_at=now())
            db.session.add(a)
            for pair in itertools.combinations(covered, 2):
                key = pair_key(category, pair)
                if not db.session.get(Cell, key):
                    db.session.add(Cell(id=key, category=category, pair_json=dump(sorted(pair))))
        db.session.commit()
        return jsonify(success=True, batch_id=batch.id)

    @route('/assets/<asset_id>/models', ['POST'])
    def comparison_confirm_models(asset_id):
        a = db.session.get(Asset, asset_id)
        if not a:
            raise ValueError('图片不存在')
        values = (request.get_json(silent=True) or {}).get('models')
        category = validate_models(values)
        # Coverage used in a decision is immutable; a wrong image must be added
        # separately so an existing decision never silently changes meaning.
        used_as_old = any(any(t.get('old_url') == a.url for t in unpack(d.targets_json, [])) for d in Decision.query.all())
        if used_as_old or Decision.query.filter_by(asset_id=asset_id).first() or Cell.query.filter_by(active_asset_id=asset_id).first():
            raise ValueError('该图片已有确认记录，不能修改覆盖型号')
        a.category, a.models_json, a.confirmed_by, a.confirmed_at = category, dump(values), actor(), now()
        for pair in itertools.combinations(values, 2):
            key = pair_key(category, pair)
            if not db.session.get(Cell, key):
                db.session.add(Cell(id=key, category=category, pair_json=dump(sorted(pair))))
        db.session.commit()
        return jsonify(success=True)

    @route('/cell', ['GET'])
    def comparison_cell():
        category = request.args.get('category', '')
        pair = [request.args.get('a'), request.args.get('b')]
        if len(set(pair)) != 2 or any(v not in s.parse_product_catalog().get(category, []) for v in pair):
            raise ValueError('无效的同品类型号对')
        cell = db.session.get(Cell, pair_key(category, pair))
        tagged, refs, associations = sources()
        urls = {v['url'] for v in tagged}
        candidates = [asset_dict(a, refs, urls, associations) for a in Asset.query.filter_by(category=category).all()
                      if a.confirmed_by and set(pair) <= set(unpack(a.models_json, [])) and a.url in urls]
        for candidate in candidates:
            candidate['targets'] = []
            for old in candidates:
                for ref in old['references']:
                    exact = set(old['models']) == set(candidate['models'])
                    candidate['targets'].append(dict(ref, old_asset_id=old['id'], old_models=old['models'],
                                                      rank=[0 if exact else 1, len(old['models'])],
                                                      reason='覆盖型号集合完全一致' if exact else '旧图包含该型号对（备选）'))
            candidate['targets'].sort(key=lambda v: v['rank'])
        candidates.sort(key=lambda v: (len(v['models']), v['id']))
        decision = db.session.get(Decision, cell.latest_decision_id) if cell and cell.latest_decision_id else None
        history = []
        if cell:
            for item in Decision.query.filter_by(cell_id=cell.id).order_by(Decision.created_at.desc()).all():
                selected_asset = db.session.get(Asset, item.asset_id) if item.asset_id else None
                history.append({'id': item.id, 'action': item.action, 'status': item.status,
                                'actor': item.actor, 'created_at': item.created_at,
                                'url': selected_asset.url if selected_asset else None,
                                'targets': unpack(item.targets_json, [])})
        return jsonify(success=True, history=history, cell=cell_dict(cell) if cell else {'id': pair_key(category, pair), 'pair': pair, 'category': category},
                       candidates=candidates, historical_conflict=len([v for v in candidates if v['historical'] and v['references']]) > 1,
                       decision={'id': decision.id, 'asset_id': decision.asset_id, 'targets': unpack(decision.targets_json, []),
                                 'action': decision.action, 'status': decision.status} if decision else None)

    @route('/confirm', ['POST'])
    def comparison_confirm():
        data = request.get_json(silent=True) or {}
        pair, category = data.get('pair'), data.get('category')
        if not isinstance(pair, list) or len(pair) != 2 or len(set(pair)) != 2:
            raise ValueError('请选择两个不同型号')
        if validate_models(pair) != category:
            raise ValueError('品类与型号不匹配')
        key = pair_key(category, pair)
        cell = db.session.get(Cell, key)
        if not cell:
            cell = Cell(id=key, category=category, pair_json=dump(sorted(pair)))
            db.session.add(cell)
        if data.get('base_decision_id') != cell.latest_decision_id:
            raise ValueError('格子已被其他人确认，请重新打开')
        previous = db.session.get(Decision, cell.latest_decision_id) if cell.latest_decision_id else None
        if previous and previous.status in ('写入中', '待恢复', '部分成功'):
            raise ValueError('该格子已有未完成写入，请先在执行清单恢复或重试')
        action = data.get('action')
        if action not in ('replace', 'keep', 'initialize'):
            raise ValueError('无效确认决定')
        asset = db.session.get(Asset, data.get('asset_id')) if data.get('asset_id') else None
        targets = []
        if action != 'keep':
            if not asset or not asset.confirmed_by or asset.category != category or not set(pair) <= set(unpack(asset.models_json, [])):
                raise ValueError('图片覆盖型号尚未人工确认或不包含此型号对')
            tagged, refs, associations = sources()
            if not any(v['url'] == asset.url for v in tagged):
                raise ValueError('该链接已删除或已移除产品对比图标签')
            if action == 'initialize':
                if cell.active_asset_id or not asset.historical or not refs.get(asset.url):
                    raise ValueError('仅可为缺失格子登记有实际 KB 引用的历史图')
            else:
                targets = checked_targets(asset, pair, data.get('targets'), refs)
        decision = Decision(id=str(uuid.uuid4()), cell_id=key, asset_id=cell.active_asset_id if action == 'keep' else asset.id,
                            action=action, targets_json=dump(targets), actor=actor(), created_at=now(),
                            status='已确认待写入' if action == 'replace' else ('已生效' if action == 'initialize' else '保持旧图'))
        db.session.add(decision)
        # Serialize competing confirmations with a compare-and-swap pointer.
        db.session.flush()
        changed = db.session.execute(update(Cell).where(Cell.id == key, Cell.latest_decision_id == cell.latest_decision_id)
                                     .values(latest_decision_id=decision.id,
                                             active_asset_id=asset.id if action == 'initialize' else cell.active_asset_id))
        if changed.rowcount != 1:
            raise ValueError('格子确认发生并发冲突，请刷新')
        db.session.commit()
        return jsonify(success=True, decision_id=decision.id, status=decision.status)

    def get_decisions(data):
        ids = data.get('decision_ids')
        if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
            raise ValueError('请选择已确认的格子')
        decisions = []
        for value in ids:
            d = db.session.get(Decision, value)
            if not d or d.action != 'replace':
                raise ValueError('决定不存在或不属于链接替换')
            cell = db.session.get(Cell, d.cell_id)
            if cell.latest_decision_id != d.id:
                raise ValueError('确认决定已被后续决定替代，请重新预览')
            decisions.append(d)
        return decisions

    def build_plan(decisions):
        grouped = {}
        for d in decisions:
            a = db.session.get(Asset, d.asset_id)
            for t in unpack(d.targets_json, []):
                grouped.setdefault(t['kb_id'], []).append(dict(t, new_url=a.url, decision_id=d.id,
                                                               pair=unpack(db.session.get(Cell, d.cell_id).pair_json, []),
                                                               batch_id=a.batch_id))
        groups = []
        for kb_id, entries in sorted(grouped.items()):
            errors = []
            if len({v['base_version'] for v in entries}) != 1:
                errors.append('同一 KB 的确认版本不一致')
            locations = {}
            for entry in entries:
                key = (entry['field'], entry['position'])
                if key in locations and any(locations[key][k] != entry[k] for k in ('old_url', 'new_url')):
                    errors.append('同一 KB 字段位置选择了不同新图或旧链接')
                locations[key] = entry
            identity = digest([kb_id, sorted(entries, key=lambda v: (v['decision_id'], v['field'], v['position']))])
            execution = db.session.get(Execution, identity)
            groups.append({'id': identity, 'kb_id': kb_id, 'entries': entries, 'conflicts': sorted(set(errors)),
                           'status': execution.status if execution else '已确认待写入',
                           'result': unpack(execution.result_json, {}) if execution else {}})
        # A started execution is an immutable per-KB group. Changing selected
        # cells on retry must not create a second intent for already written KBs.
        for group in groups:
            ids = {entry['decision_id'] for entry in group['entries']}
            for execution in Execution.query.filter_by(kb_id=group['kb_id']).all():
                if execution.id != group['id'] and ids & set(unpack(execution.decision_ids_json, [])):
                    raise ValueError('重试必须勾选原执行中合并到同一 KB 的全部格子，请一起重新预览')
        return groups

    def validate_current(row, entries):
        expected = entries[0]['base_version']
        if int(row.get('content_version') or 1) != expected:
            raise ValueError('KB 内容版本已变化，请重新确认')
        changes = {}
        for e in entries:
            field, position = e['field'], e['position']
            if field not in ('image_urls', 'link_url'):
                raise ValueError('不允许修改此字段')
            if field == 'image_urls':
                values = changes.setdefault(field, list(image_list(row.get(field))))
                original = image_list(row.get(field))
                if not isinstance(position, int) or position < 0 or position >= len(original) or original[position] != e['old_url']:
                    raise ValueError('指定图片位置旧 URL 已变化')
                values[position] = e['new_url']
            else:
                if position != 0 or row.get(field) != e['old_url']:
                    raise ValueError('单链接字段旧 URL 已变化')
                changes[field] = e['new_url']
        return changes

    def read_back_matches(row, changes):
        for field, value in changes.items():
            if field == 'image_urls':
                try:
                    if image_list(row.get(field)) != value:
                        return False
                except ValueError:
                    return False
            elif row.get(field) != value:
                return False
        return True

    @route('/preview', ['POST'])
    def comparison_preview():
        decisions = get_decisions(request.get_json(silent=True) or {})
        groups = build_plan(decisions)
        c = client()
        for group in groups:
            if group['status'] == '成功':
                continue
            try:
                row = read_kb(c, group['kb_id'])
                group['current_version'] = row.get('content_version')
                validate_current(row, group['entries'])
            except ValueError as exc:
                if group['status'] not in ('写入中', '待恢复'):
                    group['conflicts'].append(str(exc))
        token = digest([[g['id'], g['conflicts']] for g in groups])
        return jsonify(success=True, token=token, groups=groups,
                       keep_count=Decision.query.filter_by(status='保持旧图').count())

    def audit_for(c, execution):
        # operation_id is a digest, kb_id was selected from actual V1 rows.
        rows = c.select_all('knowledge_base_modifications',
                            filters={'operation_id': f'eq.cm-{execution.id}'},
                            columns='id,kb_id,operation_id,committed_version', page_size=5) or []
        return next((r for r in rows if str(r.get('kb_id')) == execution.kb_id), None)

    def finish_decisions(decisions):
        for d in decisions:
            executions = [e for e in Execution.query.all() if d.id in unpack(e.decision_ids_json, [])]
            statuses = [e.status for e in executions]
            expected_kbs = {v['kb_id'] for v in unpack(d.targets_json, [])}
            successful_kbs = {e.kb_id for e in executions if e.status == '成功'}
            if successful_kbs == expected_kbs:
                d.status = '已生效'
                cell = db.session.get(Cell, d.cell_id)
                if cell.latest_decision_id == d.id:
                    cell.active_asset_id = d.asset_id
            elif successful_kbs:
                d.status = '部分成功'
            elif '写入中' in statuses:
                d.status = '写入中'
            elif '待恢复' in statuses:
                d.status = '待恢复'
            elif '冲突' in statuses:
                d.status = '冲突'
            else:
                d.status = '失败'
        db.session.commit()

    @route('/apply', ['POST'])
    def comparison_apply():
        data = request.get_json(silent=True) or {}
        decisions = get_decisions(data)
        groups = build_plan(decisions)
        # Require preview of the exact immutable decisions and static collisions.
        # Current KB versions are checked again immediately before each write.
        c = client()
        preview_groups = []
        for g in groups:
            conflicts = list(g['conflicts'])
            if g['status'] not in ('成功', '写入中', '待恢复'):
                try:
                    validate_current(read_kb(c, g['kb_id']), g['entries'])
                except ValueError as exc:
                    conflicts.append(str(exc))
            preview_groups.append([g['id'], conflicts])
        if data.get('token') != digest(preview_groups):
            return jsonify(success=False, message='预览已变化，请重新查看 KB 差异', conflict=True), 409
        for d in decisions:
            d.started = True
            d.status = '写入中'
        db.session.commit()
        tagged_urls = {v['url'] for v in c.select_all('link_previews', columns='url,tags')
                       if TAG in (unpack(v.get('tags'), []) or [])}
        for g in groups:
            e = db.session.get(Execution, g['id'])
            if e and e.status == '成功':
                continue
            if not e:
                e = Execution(id=g['id'], kb_id=g['kb_id'], payload_json=dump({'entries': g['entries']}),
                              decision_ids_json=dump(sorted({v['decision_id'] for v in g['entries']})),
                              status='待执行', actor=actor(), created_at=now(), updated_at=now())
                db.session.add(e)
                db.session.commit()
            if g['conflicts']:
                e.status, e.result_json = '冲突', dump({'message': '；'.join(g['conflicts'])})
                db.session.commit()
                continue
            # Claim a per-KB execution atomically across requests/processes.
            # A live writer retains its claim for ten minutes; recovery is
            # immediate after a recorded exception, or after a stale claim.
            if e.status == '写入中' and datetime.fromisoformat(e.updated_at) > datetime.now(timezone.utc) - timedelta(minutes=10):
                continue
            original_status, original_updated = e.status, e.updated_at
            claimed = db.session.execute(update(Execution).where(
                Execution.id == e.id, Execution.status == original_status,
                Execution.updated_at == original_updated).values(status='写入中', updated_at=now()))
            if claimed.rowcount != 1:
                db.session.rollback()
                continue
            db.session.commit()
            payload = unpack(e.payload_json, {})
            # A crashed writer is never blindly replayed. Audit + exact readback
            # reconcile an already committed write; absence of evidence is shown.
            if payload.get('changes'):
                retry_original = False
                try:
                    audit = audit_for(c, e)
                    row = read_kb(c, e.kb_id)
                    if audit and payload.get('changes') and read_back_matches(row, payload['changes']):
                        e.status, e.result_json = '成功', dump({'recovered': True, 'modification_id': audit['id'],
                                                               'content_version': audit.get('committed_version')})
                    elif not audit and int(row.get('content_version') or 1) == g['entries'][0]['base_version']:
                        # The CAS write can safely be retried at the original
                        # version, even if another request is still completing.
                        retry_original = True
                    else:
                        e.status, e.result_json = '待恢复', dump({'message': 'KB 与执行记录需核对，禁止无审计重复覆盖'})
                    db.session.commit()
                    if not retry_original:
                        continue
                except Exception as exc:
                    e.status, e.result_json = '待恢复', dump({'message': str(exc)})
                    db.session.commit()
                    continue
            try:
                if any(entry['new_url'] not in tagged_urls for entry in g['entries']):
                    raise ValueError('新图链接已删除或产品对比图标签已移除，请重新确认')
                row = read_kb(c, e.kb_id)
                changes = validate_current(row, g['entries'])
                payload['changes'] = changes
                e.payload_json = dump(payload)
                e.status, e.updated_at = '写入中', now()
                db.session.commit()  # durable intent before writing a different DB
                write_payload = dict(changes, question_wiki_id=e.kb_id,
                                     operation_id=f'cm-{e.id}', base_version=g['entries'][0]['base_version'],
                                     strict_version=True, change_source=TAG + '矩阵', source_code='comparison_matrix')
                # This calls the existing route implementation, not an HTTP loop
                # and not a separate KB mutation/audit implementation.
                with app.test_request_context('/api/kb/update', method='POST', json=write_payload):
                    response = app.make_response(s.update_kb_item.__wrapped__())
                result = response.get_json() or {}
                result['http_status'] = response.status_code
                if not result.get('success'):
                    e.status = '冲突' if response.status_code == 409 else '失败'
                else:
                    after = read_kb(c, e.kb_id)
                    audit = audit_for(c, e)
                    if read_back_matches(after, changes) and audit:
                        e.status = '成功'
                        result['modification_id'] = audit['id']
                    else:
                        e.status = '待恢复'
                        result['message'] = 'KB 已提交，修改记录或目标链接回读未通过；重试将核对恢复'
                e.result_json, e.updated_at = dump(result), now()
                db.session.commit()
            except ValueError as exc:
                e.status, e.result_json, e.updated_at = '冲突', dump({'message': str(exc)}), now()
                db.session.commit()
            except Exception as exc:
                e.status, e.result_json, e.updated_at = '待恢复', dump({'message': str(exc)}), now()
                db.session.commit()
        finish_decisions(decisions)
        return jsonify(success=True, groups=build_plan(decisions), cells=[cell_dict(db.session.get(Cell, d.cell_id)) for d in decisions])

    def execution_rows():
        rows = []
        for e in Execution.query.order_by(Execution.created_at.desc()).all():
            result = unpack(e.result_json, {})
            for entry in unpack(e.payload_json, {}).get('entries', []):
                d = db.session.get(Decision, entry['decision_id'])
                batch = db.session.get(Batch, entry.get('batch_id')) if entry.get('batch_id') else None
                rows.append(dict(entry, batch_name=batch.name if batch else '历史初始化', execution_id=e.id, status=e.status, reason=result.get('message') or result.get('mod_log_error') or '',
                                 modification_id=result.get('modification_id'), committed_version=result.get('content_version'),
                                 operation_id=f'cm-{e.id}', actor=e.actor, created_at=e.created_at, updated_at=e.updated_at,
                                 decision=d.action if d else 'replace'))
        return rows

    @route('/executions', ['GET'])
    def comparison_executions():
        rows = execution_rows()
        if request.args.get('format') == 'csv':
            buffer = io.StringIO()
            fields = ['batch_id', 'batch_name', 'pair', 'kb_id', 'field', 'position', 'old_url', 'new_url', 'decision', 'status',
                      'reason', 'modification_id', 'base_version', 'committed_version', 'operation_id', 'actor', 'created_at', 'updated_at']
            writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                # Prevent spreadsheet formula execution in operator-controlled cells.
                writer.writerow({k: ("'" + str(v) if str(v).startswith(('=', '+', '-', '@')) else v) for k, v in row.items()})
            return Response('\ufeff' + buffer.getvalue(), mimetype='text/csv',
                            headers={'Content-Disposition': 'attachment; filename=comparison-executions.csv'})
        return jsonify(success=True, rows=rows)
