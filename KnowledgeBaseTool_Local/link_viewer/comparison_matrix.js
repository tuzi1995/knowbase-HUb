/* Product image matrix. All confirmations and execution state live on the server. */
(() => {
  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  let state = {catalog: {}, assets: [], cells: []};
  let loaded = false;
  let category = '', imageSearch = '', view = 'allLinksView', detail = null, draft = [], preview = null;
  const positions = {};
  const chosen = new Set();
  const endpoint = '/api/comparison-matrix';
  async function api(path, data) {
    const response = await fetch(endpoint + path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    if (!(response.headers.get('content-type') || '').includes('application/json')) {
      throw new Error(response.status === 404 ? '产品对比接口尚未加载，请重启 8085 服务后刷新页面。' : '服务返回了页面而非数据，请确认登录状态后重试。');
    }
    const result = await response.json();
    if (!response.ok || !result.success) throw new Error(result.message || '操作失败，请刷新重试');
    return result;
  }
  function error(err) {
    const target = $('comparisonDialog').open ? $('comparisonDialogError') : $('comparisonStatus');
    target.hidden = false;
    target.textContent = err.message || String(err);
  }
  const safe = fn => async (...args) => { try { return await fn(...args); } catch (err) { error(err); } };
  function dialog(title, html) {
    $('comparisonDialogTitle').textContent = title;
    $('comparisonDialogBody').innerHTML = html;
    $('comparisonDialogError').textContent = '';
    if (!$('comparisonDialog').open) $('comparisonDialog').showModal();
  }
  function image(url) {
    return `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer"><img class="cm-thumb" src="${escape(url)}" alt="对比图预览，加载失败可打开链接" loading="lazy" referrerpolicy="no-referrer"></a>`;
  }
  function toolbar() {
    return `<div class="cm-toolbar"><button class="primary-btn" data-cm="batch">新增批次</button><button class="action-btn" data-cm="initialize">初始化历史台账</button><button class="action-btn" data-cm="refresh">刷新</button><button class="action-btn" data-cm="executions">执行清单</button></div>`;
  }
  async function refresh() {
    state = await api('/overview'); loaded = true;
    if (!state.catalog[category]) category = Object.keys(state.catalog)[0] || '';
    $('comparisonStatus').hidden = true;
    renderImages(); renderMatrix();
  }
  function associations(asset) {
    return asset.kb_associations || [...new Map(asset.references.map(r => [r.kb_id, {...r, kb_exists:true, reference_verified:true}])).values()];
  }
  function formatTime(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value || '—') : date.toLocaleString('zh-CN', {hour12:false});
  }
  function renderAssociation(asset) {
    const related = associations(asset);
    if (!related.length) return '<span class="cm-muted">尚未关联 KB</span><small class="cm-reference-note">链接未登记 KB，当前库也未找到图片引用</small>';
    return related.map(r => {
      const positions = asset.references.filter(ref => ref.kb_id === r.kb_id);
      return `<div class="cm-kb-association"><strong>${escape(r.kb_id)}</strong><div>${escape(r.kb_models || (r.kb_exists ? 'KB 未填写关联型号' : '当前库未找到该 KB'))}</div><small class="cm-reference-note">${positions.length ? positions.map(p=>`${escape(p.field)}[${p.position}] · 版本 ${p.base_version}`).join('、') : '链接登记的关联 · 未找到可替换位置'}</small></div>`;
    }).join('');
  }
  function renderImages() {
    const tagged = state.assets.filter(a => a.tagged);
    const assets = tagged.filter(a => !imageSearch || [a.url, a.batch_name, ...a.models, ...associations(a).flatMap(r => [r.kb_id, r.kb_models])].join(' ').toLowerCase().includes(imageSearch.toLowerCase()));
    const unlinked = tagged.filter(a=>!associations(a).length).length;
    $('comparisonImagesView').innerHTML = `<div class="cm-list-header"><div><h3>产品对比图</h3><p class="cm-list-summary">${tagged.length} 张图片 · ${tagged.length-unlinked} 张已关联 KB · ${unlinked} 张未关联${state.uninitialized?.length ? ` · ${state.uninitialized.length} 条标签链接待初始化` : ''}</p></div>${toolbar()}</div>
      <div class="cm-list-filter"><label for="cmImageSearch">搜索</label><input class="input-modern" id="cmImageSearch" placeholder="链接、KB ID、关联型号或批次" value="${escape(imageSearch)}"><span>KB 型号来自知识库；图片覆盖型号需人工确认。</span></div>
      <div class="cm-table-wrap cm-images-scroll"><table class="kb-table cm-images-table"><colgroup><col class="cm-col-image"><col class="cm-col-kb"><col class="cm-col-models"><col class="cm-col-batch"><col class="cm-col-actions"></colgroup><thead><tr><th>对比图 / 链接</th><th>关联 KB / KB 型号</th><th>图片覆盖型号</th><th>批次 / 状态</th><th>操作</th></tr></thead><tbody>${assets.map(a => `<tr><td><div class="cm-asset-info">${image(a.url)}<div class="cm-link-info"><a class="cm-url" href="${escape(a.url)}" title="${escape(a.url)}" target="_blank" rel="noopener noreferrer">${escape(a.url)}</a><button class="cm-text-button" data-cm="copy" data-value="${escape(a.url)}">复制链接</button></div></div></td>
      <td>${renderAssociation(a)}</td><td><span class="${a.models.length ? '' : 'cm-muted'}">${escape(a.models.join(' → ') || '待人工确认')}</span><small class="cm-reference-note">${escape(a.category || '从目录选择图上型号')}</small></td>
      <td><span class="cm-status-badge" data-status="${escape(a.status)}">${escape(a.status)}</span><div class="cm-batch-name">${escape(a.batch_name)}</div><time class="cm-reference-note" datetime="${escape(a.created_at)}">${escape(formatTime(a.created_at))}</time></td>
      <td><div class="cm-row-actions"><button class="action-btn" data-cm="models" data-id="${escape(a.id)}">${a.models.length ? '查看型号' : '补充型号'}</button><button class="cm-text-button" data-cm="impact" data-id="${escape(a.id)}">受影响格子</button></div></td></tr>`).join('') || '<tr><td colspan="5" class="cm-empty">没有匹配图片。可调整搜索条件、初始化已有标签链接或新增批次。</td></tr>'}</tbody></table></div>
      <div class="cm-list-footer">显示 ${assets.length} / ${tagged.length} 张 · 仅列出带“产品对比图”标签的链接</div>`;
  }
  function findCell(a, b) { return state.cells.find(c => c.category === category && c.pair.includes(a) && c.pair.includes(b)); }
  function renderMatrix() {
    const previousScroll = $('cmMatrixScroll') ? {left:$('cmMatrixScroll').scrollLeft, top:$('cmMatrixScroll').scrollTop} : null;
    const models = state.catalog[category] || [];
    const cells = state.cells.filter(c => c.category === category);
    const pending = cells.filter(c => c.decision_id && c.action === 'replace');
    const total = models.length*(models.length-1)/2, configured = cells.filter(c=>c.active_url).length;
    const selected = pending.filter(c=>chosen.has(c.decision_id)).length;
    $('comparisonMatrixView').innerHTML = `<div class="cm-list-header"><div><h3>对比矩阵</h3><p class="cm-list-summary">按品类查看型号对比，点击格子选择图片并确认替换。</p></div>${toolbar()}</div>
      <div class="cm-matrix-controls"><label for="cmCategory">品类 <select id="cmCategory" class="input-modern">${Object.keys(state.catalog).map(c => `<option ${c === category ? 'selected' : ''}>${escape(c)}</option>`).join('')}</select></label><div class="cm-matrix-stats"><span><b>${models.length}</b> 个型号</span><span><b>${configured} / ${total}</b> 已配置</span><span><b>${pending.length}</b> 条替换决定</span></div><div class="cm-matrix-legend"><span class="cm-legend-active">已有图片</span><span class="cm-legend-candidate">有候选</span><span class="cm-legend-empty">暂无图片</span></div></div>
      <div class="cm-matrix-hint">A–B 与 B–A 共用一份记录；确认待写入时，当前生效图仍保留。</div>
      <div class="cm-matrix-wrap" id="cmMatrixScroll" role="region" aria-label="${escape(category)}型号对比矩阵" tabindex="0">${models.length ? `<table class="cm-matrix" style="--cm-model-columns:${models.length+1}"><thead><tr><th scope="col">型号 / 型号</th>${models.map(m=>`<th scope="col">${escape(m)}</th>`).join('')}</tr></thead><tbody>${models.map((a,i)=>`<tr><th scope="row">${escape(a)}</th>${models.map((b,j)=> {
        if(i===j) return '<td class="cm-diagonal" aria-label="同型号不比较"><span>—</span></td>';
        const cell=findCell(a,b); const candidates=state.assets.filter(v=>v.tagged && v.category===category && v.models.includes(a) && v.models.includes(b));
        const kind=cell?.active_url ? 'active' : candidates.length ? 'candidate' : 'empty';
        return `<td><button class="cm-cell" data-kind="${kind}" aria-label="${escape(a)} / ${escape(b)}：${escape(cell?.status || (candidates.length ? '待确认' : '暂无图片'))}，${candidates.length} 个候选" data-cm="cell" data-a="${escape(a)}" data-b="${escape(b)}">${cell?.active_url ? `<img src="${escape(cell.active_url)}" alt="当前生效图" loading="lazy" referrerpolicy="no-referrer">` : `<strong>${candidates.length ? '选择图片' : '暂无图片'}</strong>`}${cell?.status || candidates.length ? `<span class="cm-cell-status">${escape(cell?.status || '待确认')}</span>` : ''}<small>${candidates.length ? `${candidates.length} 个候选` : '点击查看'}</small></button></td>`;
      }).join('')}</tr>`).join('')}</tbody></table>` : '<div class="cm-matrix-empty">该品类暂无型号，请先在型号库中维护。</div>'}</div>
      <div class="cm-pending cm-matrix-pending"><div class="cm-pending-head"><div><h4>已确认的替换 <span>${pending.length}</span></h4><p>${pending.length ? '勾选本次应用的记录，查看差异后再应用；失败或部分成功记录可重试。' : '暂无替换决定，先点击矩阵格子选择图片并确认。'}</p></div><button class="primary-btn" data-cm="preview" id="cmPreviewChanges" ${selected ? '' : 'disabled'}>查看 KB 差异<span id="cmSelectedCount">${selected ? `（${selected}）` : ''}</span></button></div>${pending.length ? `<div class="cm-pending-options">${pending.map(c=>`<label><input type="checkbox" data-cm-decision="${c.decision_id}" ${chosen.has(c.decision_id)?'checked':''}><strong>${escape(c.pair.join(' / '))}</strong><span>${escape(c.status)}</span></label>`).join('')}</div>` : ''}</div>`;
    if(previousScroll) { $('cmMatrixScroll').scrollLeft=previousScroll.left; $('cmMatrixScroll').scrollTop=previousScroll.top; }
  }
  async function switchTab(id) {
    positions[view] = window.scrollY;
    view = id;
    $('linkView').classList.toggle('cm-active', id !== 'allLinksView');
    for(const name of ['allLinksView','comparisonImagesView','comparisonMatrixView']) $(name).hidden = name !== id;
    document.querySelectorAll('[data-cm-tab]').forEach(el => el.setAttribute('aria-selected', String(el.dataset.cmTab===id)));
    if(id !== 'allLinksView' && !loaded) await refresh();
    window.scrollTo(0,positions[id] || 0);
  }
  function modelPicker(index, values, selectedCategory) {
    return `<label>品类 <select class="input-modern" data-cm-draft-category="${index}">${Object.keys(state.catalog).map(c=>`<option ${c===selectedCategory?'selected':''}>${escape(c)}</option>`).join('')}</select></label><p>图片覆盖型号：<b id="cmOrder${index}">${escape(values.join(' → ') || '按图上展示顺序勾选')}</b></p>
    <div class="cm-model-picker">${(state.catalog[selectedCategory] || []).map(m=>`<label><input type="checkbox" data-cm-model-index="${index}" value="${escape(m)}" ${values.includes(m)?'checked':''}>${escape(m)}</label>`).join('')}</div>`;
  }
  function renderBatch() {
    const batchName = $('cmBatchName')?.value || '';
    const note = $('cmBatchNote')?.value || '';
    document.querySelectorAll('[data-cm-draft-url]').forEach(el => { draft[Number(el.dataset.cmDraftUrl)].url=el.value; });
    dialog('录入新图批次', `<label>批次名称 <input class="input-modern" id="cmBatchName" value="${escape(batchName)}"></label><label>备注 <input class="input-modern" id="cmBatchNote" value="${escape(note)}"></label>
      ${draft.map((v,i)=>`<fieldset><legend>图片 ${i+1}</legend><label>HTTP/HTTPS 图片链接 <input class="input-modern cm-url-input" data-cm-draft-url="${i}" value="${escape(v.url)}"></label>${modelPicker(i,v.models,v.category)}</fieldset>`).join('')}
      <div class="cm-toolbar"><button data-cm="add-draft">再添加一张</button><button class="primary-btn" data-cm="save-batch">保存批次并生成候选</button></div>`);
  }
  async function openCell(a,b) {
    detail = await api(`/cell?category=${encodeURIComponent(category)}&a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
    const current = detail.cell;
    const selectedId = detail.decision?.asset_id || detail.candidates[0]?.id;
    dialog(`${a} / ${b} · 逐格确认`, `<p>当前：${current.active_url ? image(current.active_url)+escape(current.active_url) : '缺失'} · ${escape(current.status || '待确认')}</p>
      ${detail.historical_conflict ? '<p class="cm-warning">同一型号对存在多张历史图，需人工选择初始图；各 KB 的真实引用继续单独展示。</p>':''}
      <label>选择候选 <select class="input-modern" id="cmCandidate">${detail.candidates.map(v=>`<option value="${escape(v.id)}" ${v.id===selectedId?'selected':''}>${escape(v.models.join(' → '))} · ${escape(v.batch_name)}</option>`).join('')}</select></label><div id="cmCandidateDetail"></div>
      <div class="cm-toolbar"><button data-cm="keep">保持旧图（保存决定）</button><button data-cm="initial">登记为初始历史图</button><button class="primary-btn" data-cm="confirm">确认所选目标，待写入</button></div>
      <details><summary>确认历史（${detail.history.length} 条）</summary>${detail.history.map(h=>`<section class="cm-diff"><p>${escape(h.created_at)} · ${escape(h.actor)} · ${escape(({keep:'保持旧图',initialize:'历史登记',replace:'替换'})[h.action])} · ${escape(h.status)}</p><div class="cm-url">${escape(h.url || '缺失')}${h.targets.map(t=>`<p>${escape(t.kb_id)} · ${escape(t.field)}[${t.position}] · 版本 ${t.base_version}<br>${escape(t.old_url)}</p>`).join('')}</div></section>`).join('') || '暂无确认记录'}</details>`);
    renderCandidate();
  }
  function renderCandidate() {
    const candidate = detail.candidates.find(a=>a.id===$('cmCandidate').value);
    if(!candidate) { $('cmCandidateDetail').textContent='没有人工确认的图片候选，请先补充历史图型号或录入新图。'; return; }
    const selected=detail.decision?.asset_id===candidate.id ? detail.decision.targets : [];
    $('cmCandidateDetail').innerHTML = `${image(candidate.url)}<p class="cm-url">${escape(candidate.url)}</p><p>图片覆盖：${escape(candidate.models.join(' → '))} · ${escape(candidate.status)}</p><p>逐条勾选目标；只替换显示的位置。位置从 0 开始；同一 URL 出现多次也分别确认。</p>
      <div class="cm-targets">${candidate.targets.filter(t=>t.old_url!==candidate.url).map((t,i)=>`<label class="cm-target"><input type="checkbox" data-cm-target="${i}" ${selected.some(v=>['kb_id','field','position','old_url','base_version'].every(k=>v[k]===t[k]))?'checked':''}><div><b>${escape(t.kb_id)}</b> · ${escape(t.field)}[${t.position}] · 版本 ${t.base_version}<br>KB 关联型号：${escape(t.kb_models)}<br>旧图覆盖：${escape(t.old_models.join(' → '))}<br><span>${escape(t.reason)} · 优先级 ${t.rank.join(' / ')}（同级并列）</span><div class="cm-url">旧：${escape(t.old_url)}<br>新：${escape(candidate.url)}</div></div></label>`).join('') || '<p>没有可替换的已确认旧图引用；可补全历史图片覆盖型号后重试。本期仅替换已有位置。</p>'}</div>`;
  }
  async function saveDecision(action) {
    const candidate = detail.candidates.find(a=>a.id===$('cmCandidate').value);
    const targets = candidate?.targets.filter(t=>t.old_url!==candidate.url) || [];
    const selected = [...document.querySelectorAll('[data-cm-target]:checked')].map(el=>targets[Number(el.dataset.cmTarget)]);
    const result=await api('/confirm',{category, pair:detail.cell.pair, base_decision_id:detail.cell.decision_id || null, asset_id:candidate?.id, action, targets:selected});
    if(action==='replace') chosen.add(result.decision_id);
    $('comparisonDialog').close(); await refresh();
  }
  async function previewChanges() {
    const valid=new Set(state.cells.map(c=>c.decision_id));
    const ids=[...chosen].filter(id=>valid.has(id));
    preview=await api('/preview',{decision_ids:ids}); preview.ids=ids;
    dialog('KB 修改前后差异', `<p>同一 KB 合并为一次修改。冲突目标会跳过，其余目标可执行。新增 0 项；替换 ${preview.groups.reduce((n,g)=>n+new Set(g.entries.map(e=>e.field+':'+e.position)).size,0)} 个位置；保持旧图 ${preview.keep_count} 格；冲突 ${preview.groups.filter(g=>g.conflicts.length).length} 个 KB。</p>
      ${preview.groups.map(g=>`<section class="cm-diff"><h4>${escape(g.kb_id)} · ${escape(g.status)} · 当前版本 ${g.current_version ?? '—'}</h4>${g.conflicts.map(c=>`<p class="cm-warning">${escape(c)}</p>`).join('')}${g.entries.map(e=>`<p>${escape(e.pair.join(' / '))} · ${escape(e.field)}[${e.position}] · 确认版本 ${e.base_version}</p><del>${escape(e.old_url)}</del><ins>${escape(e.new_url)}</ins>`).join('')}</section>`).join('')}
      <button class="primary-btn" data-cm="apply">一键应用（实际写入 KB / 恢复清单）</button>`);
  }
  async function executions() {
    const result=await api('/executions');
    dialog('执行清单', `<div class="cm-toolbar"><button data-cm="copy-executions">复制清单</button><a class="action-btn" href="${endpoint}/executions?format=csv" download>导出 CSV</a></div><p>失败与冲突需重新确认；部分成功或待恢复可在矩阵勾选原决定后预览重试。已成功目标不重复修改。</p>
      <div class="cm-table-wrap"><table class="kb-table"><thead><tr><th>批次 / 型号对</th><th>KB / 位置</th><th>旧 → 新</th><th>状态 / 原因</th><th>审计 / 版本</th><th>操作人 / 时间</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${escape(r.batch_name)}<br><small>${escape(r.batch_id || '历史')}</small><br>${escape(r.pair.join(' / '))}</td><td>${escape(r.kb_id)}<br>${escape(r.field)}[${r.position}]</td><td class="cm-url">${escape(r.old_url)}<br>→ ${escape(r.new_url)}</td><td>${escape(r.status)}<br>${escape(r.reason)}</td><td>${escape(r.modification_id || '—')}<br>${r.base_version} → ${r.committed_version || '—'}</td><td>${escape(r.actor)}<br>${escape(r.updated_at)}</td></tr>`).join('') || '<tr><td colspan="6">暂无执行记录</td></tr>'}</tbody></table></div>`);
    $('comparisonDialogBody').dataset.copy=JSON.stringify(result.rows,null,2);
  }
  document.addEventListener('click', safe(async event => {
    const button=event.target.closest('[data-cm]'); if(!button) return;
    const action=button.dataset.cm;
    if(button.disabled) return;
    button.disabled=true;
    try {
      if(action==='refresh') await refresh();
      if(action==='initialize') { const r=await api('/initialize',{}); await refresh(); dialog('历史初始化完成',`<p>新增 ${r.added} 条；${r.pending_model_confirmation} 条待补全型号。没有记录被自动设为生效图。</p><p>缺少实际图片引用：${r.missing_references.map(escape).join('、') || '无'}</p>`); }
      if(action==='batch') { draft=[{url:'',models:[],category}]; dialog('录入新图批次',''); renderBatch(); }
      if(action==='add-draft') { draft.push({url:'',models:[],category}); renderBatch(); }
      if(action==='save-batch') {
        document.querySelectorAll('[data-cm-draft-url]').forEach(el=>{draft[Number(el.dataset.cmDraftUrl)].url=el.value;});
        await api('/batches',{name:$('cmBatchName').value,note:$('cmBatchNote').value,images:draft.map(v=>({url:v.url,models:v.models}))}); $('comparisonDialog').close(); await refresh();
      }
      if(action==='models') { const a=state.assets.find(a=>a.id===button.dataset.id); draft=[{models:[...a.models],category:a.category||category,assetId:a.id}]; dialog('人工确认图片覆盖型号',`${image(a.url)}<p>KB 型号只供参考，请按实际图上型号勾选。</p><div id="cmEditPicker">${modelPicker(0,draft[0].models,draft[0].category)}</div><button class="primary-btn" data-cm="save-models">保存型号并生成格子</button>`); }
      if(action==='save-models') { await api(`/assets/${draft[0].assetId}/models`,{models:draft[0].models}); $('comparisonDialog').close(); await refresh(); }
      if(action==='impact') { const a=state.assets.find(a=>a.id===button.dataset.id); category=a.category||category; await switchTab('comparisonMatrixView'); const pairs=[]; a.models.forEach((m,i)=>a.models.slice(i+1).forEach(n=>pairs.push([m,n]))); dialog('受影响格子',`<p>图片覆盖：${escape(a.models.join(' → '))}</p>${pairs.map(p=>`<button data-cm="cell" data-a="${escape(p[0])}" data-b="${escape(p[1])}">${escape(p.join(' / '))}</button>`).join('')||'请先补充图片型号'}`); }
      if(action==='cell') await openCell(button.dataset.a,button.dataset.b);
      if(action==='keep') await saveDecision('keep');
      if(action==='initial') await saveDecision('initialize');
      if(action==='confirm') await saveDecision('replace');
      if(action==='preview') await previewChanges();
      if(action==='apply') { await api('/apply',{decision_ids:preview.ids,token:preview.token}); await refresh(); await executions(); }
      if(action==='executions') await executions();
      if(action==='copy') await navigator.clipboard.writeText(button.dataset.value);
      if(action==='copy-executions') await navigator.clipboard.writeText($('comparisonDialogBody').dataset.copy);
    } finally { button.disabled=false; }
  }));
  document.addEventListener('change',safe(async event=>{
    const el=event.target;
    if(el.id==='cmCategory') { category=el.value; renderMatrix(); }
    if(el.id==='cmCandidate') renderCandidate();
    if(el.dataset.cmDecision) {
      if(el.checked) chosen.add(el.dataset.cmDecision); else chosen.delete(el.dataset.cmDecision);
      const count=document.querySelectorAll('#comparisonMatrixView [data-cm-decision]:checked').length;
      $('cmPreviewChanges').disabled=!count;
      $('cmSelectedCount').textContent=count ? `（${count}）` : '';
    }
    if(el.dataset.cmDraftCategory!==undefined) {
      const index=Number(el.dataset.cmDraftCategory); draft[index].category=el.value; draft[index].models=[];
      if($('cmBatchName')) renderBatch(); else $('cmEditPicker').innerHTML=modelPicker(index,[],el.value);
    }
    if(el.dataset.cmModelIndex!==undefined) {
      const index=Number(el.dataset.cmModelIndex); const values=draft[index].models;
      if(el.checked && !values.includes(el.value)) values.push(el.value);
      if(!el.checked) draft[index].models=values.filter(v=>v!==el.value);
      $('cmOrder'+index).textContent=draft[index].models.join(' → ') || '按图上展示顺序勾选';
    }
  }));
  document.addEventListener('input',event=>{if(event.target.id==='cmImageSearch'){imageSearch=event.target.value; const at=event.target.selectionStart; renderImages(); $('cmImageSearch').focus(); $('cmImageSearch').setSelectionRange(at,at);}});
  window.comparisonUI={switchTab:safe(switchTab)};
})();
