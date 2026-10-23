/* Product image matrix. All confirmations and execution state live on the server. */
(() => {
  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  let state = {catalog: {}, assets: [], cells: []};
  let loaded = false;
  let category = '', rowModel = '', columnModel = '', imageSearch = '', view = 'allLinksView', detail = null, draft = [], preview = null;
  const positions = {};
  const chosen = new Set();
  const selectedTargets = new Map();
  const endpoint = '/api/comparison-matrix';
  let targetIdSearch = '', targetQuestionSearch = '';
  let candidateFilter = 'all', candidateSort = 'newest', candidateView = 'list', selectedCandidateIndex = 0, currentCellPair = [], showAllReferences = false;
  let previousDialogFocus = null;
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
    $('comparisonDialog').classList.remove('cm-confirm-dialog');
    $('comparisonDialogTitle').textContent = title;
    $('comparisonDialogBody').innerHTML = html;
    $('comparisonDialogError').textContent = '';
    if (!$('comparisonDialog').open) {
      previousDialogFocus = document.activeElement;
      $('comparisonDialog').showModal();
      $('comparisonDialog').querySelector('[autofocus]')?.focus();
    }
  }
  $('comparisonDialog').addEventListener('close', () => previousDialogFocus?.focus?.());
  function svg(name) {
    const paths = {close:'<path d="m6 6 12 12M18 6 6 18"/>', left:'<path d="m15 18-6-6 6-6"/>', right:'<path d="m9 18 6-6-6-6"/>', list:'<path d="M8 6h12M8 12h12M8 18h12M3 6h.01M3 12h.01M3 18h.01"/>', grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>', search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>', lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>', image:'<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/>', clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'};
    return `<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths[name] || ''}</svg>`;
  }
  function image(url) {
    return `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer"><img class="cm-thumb" src="${escape(url)}" alt="对比图预览，加载失败可打开链接" loading="lazy" referrerpolicy="no-referrer"></a>`;
  }
  function toolbar() {
    return `<div class="cm-toolbar"><button class="primary-btn" data-cm="batch">新增批次</button><button class="action-btn" data-cm="initialize">初始化历史台账</button><button class="action-btn" data-cm="refresh">刷新</button><button class="action-btn" data-cm="executions">执行清单</button></div>`;
  }
  const categoryPriority = ['扫地机', '洗地机', '洗衣机', '吸尘器'];
  function categories() {
    return Object.keys(state.catalog).sort((a, b) => {
      const ai = categoryPriority.indexOf(a), bi = categoryPriority.indexOf(b);
      if (ai >= 0 || bi >= 0) return (ai < 0 ? categoryPriority.length : ai) - (bi < 0 ? categoryPriority.length : bi);
      return Object.keys(state.catalog).indexOf(a) - Object.keys(state.catalog).indexOf(b);
    });
  }
  function orderedModels() { return [...(state.catalog[category] || [])].reverse(); }
  async function refresh() {
    state = await api('/overview'); loaded = true;
    if (!state.catalog[category]) category = categories()[0] || '';
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
    const models = orderedModels();
    const visibleRows = rowModel ? models.filter(model => model === rowModel) : models;
    const visibleColumns = columnModel ? models.filter(model => model === columnModel) : models;
    const cells = state.cells.filter(c => c.category === category);
    const pending = cells.filter(c => c.decision_id && c.action === 'replace');
    const total = models.length*(models.length-1)/2, configured = cells.filter(c=>c.active_url).length;
    const selected = pending.filter(c=>chosen.has(c.decision_id)).length;
    $('comparisonMatrixView').innerHTML = `<div class="cm-list-header"><div><h3>对比矩阵</h3><p class="cm-list-summary">按品类查看型号对比，点击格子选择图片并确认替换。</p></div>${toolbar()}</div>
      <div class="cm-matrix-controls"><label for="cmCategory">品类 <select id="cmCategory" class="input-modern">${categories().map(c => `<option ${c === category ? 'selected' : ''}>${escape(c)}</option>`).join('')}</select></label><label for="cmRowModel">行型号 <select id="cmRowModel" class="input-modern"><option value="">全部型号</option>${models.map(m => `<option value="${escape(m)}" ${m === rowModel ? 'selected' : ''}>${escape(m)}</option>`).join('')}</select></label><label for="cmColumnModel">列型号 <select id="cmColumnModel" class="input-modern"><option value="">全部型号</option>${models.map(m => `<option value="${escape(m)}" ${m === columnModel ? 'selected' : ''}>${escape(m)}</option>`).join('')}</select></label><div class="cm-matrix-stats"><span><b>${visibleRows.length} × ${visibleColumns.length}</b> 个可见位置 / ${models.length} 个型号</span><span><b>${configured} / ${total}</b> 已配置</span><span><b>${pending.length}</b> 条替换决定</span></div><div class="cm-matrix-legend"><span class="cm-legend-active">已有图片</span><span class="cm-legend-candidate">有候选</span><span class="cm-legend-empty">暂无图片</span></div></div>
      <div class="cm-matrix-hint">A–B 与 B–A 共用一份记录；确认待写入时，当前生效图仍保留。</div>
      <div class="cm-matrix-wrap" id="cmMatrixScroll" role="region" aria-label="${escape(category)}型号对比矩阵" tabindex="0">${models.length ? `<table class="cm-matrix" style="--cm-model-columns:${visibleColumns.length+1}"><thead><tr><th scope="col">型号 / 型号</th>${visibleColumns.map(m=>`<th scope="col">${escape(m)}</th>`).join('')}</tr></thead><tbody>${visibleRows.map(a=>`<tr><th scope="row">${escape(a)}</th>${visibleColumns.map(b=> {
        if(a===b) return '<td class="cm-diagonal" aria-label="同型号不比较"><span>—</span></td>';
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
    targetIdSearch = targetQuestionSearch = '';
    candidateFilter = 'all'; candidateSort = 'newest'; candidateView = 'list'; showAllReferences = false; selectedTargets.clear();
    const current = detail.cell;
    currentCellPair = [a, b];
    selectedCandidateIndex = Math.max(0, detail.candidates.findIndex(v => v.id === (detail.decision?.asset_id || detail.candidates[0]?.id)));
    const batchPending=state.cells.filter(cell=>cell.category===category && !cell.active_url && !cell.decision_id).length;
    const batchConfirmed=state.cells.filter(cell=>cell.category===category && cell.decision_id).length;
    dialog(`${a} / ${b} · 逐格确认`, `<div class="cm-confirm-header-meta"><span>逐格确认</span>对比矩阵 · 产品对比图 <i></i> 本批次待确认 <code>${batchPending}</code> <i></i> 已确认 <code>${batchConfirmed}</code></div><div class="cm-confirm-layout" data-origin-a="${escape(a)}" data-origin-b="${escape(b)}">
      <div class="cm-confirm-main">
        <section class="cm-sec"><div class="cm-sec-title"><strong>当前格</strong><span class="cm-lock-note">${svg('lock')}由矩阵点击定位，不可更改</span></div><div class="cm-current-cell"><span>行 <code>[${escape(modelIndex(a))}]</code> ${escape(a)}</span><i></i><span>列 <code>[${escape(modelIndex(b))}]</code> ${escape(b)}</span><i></i><span class="cm-state ${current.active_url ? 'is-active' : ''}"><b></b>${current.active_url ? '已有旧图 · 可替换' : '缺失 · 待确认'}</span></div>${current.active_url ? `<small class="cm-old-image-note">当前图片：${escape(current.active_url)}</small>` : ''}</section>
        ${detail.historical_conflict ? '<p class="cm-warning">同一型号对存在多张历史图，需人工选择初始图；各 KB 的真实引用继续单独展示。</p>':''}
        <section class="cm-sec"><div class="cm-sec-title"><strong>候选图片 <span class="cm-count" id="cmCandidateCount"></span></strong><div class="cm-view-switch"><button type="button" data-cm-view="list" aria-label="列表视图" title="列表视图">${svg('list')}</button><button type="button" data-cm-view="grid" aria-label="网格视图" title="网格视图">${svg('grid')}</button></div><span class="cm-shortcut-hint">键盘 1–9 快速切换</span></div><div id="cmCandidateFilters" class="cm-candidate-filters"></div><div class="cm-candidate-tools"><span id="cmFilterCounts"></span><label>排序 <select id="cmCandidateSort" aria-label="候选排序"><option value="newest">最新优先</option><option value="oldest">最早优先</option><option value="name">型号排序</option></select></label></div><div id="cmCandidateList" class="cm-candidate-list" role="radiogroup" aria-label="候选图片"></div></section>
        <section class="cm-sec" id="cmOtherRefs"></section>
        <section class="cm-sec"><div class="cm-sec-title"><strong>搜索关联目标</strong><span class="cm-sec-note">已有图片可替换对应位置；没有图片的 KB 会追加新图</span></div><div class="cm-target-search-grid"><label>搜索 KB ID<div class="cm-search-box">${svg('search')}<input id="cmTargetIdSearch" type="search" aria-label="搜索 KB ID" placeholder="输入 KB ID"></div></label><label>搜索问题<div class="cm-search-box">${svg('search')}<input id="cmTargetQuestionSearch" type="search" aria-label="搜索问题" placeholder="输入问题关键词"></div></label></div><p id="cmTargetCount" class="cm-target-count"></p><div id="cmTargetResults" class="cm-target-results"><div class="cm-search-empty">${svg('search')}输入 ID 或问题后显示搜索结果</div></div></section>
        <section class="cm-sec"><div class="cm-sec-title"><strong>确认历史 <span class="cm-count">${detail.history.length} 条</span></strong></div><details class="cm-history"><summary>${svg('clock')}本单元格的操作记录 <span class="cm-count">${detail.history.length}</span><small>确认后将自动追加</small></summary><div class="cm-history-body">${detail.history.length ? detail.history.map(h=>`<div class="cm-history-row"><time>${escape(formatTime(h.created_at))}</time><span>${escape(({keep:'保持旧图',initialize:'历史登记',replace:'替换'})[h.action] || h.action)} · ${escape(h.status)}</span><span>${escape(h.actor || '—')}</span></div>`).join('') : `<div class="cm-history-empty">${svg('clock')}暂无确认记录。完成一次写入后，此处将展示时间、动作与操作人。</div>`}</div></details></section>
      </div><aside class="cm-preview-panel"><div class="cm-preview-panel-head">${svg('image')}图片预览<span id="cmPreviewIndex" class="cm-count"></span></div><div class="cm-preview-image" id="cmPreviewImage"></div><dl id="cmPreviewMeta"></dl></aside></div>
      <footer class="cm-confirm-footer"><p>将写入 <b id="cmWriteCount">0</b> 个位置：${escape(a)} × ${escape(b)}<span class="cm-key-hints"><kbd>↑</kbd><kbd>↓</kbd> 切换候选 <kbd>Enter</kbd> 确认 <kbd>Esc</kbd> 关闭</span></p><div class="cm-footer-actions"><button class="cm-link" data-cm="initial">登记为初始历史图</button><button class="cm-alt" data-cm="keep">保持旧图（保存决定）</button><button class="cm-pri" data-cm="confirm" ${detail.candidates.length ? '' : 'disabled'}>确认所选目标并写入 <span>Enter</span></button></div></footer>`);
    $('comparisonDialog').classList.add('cm-confirm-dialog');
    renderCandidate();
  }
  function modelIndex(model) { return Math.max(0, orderedModels().indexOf(model)); }
  function renderCandidate() {
    const candidate = detail.candidates[selectedCandidateIndex];
    if(candidate && !selectedTargets.has(candidate.id)) {
      const initial = detail.decision?.asset_id===candidate.id ? detail.decision.targets : [];
      selectedTargets.set(candidate.id, new Map(initial.map(target=>{ const normalized=normalizeTarget(target); return [targetKey(normalized), normalized]; })));
    }
    const filterTypes = {all:()=>true,new: a=>Boolean(a.batch_id),history:a=>Boolean(a.historical),pending:a=>a.status!=='使用中'};
    const filtered = detail.candidates.map((item,index)=>({item,index})).filter(({item})=>filterTypes[candidateFilter](item));
    filtered.sort((a,b)=>candidateSort==='oldest' ? String(a.item.created_at).localeCompare(String(b.item.created_at)) : candidateSort==='name' ? a.item.models.join(' ').localeCompare(b.item.models.join(' '),'zh-CN') : String(b.item.created_at).localeCompare(String(a.item.created_at)));
    const filters = [['all','全部'],['new','新品对比图'],['history','历史补图'],['pending','待替换']];
    $('cmCandidateFilters').innerHTML=filters.map(([id,label])=>`<button type="button" data-cm-filter="${id}" class="${candidateFilter===id?'is-active':''}">${label} <span>${id==='all'?detail.candidates.length:detail.candidates.filter(filterTypes[id]).length}</span></button>`).join('');
    $('cmCandidateCount').textContent=`${detail.candidates.length} 个`;
    $('cmFilterCounts').textContent=`显示 ${filtered.length} / ${detail.candidates.length} 个候选`;
    $('cmCandidateSort').value=candidateSort;
    $('cmCandidateList').classList.toggle('is-grid',candidateView==='grid');
    document.querySelectorAll('[data-cm-view]').forEach(el=>el.classList.toggle('is-active',el.dataset.cmView===candidateView));
    $('comparisonDialog').querySelector('[data-cm="confirm"]').disabled=!detail.candidates.length || !(selectedTargets.get(candidate?.id)?.size);
    $('cmCandidateList').innerHTML=filtered.map(({item,index})=>`<button type="button" class="cm-candidate-card ${index===selectedCandidateIndex?'is-selected':''}" role="radio" aria-checked="${index===selectedCandidateIndex}" data-cm-candidate-index="${index}"><span class="cm-number">${index+1}</span><span class="cm-radio"></span><img src="${escape(item.url)}" alt="" loading="lazy" referrerpolicy="no-referrer"><span class="cm-candidate-info"><strong>${escape(item.models.join(' → '))} · ${escape(item.batch_name)}</strong><span class="cm-tags"><em>${item.batch_id?'新品对比图':'历史补图'}</em><em>${escape(String(item.created_at || '').slice(0,10) || '历史')}</em><em>${item.references.length} 处引用${item.references.length?' · 含当前格':''}</em></span><small>${escape(shortUrl(item.url))}</small></span><span class="cm-candidate-status">${escape(item.status==='使用中'?'待替换':'待确认')}</span></button>`).join('') || '<div class="cm-candidate-empty">该位置暂无候选图片</div>';
    renderCandidateDetails(candidate);
  }
  function shortUrl(url) { try { const parsed=new URL(url); return `${parsed.hostname} · ${parsed.pathname.split('/').filter(Boolean).pop() || ''}`; } catch { return url; } }
  function renderCandidateDetails(candidate) {
    const current = detail.cell;
    $('cmPreviewIndex').textContent=candidate ? `候选 ${selectedCandidateIndex+1}` : '暂无候选';
    $('cmPreviewImage').innerHTML=candidate ? `<img src="${escape(candidate.url)}" alt="候选对比图" referrerpolicy="no-referrer">` : '<span>该位置暂无候选图片</span>';
    const coveredModels = candidate?.models || [];
    const pairRefs=[];
    for(let i=0;i<coveredModels.length;i++) for(let j=i+1;j<coveredModels.length;j++) {
      const pair=[coveredModels[i],coveredModels[j]];
      if(pair.includes(currentCellPair[0]) && pair.includes(currentCellPair[1])) continue;
      pairRefs.push(pair);
    }
    const confirmedPairs=new Set(state.cells.filter(cell=>cell.active_asset_id===candidate?.id || cell.pending_asset_id===candidate?.id).map(cell=>JSON.stringify([...cell.pair].sort())));
    const sortedPairRefs=pairRefs.map((pair,index)=>({pair,index,confirmed:confirmedPairs.has(JSON.stringify([...pair].sort()))})).sort((a,b)=>Number(b.confirmed)-Number(a.confirmed));
    const visiblePairRefs=showAllReferences ? sortedPairRefs : sortedPairRefs.slice(0,5);
    const remainingPairRefs=sortedPairRefs.length-visiblePairRefs.length;
    $('cmOtherRefs').innerHTML=`<div class="cm-sec-title"><strong>其他引用位置 <span class="cm-count">${pairRefs.length} 处</span></strong><span class="cm-sec-note">同一 URL 出现多次，需分别确认</span></div>${pairRefs.length ? `<div class="cm-reference-list">${visiblePairRefs.map(({pair,index,confirmed})=>`<div><code>位置 ${index+1}</code><span>${escape(pair[0])} × ${escape(pair[1])}</span><em class="${confirmed?'is-confirmed':''}">${confirmed?'已确认':'待确认'}</em></div>`).join('')}</div>${sortedPairRefs.length>5?`<button type="button" class="cm-reference-more" data-cm-references="${showAllReferences?'less':'more'}">${showAllReferences?'收起':`更多（剩余 ${remainingPairRefs} 处）`}</button>`:''}` : '<p class="cm-only-reference">该图片仅在当前格使用</p>'}<div class="cm-reference-tip">ⓘ 本次仅写入位置 0，其余位置需在矩阵中逐格点击确认。</div>`;
    $('cmPreviewMeta').innerHTML=`<div><dt>当前状态</dt><dd><span class="cm-state ${current.active_url?'is-active':''}"><b></b>${current.active_url?'已有旧图 · 可替换':'缺失 · 待确认'}</span></dd></div><div><dt>覆盖方向</dt><dd class="cm-direction"><span>${escape(detail.cell.pair[0])}</span><small>↓ 覆盖到</small><span>${escape(detail.cell.pair[1])}</span></dd></div><div><dt>写入位置</dt><dd>位置 0 · 当前格（矩阵点击定位）</dd></div><div><dt>图片链接</dt><dd class="cm-preview-url"><span title="${escape(candidate?.url || '')}">${escape(candidate ? shortUrl(candidate.url) : '—')}</span><button type="button" data-cm="copy" data-value="${escape(candidate?.url || '')}">复制</button></dd></div>`;
    const idQuery=targetIdSearch.trim().toLocaleLowerCase(), questionQuery=targetQuestionSearch.trim().toLocaleLowerCase();
    const hasSearch=Boolean(idQuery || questionQuery);
    if(!candidate) { $('cmTargetCount').textContent='已选 0'; $('cmTargetResults').innerHTML='<div class="cm-search-empty">没有可搜索的目标</div>'; $('cmWriteCount').textContent='0'; $('comparisonDialog').querySelector('[data-cm="confirm"]').disabled=true; return; }
    const selected=selectedTargets.get(candidate.id) || new Map();
    const allTargets=candidate.targets.map((target,index)=>({target,index})).filter(({target})=>target.old_url!==candidate.url);
    const matches=allTargets.filter(({target})=>(!idQuery || String(target.kb_id||'').toLocaleLowerCase().includes(idQuery)) && (!questionQuery || String(target.kb_question||'').toLocaleLowerCase().includes(questionQuery)));
    $('cmTargetCount').textContent=`${hasSearch?`匹配 ${matches.length} / ${allTargets.length} 个目标 · `:''}已选 ${selected.size}`;
    $('cmWriteCount').textContent=selected.size;
    $('comparisonDialog').querySelector('[data-cm="confirm"]').disabled=selected.size===0;
    $('cmTargetResults').innerHTML=!hasSearch?`<div class="cm-search-empty">${svg('search')}输入 ID 或问题后显示搜索结果</div>`:matches.length?`<div class="cm-targets">${matches.map(({target,index})=>{const normalized=normalizeTarget(target),append=normalized.target_mode==='append';return `<label class="cm-target"><input type="checkbox" data-cm-target="${index}" ${selected.has(targetKey(normalized))?'checked':''}><span><b>${escape(target.kb_id)}</b> · ${append?'新增关联':`${escape(target.field)}[${target.position}]`} · 版本 ${target.base_version}<br><small>${escape(target.kb_question||'未填写问题')}</small><br>${append?'新图将追加到该 KB 的图片链接':`旧图：${escape(target.old_url)}`}</span></label>`;}).join('')}</div>`:'<div class="cm-search-empty">未找到匹配的 KB，试试其他关键词</div>';
  }
  function normalizeTarget(target) { return {...target,target_mode:target.target_mode || (target.old_url ? 'replace' : 'append')}; }
  function targetKey(target) { return JSON.stringify(['kb_id','field','position','old_url','base_version','target_mode'].map(key=>target[key] ?? null)); }
  async function saveDecision(action) {
    const candidate = detail.candidates[selectedCandidateIndex];
    const selected = [...(candidate ? (selectedTargets.get(candidate.id)?.values() || []) : [])];
    const result=await api('/confirm',{category, pair:detail.cell.pair, base_decision_id:detail.cell.decision_id || null, asset_id:candidate?.id, action, targets:selected});
    if(action==='replace') chosen.add(result.decision_id);
    $('comparisonDialog').close(); await refresh();
  }
  async function previewChanges() {
    const valid=new Set(state.cells.map(c=>c.decision_id));
    const ids=[...chosen].filter(id=>valid.has(id));
    preview=await api('/preview',{decision_ids:ids}); preview.ids=ids;
    const appendCount=preview.groups.reduce((n,g)=>n+new Set(g.entries.filter(e=>e.target_mode==='append').map(e=>e.field+':'+e.position)).size,0);
    const replaceCount=preview.groups.reduce((n,g)=>n+new Set(g.entries.filter(e=>e.target_mode!=='append').map(e=>e.field+':'+e.position)).size,0);
    dialog('KB 修改前后差异', `<p>同一 KB 合并为一次修改。冲突目标会跳过，其余目标可执行。新增图片 ${appendCount} 个位置；替换 ${replaceCount} 个位置；保持旧图 ${preview.keep_count} 格；冲突 ${preview.groups.filter(g=>g.conflicts.length).length} 个 KB。</p>
      ${preview.groups.map(g=>`<section class="cm-diff"><h4>${escape(g.kb_id)} · ${escape(g.status)} · 当前版本 ${g.current_version ?? '—'}</h4>${g.conflicts.map(c=>`<p class="cm-warning">${escape(c)}</p>`).join('')}${g.entries.map(e=>`<p>${escape(e.pair.join(' / '))} · ${escape(e.field)}[${e.position}] · ${e.target_mode==='append'?'新增图片':`替换图片 · 版本 ${e.base_version}`}</p>${e.target_mode==='append'?'<del>无</del>':`<del>${escape(e.old_url)}</del>`}<ins>${escape(e.new_url)}</ins>`).join('')}</section>`).join('')}
      <button class="primary-btn" data-cm="apply">一键应用（实际写入 KB / 恢复清单）</button>`);
  }
  async function executions() {
    const result=await api('/executions');
    dialog('执行清单', `<div class="cm-toolbar"><button data-cm="copy-executions">复制清单</button><a class="action-btn" href="${endpoint}/executions?format=csv" download>导出 CSV</a></div><p>失败与冲突需重新确认；部分成功或待恢复可在矩阵勾选原决定后预览重试。已成功目标不重复修改。</p>
      <div class="cm-table-wrap"><table class="kb-table"><thead><tr><th>批次 / 型号对</th><th>KB / 位置</th><th>旧 → 新</th><th>状态 / 原因</th><th>审计 / 版本</th><th>操作人 / 时间</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td>${escape(r.batch_name)}<br><small>${escape(r.batch_id || '历史')}</small><br>${escape(r.pair.join(' / '))}</td><td>${escape(r.kb_id)}<br>${escape(r.field)}[${r.position}]</td><td class="cm-url">${escape(r.old_url)}<br>→ ${escape(r.new_url)}</td><td>${escape(r.status)}<br>${escape(r.reason)}</td><td>${escape(r.modification_id || '—')}<br>${r.base_version} → ${r.committed_version || '—'}</td><td>${escape(r.actor)}<br>${escape(r.updated_at)}</td></tr>`).join('') || '<tr><td colspan="6">暂无执行记录</td></tr>'}</tbody></table></div>`);
    $('comparisonDialogBody').dataset.copy=JSON.stringify(result.rows,null,2);
  }
  document.addEventListener('click', safe(async event => {
    const referenceButton=event.target.closest('[data-cm-references]');
    if(referenceButton) { showAllReferences=referenceButton.dataset.cmReferences==='more'; renderCandidateDetails(detail.candidates[selectedCandidateIndex]); return; }
    const candidateButton=event.target.closest('[data-cm-candidate-index]');
    if(candidateButton) { selectedCandidateIndex=Number(candidateButton.dataset.cmCandidateIndex); renderCandidate(); return; }
    const filterButton=event.target.closest('[data-cm-filter]');
    if(filterButton) { candidateFilter=filterButton.dataset.cmFilter; renderCandidate(); return; }
    const viewButton=event.target.closest('[data-cm-view]');
    if(viewButton) { candidateView=viewButton.dataset.cmView; document.querySelectorAll('[data-cm-view]').forEach(el=>el.classList.toggle('is-active',el.dataset.cmView===candidateView)); renderCandidate(); return; }
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
    if(el.id==='cmCategory') { category=el.value; rowModel=''; columnModel=''; renderMatrix(); }
    if(el.id==='cmRowModel') { rowModel=el.value; renderMatrix(); }
    if(el.id==='cmColumnModel') { columnModel=el.value; renderMatrix(); }
    if(el.id==='cmCandidateSort') { candidateSort=el.value; renderCandidate(); }
    if(el.dataset.cmTarget!==undefined) {
      const candidate=detail.candidates[selectedCandidateIndex];
      const target=candidate?.targets[Number(el.dataset.cmTarget)];
      if(target) {
        const normalized = normalizeTarget(target);
        const selected=selectedTargets.get(candidate.id) || new Map();
        if(el.checked) selected.set(targetKey(normalized),normalized); else selected.delete(targetKey(normalized));
        selectedTargets.set(candidate.id,selected);
        renderCandidateDetails(candidate);
      }
    }
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
  document.addEventListener('input',event=>{
    const id=event.target.id;
    if(id!=='cmTargetIdSearch' && id!=='cmTargetQuestionSearch') return;
    if(id==='cmTargetIdSearch') targetIdSearch=event.target.value; else targetQuestionSearch=event.target.value;
    const at=event.target.selectionStart;
    renderCandidateDetails(detail.candidates[selectedCandidateIndex]);
    const input=$(id); input.focus(); input.setSelectionRange(at,at);
  });
  document.addEventListener('keydown',event=>{
    if(!$('comparisonDialog').open || !$('comparisonDialog').classList.contains('cm-confirm-dialog')) return;
    const typing=/INPUT|TEXTAREA|SELECT/.test(event.target.tagName) || event.target.isContentEditable;
    if(event.key==='Escape') return;
    if(typing) return;
    if(/^[1-9]$/.test(event.key) && detail.candidates[Number(event.key)-1]) { event.preventDefault(); selectedCandidateIndex=Number(event.key)-1; renderCandidate(); }
    if(event.key==='ArrowDown' || event.key==='ArrowUp') { event.preventDefault(); const count=detail.candidates.length; if(count) { selectedCandidateIndex=(selectedCandidateIndex+(event.key==='ArrowDown'?1:-1)+count)%count; renderCandidate(); } }
    if(event.key==='Enter' && !event.target.closest('button')) { event.preventDefault(); $('comparisonDialog').querySelector('[data-cm="confirm"]')?.click(); }
  });
  window.comparisonUI={switchTab:safe(switchTab)};
})();
