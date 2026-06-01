def validate_submit_changes(changes):
    errors = []
    normalized = []
    keys = set()
    if not isinstance(changes, list) or len(changes) == 0:
        return [], ['No changes']
    for idx, item in enumerate(changes):
        prefix = f'第 {idx + 1} 条'
        if not isinstance(item, dict):
            errors.append(f'{prefix}: 记录格式非法')
            continue
        wiki_id = str(item.get('question_wiki_id') or '').strip()
        product_name = str(item.get('product_name') or '').strip()
        old_val = item.get('old_is_configured', None)
        new_val = item.get('new_is_configured', None)
        edit_source = str(item.get('edit_source') or '').strip()
        if not wiki_id:
            errors.append(f'{prefix}: 缺少 question_wiki_id')
        if not product_name:
            errors.append(f'{prefix}: 缺少 product_name')
        if type(old_val) is not bool:
            errors.append(f'{prefix}: old_is_configured 必须是布尔值')
        if type(new_val) is not bool:
            errors.append(f'{prefix}: new_is_configured 必须是布尔值')
        if type(old_val) is bool and type(new_val) is bool and old_val == new_val:
            errors.append(f'{prefix}: 修改前后无差异')
        k = f'{wiki_id}::{product_name}'
        if wiki_id and product_name:
            if k in keys:
                errors.append(f'{prefix}: 重复的 (question_wiki_id, product_name)')
            keys.add(k)
        normalized.append({
            'question_wiki_id': wiki_id,
            'product_name': product_name,
            'old_is_configured': old_val,
            'new_is_configured': new_val,
            'edit_source': edit_source
        })
    return normalized, errors
