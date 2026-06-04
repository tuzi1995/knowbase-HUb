
// ==========================================
// App Configuration & API
// ==========================================
const API_BASE = '/api';

// ==========================================
// 防抖函数 - 优化性能
// ==========================================
/**
 * 防抖函数：延迟执行，在指定时间内如果再次触发则重新计时
 * @param {Function} func - 要执行的函数
 * @param {number} wait - 延迟时间(毫秒)
 * @param {boolean} immediate - 是否立即执行
 * @returns {Function} 防抖后的函数
 */
function debounce(func, wait = 300, immediate = false) {
  let timeout;
  return function executedFunction(...args) {
    const context = this;
    const later = function() {
      timeout = null;
      if (!immediate) func.apply(context, args);
    };
    const callNow = immediate && !timeout;
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
    if (callNow) func.apply(context, args);
  };
}

/**
 * 节流函数：固定时间内只执行一次
 * @param {Function} func - 要执行的函数
 * @param {number} wait - 间隔时间(毫秒)
 * @returns {Function} 节流后的函数
 */
function throttle(func, wait = 300) {
  let timeout;
  let previous = 0;
  return function executedFunction(...args) {
    const context = this;
    const now = Date.now();
    const remaining = wait - (now - previous);
    if (remaining <= 0 || remaining > wait) {
      if (timeout) {
        clearTimeout(timeout);
        timeout = null;
      }
      previous = now;
      func.apply(context, args);
    } else if (!timeout) {
      timeout = setTimeout(() => {
        previous = Date.now();
        timeout = null;
        func.apply(context, args);
      }, remaining);
    }
  };
}

async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin' };
  if (body) opts.body = JSON.stringify(body);
  
  const url = API_BASE + path;
  const isGet = method.toUpperCase() === 'GET';
  
  async function doFetch() {
    let res;
    try {
      res = await fetch(url, opts);
    } catch (e) {
      const msg = (e && e.message) ? e.message : String(e);
      throw new Error(`请求失败: ${url} (${msg})`);
    }
    
    if (res.status === 401) {
      showLogin(true);
      throw new Error('Unauthorized');
    }
    
    const text = await res.text();
    try {
      const obj = text ? JSON.parse(text) : {};
      // attach minimal meta for debugging without affecting normal UI
      if (obj && typeof obj === 'object') {
        try {
          Object.defineProperty(obj, '__meta', { value: { status: res.status, url }, enumerable: false });
        } catch { }
        if (Array.isArray(obj.warnings) && obj.warnings.length && typeof showToast === 'function') {
          showToast(obj.warnings.join('\n'), 'warning');
        }
      }
      return obj;
    } catch (e) {
      throw new Error(`响应不是 JSON: ${url} (HTTP ${res.status})`);
    }
  }
  
  if (!isGet) return doFetch();
  
  try {
    return await doFetch();
  } catch (e) {
    await new Promise(r => setTimeout(r, 400));
    return await doFetch();
  }
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Global State
let currentUser = null;
let currentTab = 'kbView';

// Link View State
let currentLinks = [];
let linksLoaded = false;
let activeFilterTags = [];
let selectedIds = new Set();
let linkCurrentPage = 1;
let linkPageSize = 20;
let linkShowDuplicateUrlsOnly = false;
let linkSortBy = 'createdAt';
let linkSortDir = 'desc';
let bulkPendingUrls = [];
let bulkPendingTags = [];
let duplicateGroupsCache = [];
let allTags = []; // Global tags cache
const LINK_TABLE_STORAGE_KEY = 'link_table_config';
const LINK_TABLE_DEFAULT_WIDTHS = {
  checkbox: 40,
  preview: 320,
  kb_id: 200,
  url: 560,
  type: 140,
  tags: 280,
  action: 110
};
let linkTableWidths = loadLinkTableWidths();

function loadLinkTableWidths() {
  try {
    const raw = localStorage.getItem(LINK_TABLE_STORAGE_KEY);
    if (!raw) return { ...LINK_TABLE_DEFAULT_WIDTHS };
    const parsed = JSON.parse(raw);
    return { ...LINK_TABLE_DEFAULT_WIDTHS, ...(parsed || {}) };
  } catch {
    return { ...LINK_TABLE_DEFAULT_WIDTHS };
  }
}

function saveLinkTableWidths() {
  try {
    localStorage.setItem(LINK_TABLE_STORAGE_KEY, JSON.stringify(linkTableWidths));
  } catch {}
}

function applyLinkTableWidths() {
  const table = document.getElementById('linkTable');
  if (!table) return;
  const colgroup = document.getElementById('linkTableColgroup');
  if (colgroup) {
    colgroup.querySelectorAll('col[data-col-key]').forEach(col => {
      const key = col.dataset.colKey;
      const width = Number(linkTableWidths[key] || LINK_TABLE_DEFAULT_WIDTHS[key] || 120);
      col.style.width = `${width}px`;
    });
  }
  table.querySelectorAll('th[data-col-key]').forEach(th => {
    const key = th.dataset.colKey;
    const width = Number(linkTableWidths[key] || LINK_TABLE_DEFAULT_WIDTHS[key] || 120);
    th.style.width = `${width}px`;
    th.style.minWidth = `${width}px`;
  });
}

function _isSysLinkTag(tag) {
    const t = String(tag || '');
    return t.startsWith('来源:') || t.startsWith('外链类型:');
}

function _getLinkSysMeta(item) {
    const tags = Array.isArray(item?.tags) ? item.tags : [];
    let source = '';
    let externalType = '';
    tags.forEach(t => {
        const s = String(t || '').trim();
        if (!s) return;
        if (s.startsWith('来源:')) source = s.slice('来源:'.length).trim();
        if (s.startsWith('外链类型:')) externalType = s.slice('外链类型:'.length).trim();
    });
    return { source, externalType };
}

function _getLinkSourceLabel(item) {
    const meta = _getLinkSysMeta(item);
    if (meta.source) {
        if (meta.source === '外部链接' && meta.externalType) return `外部链接(${meta.externalType})`;
        return meta.source;
    }
    const t = String(item?.type || '').toLowerCase();
    if (t === 'image') return '图片链接';
    if (t === 'video' || t === 'youtube') return '视频链接';
    if (t === 'file') return '文件链接';
    return '外部链接';
}

async function fetchGlobalTags() {
    try {
        const res = await api('/tags');
        if (Array.isArray(res)) {
            allTags = res.filter(t => !_isSysLinkTag(t));
        }
    } catch (e) {
        console.error('Failed to load tags:', e);
    }
}

// KB View State
let currentKBData = [];
let kbTotal = 0;
let kbCurrentPage = 1;
let kbPageSize = 50;
let selectedKBRows = new Set();
let kbSelectedProductCategories = new Set();
let kbSelectedTags = new Set();
let kbAllTags = [];
let kbSortBy = 'question_wiki_id';
let kbSortDir = 'desc';
let kbShowSelectedOnly = false;
let dangerConfirmResolver = null;
let kbEditCloseConfirmResolver = null;

// ==========================================
// 分页预加载缓存系统
// ==========================================
const kbPageCache = new Map();
const CACHE_EXPIRY_MS = 5 * 60 * 1000; // 5分钟缓存过期
const CACHE_MAX_SIZE = 10; // 最多缓存10页

function getCacheKey(page, params) {
    // 生成缓存键，包含页码和所有查询参数
    return `${page}_${params.toString()}`;
}

function getFromCache(cacheKey) {
    const cached = kbPageCache.get(cacheKey);
    if (!cached) return null;
    
    // 检查是否过期
    if (Date.now() - cached.timestamp > CACHE_EXPIRY_MS) {
        kbPageCache.delete(cacheKey);
        return null;
    }
    
    return cached.data;
}

function saveToCache(cacheKey, data) {
    // LRU策略：如果缓存满了，删除最旧的
    if (kbPageCache.size >= CACHE_MAX_SIZE) {
        const firstKey = kbPageCache.keys().next().value;
        kbPageCache.delete(firstKey);
    }
    
    kbPageCache.set(cacheKey, {
        data: data,
        timestamp: Date.now()
    });
}

function clearKBCache() {
    kbPageCache.clear();
}

// 预加载下一页（静默执行，不影响UI）
async function prefetchKBNextPage(currentPage, params) {
    try {
        const nextPage = currentPage + 1;
        const totalPages = Math.ceil(kbTotal / kbPageSize);
        
        // 只有在有下一页时才预加载
        if (nextPage > totalPages) return;
        
        // 构建下一页的参数
        const nextParams = new URLSearchParams(params.toString());
        nextParams.set('page', nextPage);
        
        const cacheKey = getCacheKey(nextPage, nextParams);
        
        // 如果已经缓存，跳过
        if (getFromCache(cacheKey)) return;
        
        // 静默请求下一页数据
        const res = await fetch(`${API_BASE}/kb/data?${nextParams.toString()}`, {
            method: 'GET',
            credentials: 'same-origin'
        });
        
        if (!res.ok) return; // 预加载失败不影响主流程
        
        const data = await res.json();
        
        // 保存到缓存
        saveToCache(cacheKey, data);
        
        console.log(`✓ 预加载第 ${nextPage} 页成功`);
    } catch (e) {
        // 预加载失败不影响主流程，静默处理
        console.debug('预加载失败（不影响功能）:', e.message);
    }
}

async function fetchKBAllTags() {
    try {
        // Use raw fetch so we can handle non-JSON (e.g. 404 HTML) gracefully.
        const url = API_BASE + '/kb/tags';
        const resp = await fetch(url, { method: 'GET', credentials: 'same-origin' });
        if (resp.status === 401) {
            showLogin(true);
            throw new Error('Unauthorized');
        }
        const text = await resp.text();
        let json = null;
        try { json = text ? JSON.parse(text) : null; } catch { json = null; }

        if (!resp.ok) {
            const msg = (json && json.message) ? json.message : (text ? String(text).slice(0, 200) : '');
            showToast(`加载标签失败: 后端未提供 /api/kb/tags (HTTP ${resp.status})`, 'error');
            if (msg) console.error('kb/tags error body:', msg);
            kbAllTags = [];
            return;
        }

        if (Array.isArray(json)) {
            kbAllTags = json.map(t => String(t ?? '').trim()).filter(Boolean);
        } else if (json && typeof json === 'object' && json.success === false) {
            showToast('加载标签失败: ' + (json.message || '未知错误'), 'error');
            kbAllTags = [];
        } else {
            kbAllTags = [];
        }
    } catch (e) {
        console.error('Failed to load KB tags:', e);
        try { showToast('加载标签异常: ' + (e?.message || String(e)), 'error'); } catch {}
        kbAllTags = [];
    }
}

let tempKbSelectedTags = new Set();

async function openKbTagFilterModal() {
    const modal = document.getElementById('kbTagFilterModal');
    if (!modal) return;
    
    // sync temp state with actual state
    tempKbSelectedTags = new Set(kbSelectedTags);
    
    // load tags if not loaded
    await fetchKBAllTags();
    
    // render list
    const listContainer = document.getElementById('kbTagFilterModalList');
    listContainer.innerHTML = '';
    
    if (!kbAllTags || kbAllTags.length === 0) {
        listContainer.innerHTML = '<div class="text-muted" style="width: 100%; text-align: center; padding: 20px;">没有可选标签</div>';
    } else {
        kbAllTags.forEach(tag => {
            const label = document.createElement('label');
            label.style.display = 'flex';
            label.style.alignItems = 'center';
            label.style.gap = '6px';
            label.style.padding = '6px 12px';
            label.style.background = '#f8fafc';
            label.style.border = '1px solid #e2e8f0';
            label.style.borderRadius = '16px';
            label.style.cursor = 'pointer';
            label.style.userSelect = 'none';
            label.style.transition = 'all 0.2s';
            
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = tempKbSelectedTags.has(tag);
            cb.onchange = (e) => {
                if (cb.checked) tempKbSelectedTags.add(tag);
                else tempKbSelectedTags.delete(tag);
                
                if (cb.checked) {
                    label.style.background = '#e0e7ff';
                    label.style.borderColor = '#c7d2fe';
                } else {
                    label.style.background = '#f8fafc';
                    label.style.borderColor = '#e2e8f0';
                }
            };
            
            // initial style
            if (cb.checked) {
                label.style.background = '#e0e7ff';
                label.style.borderColor = '#c7d2fe';
            }
            
            const text = document.createElement('span');
            text.textContent = tag;
            text.style.color = '#334155';
            text.style.fontSize = '13px';
            
            label.appendChild(cb);
            label.appendChild(text);
            listContainer.appendChild(label);
        });
    }
    
    modal.style.display = 'flex';
}

function closeKbTagFilterModal() {
    const modal = document.getElementById('kbTagFilterModal');
    if (modal) modal.style.display = 'none';
}

function applyKbTagFilterModal() {
    kbSelectedTags = new Set(tempKbSelectedTags);
    updateKbTagFilterButton();
    closeKbTagFilterModal();
    loadKBTable(1);
}

function clearKbTagFilterModal() {
    tempKbSelectedTags.clear();
    const cbs = document.querySelectorAll('#kbTagFilterModalList input[type="checkbox"]');
    cbs.forEach(cb => {
        cb.checked = false;
        cb.dispatchEvent(new Event('change'));
    });
}

function updateKbTagFilterButton() {
    const countSpan = document.getElementById('kbTagFilterCount');
    const btn = document.getElementById('kbTagFilterModalBtn');
    if (!countSpan || !btn) return;
    
    if (kbSelectedTags.size > 0) {
        countSpan.textContent = kbSelectedTags.size;
        countSpan.style.display = 'inline-block';
        btn.classList.add('is-active');
        btn.style.borderColor = 'var(--primary-color)';
        btn.style.color = 'var(--primary-color)';
    } else {
        countSpan.style.display = 'none';
        btn.classList.remove('is-active');
        btn.style.borderColor = '';
        btn.style.color = '';
    }
}

function setupKBTagDropdown() {
    updateKbTagFilterButton();
}

function updateKBPreviewSelectedButton() {
    const btn = document.getElementById('kbPreviewSelectedBtn');
    if (!btn) return;
    const n = selectedKBRows.size;
    if (kbShowSelectedOnly) {
        btn.classList.add('is-active');
        btn.textContent = n > 0 ? `👁️ 显示全部 (${n})` : '👁️ 显示全部';
        btn.title = '取消仅预览勾选';
    } else {
        btn.classList.remove('is-active');
        btn.textContent = n > 0 ? `👁️ 仅预览勾选 (${n})` : '👁️ 仅预览勾选';
        btn.title = '仅显示已勾选的数据';
    }
}

function toggleKBPreviewSelectedOnly() {
    if (!kbShowSelectedOnly) {
        if (selectedKBRows.size === 0) {
            alert('请先勾选至少一条数据');
            return;
        }
        kbShowSelectedOnly = true;
    } else {
        kbShowSelectedOnly = false;
    }
    loadKBTable(1);
    updateKBPreviewSelectedButton();
}

function showDangerConfirmModal(title, message, confirmText = '确认执行') {
    const modal = document.getElementById('dangerConfirmModal');
    const titleEl = document.getElementById('dangerConfirmTitle');
    const msgEl = document.getElementById('dangerConfirmMessage');
    const confirmBtn = modal ? modal.querySelector('.btn-confirm') : null;
    if (!modal) return Promise.resolve(false);
    if (titleEl) titleEl.textContent = title || '高风险操作确认';
    if (msgEl) msgEl.textContent = message || '确认继续执行该操作吗？';
    if (confirmBtn) confirmBtn.textContent = confirmText || '确认执行';
    modal.style.display = 'block';
    return new Promise((resolve) => {
        dangerConfirmResolver = resolve;
    });
}

function closeDangerConfirmModal(confirmed = false) {
    const modal = document.getElementById('dangerConfirmModal');
    if (modal) modal.style.display = 'none';
    if (dangerConfirmResolver) {
        dangerConfirmResolver(Boolean(confirmed));
        dangerConfirmResolver = null;
    }
}

/** @returns {Promise<'save'|'cancel'|'discard'>} */
function showKbEditUnsavedCloseChoices() {
    const modal = document.getElementById('kbEditCloseConfirmModal');
    if (!modal) return Promise.resolve('cancel');
    modal.style.display = 'block';
    return new Promise((resolve) => {
        kbEditCloseConfirmResolver = resolve;
    });
}

function closeKbEditUnsavedCloseModal(choice) {
    const modal = document.getElementById('kbEditCloseConfirmModal');
    if (modal) modal.style.display = 'none';
    if (kbEditCloseConfirmResolver) {
        const c = choice === 'save' || choice === 'discard' ? choice : 'cancel';
        kbEditCloseConfirmResolver(c);
        kbEditCloseConfirmResolver = null;
    }
}

// KB Table Columns Configuration (Supports Reordering and Visibility)
let kbColumns = [
    { key: 'checkbox', title: '', width: '40px', className: 'col-check', visible: true, fixed: true }, // checkbox always visible
    { key: 'status', title: '修订状态', width: '90px', field: 'review_status', className: 'col-status', visible: true },
    { key: 'id', title: 'ID', field: 'question_wiki_id', sortable: true, width: '180px', className: 'col-id', visible: true },
    { key: 'question', title: '问题', field: 'question', sortable: true, width: '300px', className: 'col-question', visible: true },
    { key: 'answer', title: '答案', field: 'answer', sortable: true, width: '300px', className: 'col-answer', visible: true },
    { key: 'product_name', title: '产品型号', field: 'product_name', sortable: true, width: '120px', className: 'col-product', visible: true },
    { key: 'product_category', title: '产品分类', field: 'product_category_name', width: '100px', className: 'col-category', visible: true },
    { key: 'question_type', title: '问题类型', field: 'question_type', width: '100px', className: 'col-type', visible: true },
    { key: 'answer_type', title: '答案类型', field: 'answer_type', width: '100px', className: 'col-type', visible: true },
    { key: 'similar_questions', title: '相似问题', field: 'similar_questions', type: 'json', width: '150px', className: 'col-similar', visible: true },
    { key: 'bm25', title: 'BM25', field: 'if_bm25', width: '80px', className: 'col-bm25', visible: true },
    { key: 'error_list', title: '错误列表', field: 'error_list', type: 'json', width: '150px', className: 'col-error', visible: true },
    { key: 'keyword_list', title: '关键词', field: 'keyword_list', type: 'json', width: '150px', className: 'col-keyword', visible: true },
    { key: 'image_urls', title: '图片链接', field: 'image_urls', type: 'json', width: '150px', className: 'col-image-urls', visible: true },
    { key: 'video_urls', title: '视频链接', field: 'video_urls', type: 'json', width: '150px', className: 'col-video-urls', visible: true },
    { key: 'file_urls', title: '文件链接', field: 'file_urls', type: 'json', width: '150px', className: 'col-file-urls', visible: true },
    { key: 'link_type', title: '外链类型', field: 'link_type', width: '100px', className: 'col-link-type', visible: true },
    { key: 'link_url', title: '外部链接', field: 'link_url', width: '180px', className: 'col-link-url', visible: true },
    { key: 'update_time', title: '更新时间', field: 'update_time', sortable: true, width: '160px', className: 'col-time', visible: true },
    { key: 'kb_tags', title: '标签', field: 'kb_tags', width: '200px', className: 'col-tags', visible: true }
];

let kbHeaderSignature = '';
let kbResizersBound = false;

// Load saved column widths and visibility
const savedKBConfig = localStorage.getItem('kb_table_config');
if (savedKBConfig) {
    try {
        const config = JSON.parse(savedKBConfig);
        // Load widths
        if (config.widths) {
            kbColumns.forEach(col => {
                if (config.widths[col.key]) {
                    col.width = config.widths[col.key];
                }
            });
        }
        // Load visibility
        if (config.visibility) {
            kbColumns.forEach(col => {
                if (config.visibility[col.key] !== undefined) {
                    col.visible = config.visibility[col.key];
                }
            });
        }
    } catch (e) {
        console.error('Failed to load KB column config', e);
    }
} else {
    // Fallback to old key for backward compatibility
    const savedKBWidths = localStorage.getItem('kb_table_column_widths');
    if (savedKBWidths) {
        try {
            const widths = JSON.parse(savedKBWidths);
            kbColumns.forEach(col => {
                if (widths[col.key]) {
                    col.width = widths[col.key];
                }
            });
        } catch (e) {}
    }
}

function saveKBConfig() {
    const table = document.getElementById('kbTable');
    if (table) {
        const ths = table.querySelectorAll('th');
        let thIndex = 0;
        kbColumns.forEach(col => {
            if (col.visible !== false) {
                if (ths[thIndex]) {
                    col.width = ths[thIndex].style.width;
                }
                thIndex++;
            }
        });
    }
    
    const widths = {};
    kbColumns.forEach(col => {
        widths[col.key] = col.width;
    });

    const visibility = {};
    kbColumns.forEach(col => {
        visibility[col.key] = col.visible;
    });

    localStorage.setItem('kb_table_config', JSON.stringify({ widths, visibility }));
}

// Column Visibility Settings
function openColumnSettingsModal() {
    const modal = document.getElementById('columnSettingsModal');
    const list = document.getElementById('columnSettingsList');
    if (!modal || !list) return;

    list.innerHTML = '';
    
    kbColumns.forEach(col => {
        // Skip checkbox and ID if you want them always visible, but user might want to hide ID
        if (col.key === 'checkbox') return;

        const div = document.createElement('div');
        div.style.display = 'flex';
        div.style.alignItems = 'center';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = 'col-vis-' + col.key;
        checkbox.checked = col.visible !== false;
        checkbox.onchange = () => toggleColumnVisibility(col.key);
        
        const label = document.createElement('label');
        label.htmlFor = 'col-vis-' + col.key;
        label.innerText = col.title || col.key;
        label.style.marginLeft = '8px';
        label.style.cursor = 'pointer';
        
        div.appendChild(checkbox);
        div.appendChild(label);
        list.appendChild(div);
    });
    
    modal.style.display = 'block';
}

function closeColumnSettingsModal() {
    const modal = document.getElementById('columnSettingsModal');
    if (modal) modal.style.display = 'none';
}

function toggleColumnVisibility(key) {
    const col = kbColumns.find(c => c.key === key);
    if (col) {
        col.visible = !col.visible;
        saveKBConfig();
        kbHeaderSignature = '';
        // Re-render table immediately to show effect
        renderKBTableHeader(true);
        renderKBTable();
    }
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('columnSettingsModal');
    if (event.target == modal) {
        modal.style.display = "none";
    }
}

function makeTableResizable(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    // For KB table, we want to save widths to localStorage
    const isKBTable = tableId === 'kbTable';
    const isLinkTable = tableId === 'linkTable';
    
    const ths = table.querySelectorAll('th');
    
    ths.forEach((th, index) => {
        if (th.querySelector('.resizer')) return;
        
        // Skip checkbox column for resizing if desired
        // if (th.classList.contains('col-checkbox')) return;
        
        const resizer = document.createElement('div');
        resizer.classList.add('resizer');
        th.appendChild(resizer);
        
        let x = 0;
        let w = 0;
        
        const mouseDownHandler = function(e) {
            e.stopPropagation();
            x = e.clientX;
            const styles = window.getComputedStyle(th);
            w = parseInt(styles.width, 10);
            
            document.addEventListener('mousemove', mouseMoveHandler);
            document.addEventListener('mouseup', mouseUpHandler);
            resizer.classList.add('resizing');
        };
        
        const mouseMoveHandler = function(e) {
            const dx = e.clientX - x;
            // 不限制最短列宽，支持自定义拖拽
            const newWidth = Math.max(20, w + dx); 
            th.style.width = `${newWidth}px`;
            th.style.minWidth = '0'; 
            const colKey = th.dataset.colKey;
            if (isLinkTable && colKey) {
                linkTableWidths[colKey] = newWidth;
                const col = table.querySelector(`col[data-col-key="${colKey}"]`);
                if (col) col.style.width = `${newWidth}px`;
                th.style.minWidth = `${newWidth}px`;
            }
            
            if (isKBTable) {
                // updateStickyColumns();
            }
        };
        
        const mouseUpHandler = function() {
            document.removeEventListener('mousemove', mouseMoveHandler);
            document.removeEventListener('mouseup', mouseUpHandler);
            resizer.classList.remove('resizing');
            
            // Save width if it's KB table
            if (isKBTable) {
                saveKBConfig();
                // updateStickyColumns();
            }
            if (isLinkTable) {
                saveLinkTableWidths();
            }
        };
        
        resizer.addEventListener('mousedown', mouseDownHandler);
    });
}

function updateStickyColumns() {
    // Deprecated: Sticky columns removed due to rendering issues
    return;
}

// saveKBColumnWidths removed as it is replaced by saveKBConfig

// Matrix View State
let currentMatrixData = [];
let matrixColumns = [];
let matrixTotal = 0;
let matrixCurrentPage = 1;
let matrixPageSize = 20;
let selectedMatrixRows = new Set();
let matrixFilteredTotal = null;
let matrixFilteredTotalRequestSeq = 0;
let matrixDiffCompareEnabled = false;
let matrixLoaded = false;
let matrixLastRequestKey = '';

// Scoring View State
let currentScoringData = [];
let scoringTotal = 0;
let scoringPage = 1;
let scoringPageSize = 50;
let selectedScoringRows = new Set();
let scoringLoaded = false;
let scoringProgressTimer = null;
let scoringRunState = {
    active: false,
    paused: false,
    pauseRequested: false,
    label: '',
    total: 0,
    processed: 0,
    success: 0,
    errors: 0,
    startedAt: null,
    lastErrors: [],
    failedIds: new Set(),
    pendingIds: [],
    options: {},
    batchSize: 20,
    kind: '',
    activeIds: new Set()
};

// ==========================================
// Authentication
// ==========================================
function showLogin(show) {
  const loginPanel = document.getElementById('loginPanel');
  const mainContent = document.getElementById('mainContent');
  
  if (loginPanel) {
      if (show) {
          loginPanel.style.display = '';
          loginPanel.classList.remove('d-none');
      } else {
          loginPanel.style.display = 'none';
          loginPanel.classList.add('d-none');
      }
  }
  
  if (mainContent) {
      if (show) {
          mainContent.style.display = 'none';
          mainContent.classList.add('d-none');
      } else {
          mainContent.style.display = '';
          mainContent.classList.remove('d-none');
      }
  }
}

let isLoggingIn = false;
async function handleLogin() {
    if (isLoggingIn) return;
    isLoggingIn = true;
    
    const btn = document.getElementById('loginBtn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '登录中...';
    }
    const u = document.getElementById('username').value;
    const p = document.getElementById('password').value;
    try {
      const res = await fetch('/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: u, password: p })
      });
      const data = await res.json();
      if (data.success) {
        location.reload();
      } else {
        alert('登录失败: ' + (data.message || '未知错误'));
        if (btn) {
            btn.disabled = false;
            btn.textContent = '登录';
        }
        isLoggingIn = false;
      }
    } catch (e) {
      alert('无法连接服务器，请确认后台服务已启动。\n错误信息: ' + e);
      if (btn) {
          btn.disabled = false;
          btn.textContent = '登录';
      }
      isLoggingIn = false;
    }
}
window.handleLogin = handleLogin;

async function logout() {
    await fetch('/logout', { method: 'POST' });
    location.reload();
}

// ==========================================
// Tab Management
// ==========================================
// Tab Management
// ==========================================
const TAB_META = {
    kbView: {
        title: '知识库管理',
        group: '核心数据',
        description: '维护 V1 / V1T-1 知识库内容，支持搜索、编辑、导出与同步。',
    },
    matrixView: {
        title: '机型矩阵管理',
        group: '核心数据',
        description: '管理机型矩阵配置、批量提交变更，并查看提交日志。',
    },
    linkView: {
        title: '多媒体预览',
        group: '核心数据',
        description: '集中维护图片、视频与文件链接，支持筛选、录入与批量导入。',
    },
    scoringView: {
        title: '知识库评分',
        group: '质量管控',
        description: '执行知识库抽样、评分与导出，统一管理评分配置。',
    },
    governanceView: {
        title: '知识库治理',
        group: '质量管控',
        description: '按月份与质量指标治理知识库，查看筛选摘要与召回关联结果。',
    },
    controlCenterView: {
        title: '管控中心',
        group: '质量管控',
        description: '管理质量任务池、原始问题聚合与任务整改闭环。',
    },
    dataSettingsView: {
        title: '数据设置',
        group: '工具与映射',
        description: '集中管理导入、同步、AI 配置、型号库与知识库表格展示设置。',
    },
    modificationsView: {
        title: '修改记录',
        group: '日志与归档',
        description: '查看各模块修改记录、变更明细与提交链路。',
    },
    archiveView: {
        title: '归档管理',
        group: '日志与归档',
        description: '管理归档批次，查询历史记录并执行归档操作。',
    },
    smartMappingView: {
        title: '智能映射',
        group: '工具与映射',
        description: '按准备、比对、人工决策与提交归档的流程处理智能映射任务。',
    },
};

function updateWorkbenchHeader(tabId) {
    const meta = TAB_META[tabId] || {};
    const title = meta.title || '工作台';
    const group = meta.group || '未分组';
    const description = meta.description || '当前模块已切换。';

    const titleEl = document.getElementById('currentModuleTitle');
    if (titleEl) titleEl.textContent = title;

    const descEl = document.getElementById('currentModuleDesc');
    if (descEl) descEl.textContent = description;

    const groupEl = document.getElementById('currentModuleGroup');
    if (groupEl) groupEl.textContent = group;

    const labelEl = document.getElementById('currentModuleLabel');
    if (labelEl) labelEl.textContent = `${group} / ${title}`;

    document.title = `${title} - K-Matrix 助手`;
}

let workbenchSidebarHeightRaf = null;
const WORKBENCH_SIDEBAR_STORAGE_KEY = 'link_viewer_workbench_sidebar_collapsed_v1';
let workbenchSidebarCollapsed = false;

function getWorkbenchSidebarElements() {
    return {
        layout: document.getElementById('workbenchLayout') || document.querySelector('.workbench-layout'),
        sidebar: document.querySelector('.workbench-sidebar'),
        sidebarCard: document.querySelector('.workbench-sidebar-card'),
        headerToggle: document.getElementById('workbenchSidebarToggle'),
        floatToggle: document.getElementById('workbenchSidebarToggleFloat')
    };
}

function syncWorkbenchSidebarToggleState(collapsed) {
    const { headerToggle, floatToggle } = getWorkbenchSidebarElements();
    const headerIcon = headerToggle ? headerToggle.querySelector('i') : null;
    const floatIcon = floatToggle ? floatToggle.querySelector('i') : null;

    if (headerToggle) {
        headerToggle.setAttribute('aria-label', collapsed ? '展开模块导航' : '收起模块导航');
        headerToggle.setAttribute('title', collapsed ? '展开模块导航' : '收起模块导航');
        headerToggle.setAttribute('aria-expanded', String(!collapsed));
    }
    if (floatToggle) {
        floatToggle.setAttribute('aria-label', collapsed ? '展开模块导航' : '收起模块导航');
        floatToggle.setAttribute('title', collapsed ? '展开模块导航' : '收起模块导航');
        floatToggle.setAttribute('aria-expanded', String(!collapsed));
    }
    if (headerIcon) {
        headerIcon.classList.toggle('fa-angle-left', !collapsed);
        headerIcon.classList.toggle('fa-angle-right', collapsed);
    }
    if (floatIcon) {
        floatIcon.classList.toggle('fa-angle-right', collapsed);
        floatIcon.classList.toggle('fa-angle-left', !collapsed);
    }
}

function setWorkbenchSidebarCollapsed(collapsed, options = {}) {
    const { persist = true } = options;
    const { layout, sidebarCard } = getWorkbenchSidebarElements();
    if (!layout) return;

    workbenchSidebarCollapsed = !!collapsed;
    layout.classList.toggle('sidebar-collapsed', workbenchSidebarCollapsed);
    syncWorkbenchSidebarToggleState(workbenchSidebarCollapsed);

    if (sidebarCard && workbenchSidebarCollapsed) {
        sidebarCard.style.removeProperty('height');
        sidebarCard.style.removeProperty('max-height');
    }

    if (persist) {
        try {
            localStorage.setItem(WORKBENCH_SIDEBAR_STORAGE_KEY, workbenchSidebarCollapsed ? '1' : '0');
        } catch (_) {}
    }

    requestAnimationFrame(() => {
        scheduleWorkbenchSidebarHeightUpdate();
        applyWorkbenchLayoutHotfix();
    });
}

function toggleWorkbenchSidebar(forceCollapsed) {
    const nextCollapsed = typeof forceCollapsed === 'boolean'
        ? forceCollapsed
        : !workbenchSidebarCollapsed;
    setWorkbenchSidebarCollapsed(nextCollapsed);
}

function initWorkbenchSidebarState() {
    let collapsed = false;
    try {
        collapsed = localStorage.getItem(WORKBENCH_SIDEBAR_STORAGE_KEY) === '1';
    } catch (_) {}
    setWorkbenchSidebarCollapsed(collapsed, { persist: false });
}

function getElementDocumentTop(el) {
    let top = 0;
    let node = el;
    while (node) {
        top += node.offsetTop || 0;
        node = node.offsetParent;
    }
    return top;
}

function updateWorkbenchSidebarHeight() {
    const sidebar = document.querySelector('.workbench-sidebar');
    const sidebarCard = document.querySelector('.workbench-sidebar-card');
    const layout = document.getElementById('workbenchLayout') || document.querySelector('.workbench-layout');
    if (!sidebar || !sidebarCard) return;

    if (window.innerWidth <= 1180 || (layout && layout.classList.contains('sidebar-collapsed'))) {
        sidebarCard.style.removeProperty('height');
        sidebarCard.style.removeProperty('max-height');
        return;
    }

    // Use the rendered viewport position instead of CSS `top`, because
    // later overrides may force sticky top to 0 while the sidebar still
    // starts below the header during initial layout.
    const sidebarTop = Math.max(0, sidebarCard.getBoundingClientRect().top || 0);
    const main = document.querySelector('main');
    const bottomGap = main ? (parseFloat(window.getComputedStyle(main).paddingBottom) || 0) : 12;
    const availableHeight = Math.max(320, window.innerHeight - sidebarTop - bottomGap);

    sidebarCard.style.height = `${availableHeight}px`;
    sidebarCard.style.maxHeight = `${availableHeight}px`;
}

function scheduleWorkbenchSidebarHeightUpdate() {
    if (workbenchSidebarHeightRaf) cancelAnimationFrame(workbenchSidebarHeightRaf);
    workbenchSidebarHeightRaf = requestAnimationFrame(() => {
        workbenchSidebarHeightRaf = null;
        updateWorkbenchSidebarHeight();
    });
}

function normalizeWorkbenchViews() {
    const viewsWrap = document.querySelector('.workbench-views');
    if (!viewsWrap) return;
    const viewIds = ['kbView', 'matrixView', 'linkView', 'scoringView', 'governanceView', 'controlCenterView', 'dataSettingsView', 'modificationsView', 'archiveView', 'smartMappingView'];
    viewIds.forEach(id => {
        const el = document.getElementById(id);
        if (el && el.parentElement !== viewsWrap) viewsWrap.appendChild(el);
    });
}

function switchTab(tabId) {
    normalizeWorkbenchViews();
    const tabs = ['kbView', 'matrixView', 'linkView', 'scoringView', 'governanceView', 'controlCenterView', 'dataSettingsView', 'modificationsView', 'archiveView', 'smartMappingView'];
    const viewsWrap = document.querySelector('.workbench-views');
    const isQualityControlCenter = tabId === 'controlCenterView';
    [
        document.getElementById('workbenchLayout'),
        document.querySelector('.workbench-main'),
        document.querySelector('.workbench-content-panel'),
        viewsWrap
    ].forEach(el => {
        if (el) el.classList.toggle('qc-active-workbench', isQualityControlCenter);
    });
    
    tabs.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.classList.remove('is-active-view');
            
            if (id === tabId) {
                el.classList.remove('d-none');
                el.classList.add('is-active-view');
                el.style.display = '';
                const section = el.querySelector('.kb-section');
                if (section) section.style.display = '';
            } else {
                el.classList.add('d-none');
                el.style.display = 'none';
            }
        }
    });
    
    // Update buttons - 支持新旧两种class
    document.querySelectorAll('.tab-btn, .tab-modern').forEach(btn => {
        btn.classList.remove('active');
        btn.removeAttribute('aria-current');
        // 移除旧样式
        btn.style.borderBottom = '';
        btn.style.color = '';
    });

    const activeBtn = document.getElementById('tab-' + tabId);
    if (activeBtn) {
        activeBtn.classList.add('active');
        activeBtn.setAttribute('aria-current', 'page');
        // 不再需要内联样式，CSS会处理
    }
    
    currentTab = tabId;
    updateWorkbenchHeader(tabId);
    stopModAutoRefresh();

    if (viewsWrap) viewsWrap.scrollTop = 0;
    window.scrollTo({ top: 0, behavior: 'instant' });
    
    // Load data for the tab
    if (tabId === 'matrixView') {
        if (typeof loadMatrixData === 'function') loadMatrixData(matrixCurrentPage || 1, { reuse: true });
    } else if (tabId === 'linkView') {
        if (typeof loadLinks === 'function') loadLinks({ reuse: true });
    } else if (tabId === 'kbView') {
        if (typeof loadKBTable === 'function') loadKBTable(kbCurrentPage || 1);
    } else if (tabId === 'scoringView') {
        if (typeof isScoringInProgress === 'function' && isScoringInProgress()) {
            if (typeof renderScoringTable === 'function') renderScoringTable(true);
            if (typeof updateScoringStats === 'function') updateScoringStats();
            if (typeof updateScoringProgressUI === 'function') updateScoringProgressUI();
        } else if (typeof loadScoringData === 'function') {
            loadScoringData({ reuse: true });
        }
    } else if (tabId === 'governanceView') {
        if (typeof loadGovMonths === 'function') loadGovMonths('', { reuse: true });
    } else if (tabId === 'controlCenterView') {
        if (typeof qcLoadAll === 'function') qcLoadAll();
    } else if (tabId === 'modificationsView') {
        if (typeof loadModifications === 'function') loadModifications(1);
        const toggle = document.getElementById('modAutoRefreshToggle');
        setModAutoRefreshEnabled(!!toggle && toggle.checked);
    } else if (tabId === 'dataSettingsView') {
        if (typeof updateDataSettingsState === 'function') updateDataSettingsState();
    } else if (tabId === 'archiveView') {
        if (typeof loadArchives === 'function') loadArchives();
    } else if (tabId === 'smartMappingView') {
        if (typeof smInitSmartMapping === 'function') smInitSmartMapping();
    }
    if (typeof enableAllTableDragScroll === 'function') enableAllTableDragScroll();
    if (typeof enableAllTableColumnResize === 'function') enableAllTableColumnResize();
    scheduleWorkbenchSidebarHeightUpdate();
    applyWorkbenchLayoutHotfix();
}

function openDataSettingsImport() {
    switchTab('dataSettingsView');
    const panel = document.getElementById('importKBPanel');
    const view = document.getElementById('dataSettingsView');
    if (panel) {
        panel.classList.remove('d-none');
        if (view && !view.contains(panel)) {
            const section = view.querySelector('.data-settings-section');
            const grid = view.querySelector('.data-settings-grid');
            if (section && grid) section.insertBefore(panel, grid);
            else if (section) section.appendChild(panel);
        }
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function updateDataSettingsState() {
    const panel = document.getElementById('importKBPanel');
    const view = document.getElementById('dataSettingsView');
    if (panel && view && !view.contains(panel)) {
        const section = view.querySelector('.data-settings-section');
        const grid = view.querySelector('.data-settings-grid');
        if (section && grid) section.insertBefore(panel, grid);
        else if (section) section.appendChild(panel);
    }
}

function _hotfixSetStyle(el, styles) {
    if (!el) return;
    Object.entries(styles || {}).forEach(([key, value]) => {
        el.style.setProperty(key, value, 'important');
    });
}

function _hotfixHideIfEmpty(el) {
    if (!el) return;
    const hasVisibleChild = Array.from(el.children || []).some(child => {
        if (!child || child.offsetParent === null) return false;
        return (child.textContent || '').trim() || child.querySelector('input,button,select,textarea');
    });
    if (!hasVisibleChild && !(el.textContent || '').trim()) {
        el.style.setProperty('display', 'none', 'important');
    }
}

function applyWorkbenchLayoutHotfix() {
    const views = document.querySelector('.workbench-views');
    if (!views) return;
    _hotfixSetStyle(views, { 'height': '100%', 'min-height': '0', 'overflow-y': 'auto', 'overflow-x': 'hidden' });

    ['modificationsView', 'archiveView', 'smartMappingView'].forEach(id => {
        const view = document.getElementById(id);
        if (!view || view.classList.contains('d-none') || view.style.display === 'none') return;
        view.classList.add('is-active-view');
        _hotfixSetStyle(view, { 'display': 'flex', 'flex-direction': 'column', 'height': '100%', 'min-height': '0' });
        const section = view.querySelector('.kb-section');
        _hotfixSetStyle(section, { 'display': 'flex', 'flex': '1 1 auto', 'flex-direction': 'column', 'min-height': '0', 'overflow': 'hidden', 'padding': '12px', 'gap': '10px' });
        _hotfixSetStyle(view.querySelector('.kb-section-title'), { 'margin-bottom': '0' });
    });

    // matrixView is now fully styled via CSS in styles.css and extra_styles.css
    // document.querySelectorAll('#matrixView ...') removed

    document.querySelectorAll('#modificationsView .table-container, #archiveView .table-container, #smartMappingView .table-container').forEach(el => {
        _hotfixSetStyle(el, { 'flex': '1 1 auto', 'min-height': '220px', 'overflow': 'auto' });
    });

    document.querySelectorAll('#modificationsView .filter-section, #archiveView .filter-section').forEach(el => {
        _hotfixSetStyle(el, { 'display': 'grid', 'grid-template-columns': 'repeat(auto-fit, minmax(130px, max-content))', 'justify-content': 'start', 'padding': '8px 10px', 'margin-bottom': '8px', 'gap': '8px' });
    });

    document.querySelectorAll('#smartMappingView .kb-header-group').forEach(el => {
        _hotfixSetStyle(el, { 'height': 'auto', 'padding': '10px', 'margin-bottom': '0' });
    });
    document.querySelectorAll('#smartMappingView .sm-two-col').forEach(el => {
        _hotfixSetStyle(el, { 'grid-template-columns': 'repeat(auto-fit, minmax(280px, 1fr))', 'gap': '10px', 'align-items': 'start' });
    });
    document.querySelectorAll('#smartMappingView .sm-card').forEach(el => {
        _hotfixSetStyle(el, { 'padding': '8px', 'margin-bottom': '0' });
    });
}

let smInited = false;
let smCatalog = null;
let smAllModels = [];
let smSelectedModels = new Set();
let smFaqItems = [];
let smKbItems = [];
let smExcelFileObj = null;
let smCompareJobId = null;
let smWorkbenchRows = [];
let smManualSearchRowIdx = null;
let smManualSearchResults = [];
let smLastOperationId = null;
let smWorkbenchFilter = { q: '', model: 'all', matchType: 'all', sort: 'default', page: 1, pageSize: 50 };
let smWorkbenchSelected = new Set();
let smWorkbenchExpanded = new Set();
let smWorkbenchOtherInfoOpen = new Set();
let smWorkbenchEventsBound = false;
let smCacheSaveTimer = null;

function smGetCompareCacheKeys() {
    const u = String(currentUser || '').trim();
    const keys = [];
    if (u) keys.push(`sm_compare_cache_v1:${u}`);
    keys.push('sm_compare_cache_v1:last');
    return keys;
}

function smReadCompareCache() {
    const keys = smGetCompareCacheKeys();
    for (let i = 0; i < keys.length; i++) {
        const k = keys[i];
        try {
            const raw = localStorage.getItem(k);
            if (!raw) continue;
            const data = JSON.parse(raw);
            if (!data || data.v !== 1) continue;
            return data;
        } catch {}
    }
    return null;
}

function smBuildCompareCachePayload() {
    const rows = Array.isArray(smWorkbenchRows) ? smWorkbenchRows.filter(Boolean).map(r => ({
        faq: r.faq,
        match: r.match,
        reason: r.reason,
        decision: r.decision,
        mode: r.mode,
        models: r.models,
        other_info: r.other_info,
        reasonEdited: r.reasonEdited,
        manual_kb_id: r.manual_kb_id,
        other_info_loaded: r.other_info_loaded
    })) : [];
    const selectedModels = Array.from(smSelectedModels || []).filter(Boolean);
    const filter = smWorkbenchFilter && typeof smWorkbenchFilter === 'object'
        ? {
            q: String(smWorkbenchFilter.q || ''),
            model: String(smWorkbenchFilter.model || 'all'),
            matchType: String(smWorkbenchFilter.matchType || 'all'),
            sort: String(smWorkbenchFilter.sort || 'default'),
            page: Math.max(1, Number(smWorkbenchFilter.page || 1)),
            pageSize: Math.max(0, Number(smWorkbenchFilter.pageSize || 50))
        }
        : { q: '', model: 'all', matchType: 'all', sort: 'default', page: 1, pageSize: 50 };
    return {
        v: 1,
        savedAt: Date.now(),
        selectedModels,
        filter,
        rows,
        lastOperationId: smLastOperationId || null,
        summary: {
            total: rows.length,
            submit: rows.filter(r => r && r.decision === 'submit').length,
            skip: rows.filter(r => r && r.decision === 'skip').length
        }
    };
}

function smSaveCompareCache() {
    if (!smWorkbenchRows || smWorkbenchRows.length === 0) return;
    const payload = smBuildCompareCachePayload();
    const keys = smGetCompareCacheKeys();
    let ok = true;
    keys.forEach((k) => {
        try {
            localStorage.setItem(k, JSON.stringify(payload));
        } catch {
            ok = false;
        }
    });
    if (!ok) {
        if (typeof showToast === 'function') showToast('对比缓存写入失败（可能是浏览器存储空间不足）', 'warning');
    }
}

function smScheduleSaveCompareCache() {
    if (smCacheSaveTimer) clearTimeout(smCacheSaveTimer);
    smCacheSaveTimer = setTimeout(() => {
        smCacheSaveTimer = null;
        smSaveCompareCache();
    }, 600);
}

function smRestoreCompareCache() {
    const data = smReadCompareCache();
    if (!data) return false;
    const models = Array.isArray(data.selectedModels) ? data.selectedModels.map(x => String(x || '').trim()).filter(Boolean) : [];
    smSelectedModels = new Set(models);
    smFaqItems = [];
    smKbItems = [];
    smExcelFileObj = null;
    smCompareJobId = null;
    smWorkbenchRows = Array.isArray(data.rows) ? data.rows.filter(Boolean).map((r) => ({
        faq: r.faq || {},
        match: r.match || {},
        reason: r.reason || '',
        decision: r.decision || 'pending',
        mode: r.mode || 'update',
        models: Array.isArray(r.models) ? r.models.filter(Boolean) : [],
        other_info: (r.other_info && typeof r.other_info === 'object') ? r.other_info : {},
        reasonEdited: !!r.reasonEdited,
        manual_kb_id: r.manual_kb_id,
        other_info_loaded: !!r.other_info_loaded
    })) : [];
    if (data.filter && typeof data.filter === 'object') {
        smWorkbenchFilter = {
            ...smWorkbenchFilter,
            q: String(data.filter.q || ''),
            model: String(data.filter.model || 'all'),
            matchType: String(data.filter.matchType || 'all'),
            sort: String(data.filter.sort || 'default'),
            page: Math.max(1, Number(data.filter.page || 1)),
            pageSize: Math.max(0, Number(data.filter.pageSize || 50))
        };
    }
    smWorkbenchSelected = new Set();
    smWorkbenchExpanded = new Set();
    smWorkbenchOtherInfoOpen = new Set();
    smLastOperationId = data.lastOperationId || null;
    smSetStatusText('smExcelStatus', `✅ 已从缓存恢复对比数据（${Number(data.summary?.total || smWorkbenchRows.length) || smWorkbenchRows.length} 条）`);
    smSetProgress(100, '已从缓存恢复');
    return smWorkbenchRows.length > 0;
}

function smClearCompareCache() {
    const keys = smGetCompareCacheKeys();
    keys.forEach((k) => {
        try { localStorage.removeItem(k); } catch {}
    });
    if (typeof showToast === 'function') showToast('已清除本地对比缓存', 'success');
    smSetStatusText('smExcelStatus', '');
    smSetProgress(0, '');
}

function smGetSelectedModels() {
    return Array.from(smSelectedModels);
}

function smSetStatusText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text || '';
}

function smSetProgress(pct, text) {
    const inner = document.getElementById('smProgressInner');
    if (inner) inner.style.width = `${Math.max(0, Math.min(100, pct || 0))}%`;
    smSetStatusText('smProgressText', text || '');
}

function smUpdateReadyState() {
    const compareBtn = document.getElementById('smCompareBtn');
    const submitBtn = document.getElementById('smSubmitBtn');
    const archiveBtn = document.getElementById('smArchiveBtn');
    const exportBtn = document.getElementById('smExportBtn');
    if (compareBtn) compareBtn.disabled = !(smFaqItems.length > 0 && smKbItems.length > 0);
    const hasSubmit = smWorkbenchRows.some(r => r && r.decision === 'submit');
    if (submitBtn) submitBtn.disabled = !hasSubmit;
    if (archiveBtn) archiveBtn.disabled = !smLastOperationId;
    if (exportBtn) exportBtn.disabled = !(smWorkbenchRows && smWorkbenchRows.length > 0);
    const summary = document.getElementById('smSummary');
    if (summary) {
        const total = smWorkbenchRows.length;
        const submit = smWorkbenchRows.filter(r => r.decision === 'submit').length;
        const skip = smWorkbenchRows.filter(r => r.decision === 'skip').length;
        summary.textContent = total ? `共 ${total} 条：待提交 ${submit} 条，已跳过 ${skip} 条` : '';
    }
}

let _smArchiveModalBackup = null;
async function fetchArchivePreview(operationId = null) {
    const qs = operationId ? `?operation_id=${encodeURIComponent(operationId)}` : '';
    const res = await api(`/archives/preview${qs}`);
    if (!res || !res.success) throw new Error(res?.message || '获取归档预览失败');
    return res;
}

async function confirmArchiveImpact(operationId = null) {
    const preview = await fetchArchivePreview(operationId);
    if (!preview.count) {
        throw new Error('没有待归档的修改记录');
    }
    const ok = await showDangerConfirmModal(
        '归档确认',
        `本次将归档 ${preview.count || 0} 条修改记录，并从当前修改记录列表删除 ${preview.delete_count || 0} 条对应记录。\n归档后可在归档管理中查看和导出，但当前列表不会再显示这些记录。确认继续？`,
        '确认归档'
    );
    if (!ok) throw new Error('已取消归档');
    return preview;
}

function smOpenArchiveModal() {
    if (!smLastOperationId) {
        alert('当前没有可归档的提交批次，请先提交修改');
        return;
    }
    const modal = document.getElementById('archiveNameModal');
    const title = modal?.querySelector('.modal-header h3');
    const input = document.getElementById('archiveNameInput');
    const btn = document.getElementById('archiveNameConfirmBtn');

    _smArchiveModalBackup = {
        titleText: title ? title.textContent : null,
        inputKeydown: input ? input.onkeydown : null,
        btnClick: btn ? btn.onclick : null
    };

    openArchiveNameModal(smLastOperationId);

    if (title) title.textContent = '归档本次智能映射提交';
    if (input) {
        const now = new Date();
        const pad2 = (n) => String(n).padStart(2, '0');
        input.value = `SM_${now.getFullYear()}${pad2(now.getMonth() + 1)}${pad2(now.getDate())}_${pad2(now.getHours())}${pad2(now.getMinutes())}${pad2(now.getSeconds())}`;
        input.onkeydown = (e) => {
            if (e && e.key === 'Enter') smConfirmArchiveModal();
        };
    }
    if (btn) btn.onclick = smConfirmArchiveModal;
}

async function smConfirmArchiveModal() {
    const input = document.getElementById('archiveNameInput');
    const btn = document.getElementById('archiveNameConfirmBtn');
    const name = String(input?.value || '').trim();
    if (!name) {
        if (typeof showToast === 'function') showToast('请填写归档批次名称', 'warning');
        else alert('请填写归档批次名称');
        if (input) input.focus();
        return;
    }
    if (btn) btn.disabled = true;
    try {
        const preview = await confirmArchiveImpact(smLastOperationId);
        const res = await api('/smart_mapping/archive', 'POST', {
            batch_name: name,
            operation_id: smLastOperationId,
            confirm_archive: true,
            expected_count: preview.count || 0
        });
        if (res && res.success) {
            closeArchiveNameModal();
            smLastOperationId = null;
            smUpdateReadyState();
            smScheduleSaveCompareCache();
            if (typeof showToast === 'function') showToast(`归档成功：${res.record_count || 0} 条`, 'success');
            else alert(`归档成功：${res.record_count || 0} 条`);
            switchTab('archiveView');
        } else {
            if (typeof showToast === 'function') showToast(res && res.message ? res.message : '归档失败', 'error');
            else alert(res && res.message ? res.message : '归档失败');
        }
    } catch (e) {
        const msg = e && e.message ? e.message : String(e);
        if (typeof showToast === 'function') showToast('归档失败: ' + msg, 'error');
        else alert('归档失败: ' + msg);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function smInitSmartMapping() {
    if (smInited) return;
    smInited = true;

    const dropzone = document.getElementById('smExcelDropzone');
    const fileInput = document.getElementById('smExcelFile');
    if (dropzone && fileInput) {
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            const files = e.dataTransfer && e.dataTransfer.files ? e.dataTransfer.files : [];
            if (files && files[0]) {
                smExcelFileObj = files[0];
                smSetStatusText('smExcelStatus', `已选择：${smExcelFileObj.name}`);
            }
        });
    }

    let restored = false;
    const cache = smReadCompareCache();
    if (cache && Array.isArray(cache.rows) && cache.rows.length > 0) {
        const savedAt = cache.savedAt ? new Date(Number(cache.savedAt)) : null;
        const savedText = savedAt && !Number.isNaN(savedAt.getTime())
            ? savedAt.toLocaleString('zh-CN', { hour12: false })
            : '';
        const msg = [
            `检测到上次智能映射缓存${savedText ? `（保存于 ${savedText}）` : ''}。`,
            '',
            '注意：缓存里的知识库匹配内容可能不是最新（知识库已更新时尤其明显）。',
            '',
            '是否恢复缓存？',
            '- 确定：恢复缓存',
            '- 取消：丢弃并清空缓存'
        ].join('\n');
        if (confirm(msg)) restored = smRestoreCompareCache();
        else smClearCompareCache();
    }
    await smLoadCatalogAndRenderSelector();
    if (restored) smRenderWorkbench();
    smUpdateReadyState();
}

async function smLoadCatalogAndRenderSelector() {
    const host = document.getElementById('smModelSelect');
    if (!host) return;
    host.innerHTML = '<div class="text-muted" style="padding:8px 0;">加载型号库中...</div>';
    try {
        const res = await api('/kb/product_catalog');
        smCatalog = res && res.data ? res.data : (res || {});
        const models = [];
        Object.keys(smCatalog || {}).forEach(cat => {
            const arr = smCatalog[cat];
            if (Array.isArray(arr)) arr.forEach(m => models.push(String(m)));
        });
        smAllModels = Array.from(new Set(models.map(s => s.trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'zh-CN'));
        smRenderModelMultiSelect(host);
    } catch (e) {
        host.innerHTML = `<div class="text-danger" style="padding:8px 0;">加载失败：${escapeHtml(e.message)}</div>`;
    }
}

function smRenderModelMultiSelect(host) {
    const wrap = document.createElement('div');
    wrap.className = 'custom-select-wrapper';

    const select = document.createElement('div');
    select.className = 'custom-select';

    const trigger = document.createElement('div');
    trigger.className = 'custom-select__trigger';
    trigger.style.height = '38px';
    trigger.style.borderRadius = '10px';
    trigger.innerHTML = `<span id="smModelTriggerText" style="color:#333;">请选择型号（可多选）</span><div class="arrow"></div>`;

    const options = document.createElement('div');
    options.className = 'custom-options';
    options.style.maxHeight = '320px';
    options.style.overflowY = 'auto';
    options.style.padding = '10px';

    const topRow = document.createElement('div');
    topRow.style.display = 'flex';
    topRow.style.gap = '10px';
    topRow.style.alignItems = 'center';
    topRow.style.marginBottom = '10px';
    topRow.innerHTML = `
        <input id="smModelSearchInput" type="text" placeholder="搜索型号..." class="form-control" style="height: 32px; width: 220px;">
        <button type="button" class="action-btn" style="height: 32px; padding: 0 12px;" id="smModelClearBtn">清空</button>
        <span class="text-muted" id="smModelCountText"></span>
    `;
    options.appendChild(topRow);

    const list = document.createElement('div');
    list.id = 'smModelOptions';
    list.style.display = 'grid';
    list.style.gridTemplateColumns = 'repeat(auto-fill, minmax(200px, 1fr))';
    list.style.gap = '8px 10px';
    options.appendChild(list);

    function refreshList(filterText) {
        const ft = String(filterText || '').trim().toLowerCase();
        list.innerHTML = '';
        const shown = smAllModels.filter(m => !ft || m.toLowerCase().includes(ft));
        shown.forEach(model => {
            const item = document.createElement('div');
            item.className = 'product-checkbox-item';
            item.innerHTML = `
                <label title="${escapeHtml(model)}" style="display:flex; align-items:flex-start; gap:10px; padding:8px 10px; border:1px solid #f0f0f0; border-radius:10px; cursor:pointer; user-select:none; background:#fff;">
                    <input type="checkbox" ${smSelectedModels.has(model) ? 'checked' : ''} data-model="${escapeHtml(model)}" style="width:16px; height:16px; margin-top:2px;">
                    <span style="flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; color:#333; line-height:1.35;">${escapeHtml(model)}</span>
                </label>
            `;
            list.appendChild(item);
        });

        const countEl = topRow.querySelector('#smModelCountText');
        if (countEl) countEl.textContent = `已选 ${smSelectedModels.size} / 展示 ${shown.length}`;
    }

    function refreshTrigger() {
        const t = document.getElementById('smModelTriggerText');
        if (!t) return;
        const arr = smGetSelectedModels();
        if (arr.length === 0) {
            t.textContent = '请选择型号（可多选）';
        } else if (arr.length <= 2) {
            t.textContent = arr.join(', ');
        } else {
            t.textContent = `${arr.slice(0, 2).join(', ')} 等 ${arr.length} 个`;
        }
    }

    trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        select.classList.toggle('open');
        if (select.classList.contains('open')) {
            refreshList(document.getElementById('smModelSearchInput')?.value);
        }
    });

    document.addEventListener('click', () => {
        select.classList.remove('open');
    });

    options.addEventListener('click', (e) => {
        e.stopPropagation();
    });

    options.addEventListener('change', (e) => {
        const target = e.target;
        if (!target || target.type !== 'checkbox') return;
        const model = target.getAttribute('data-model');
        if (!model) return;
        if (target.checked) smSelectedModels.add(model);
        else smSelectedModels.delete(model);
        refreshTrigger();
        smUpdateReadyState();
    });

    const searchInput = topRow.querySelector('#smModelSearchInput');
    if (searchInput) {
        searchInput.addEventListener('input', () => refreshList(searchInput.value));
    }

    const clearBtn = topRow.querySelector('#smModelClearBtn');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            smSelectedModels = new Set();
            refreshList(searchInput ? searchInput.value : '');
            refreshTrigger();
            smUpdateReadyState();
        });
    }

    select.appendChild(trigger);
    select.appendChild(options);
    wrap.appendChild(select);
    host.innerHTML = '';
    host.appendChild(wrap);
    refreshTrigger();
    refreshList('');
}

function smChooseCompareExcelFile() {
    const input = document.getElementById('smExcelFile');
    if (!input) return;
    input.click();
    input.onchange = () => {
        const f = input.files && input.files[0] ? input.files[0] : null;
        if (f) {
            smExcelFileObj = f;
            smSetStatusText('smExcelStatus', `已选择：${f.name}`);
        }
    };
}

function smDownloadCompareTemplate() {
    const models = smGetSelectedModels();
    if (models.length === 0) {
        alert('请先选择产品型号');
        return;
    }
    const url = `${API_BASE}/smart_mapping/template?table=knowledge_base_v1&models=${encodeURIComponent(models.join(','))}`;
    smSetStatusText('smKbStatus', '生成中...');
    window.location.href = url;
    setTimeout(() => smSetStatusText('smKbStatus', ''), 1200);
}

async function smUploadAndParseCompareExcel() {
    const input = document.getElementById('smExcelFile');
    const btn = document.getElementById('smParseExcelBtn');
    const file = smExcelFileObj || (input && input.files && input.files[0] ? input.files[0] : null);
    if (!file) {
        alert('请选择 .xlsx/.xls 文件');
        return;
    }

    if (btn) btn.disabled = true;
    smSetStatusText('smExcelStatus', '上传并解析中...');
    try {
        const formData = new FormData();
        formData.append('file', file);
        const res = await fetch(API_BASE + '/smart_mapping/excel/parse', {
            method: 'POST',
            body: formData,
            credentials: 'same-origin'
        });
        if (res.status === 401) {
            showLogin(true);
            throw new Error('Unauthorized');
        }
        const data = await res.json();
        if (!data.success) throw new Error(data.message || '解析失败');
        smFaqItems = Array.isArray(data.faq_items) ? data.faq_items : [];
        smKbItems = Array.isArray(data.kb_items) ? data.kb_items : [];
        smSetStatusText('smExcelStatus', `✅ FAQ ${smFaqItems.length} 条 / 知识库 ${smKbItems.length} 条`);
        smResetWorkbench();
    } catch (e) {
        smFaqItems = [];
        smKbItems = [];
        smSetStatusText('smExcelStatus', `❌ ${e.message}`);
        smResetWorkbench();
    } finally {
        if (btn) btn.disabled = false;
        smUpdateReadyState();
    }
}

function smResetWorkbench() {
    smCompareJobId = null;
    smWorkbenchRows = [];
    smWorkbenchSelected = new Set();
    smWorkbenchExpanded = new Set();
    smWorkbenchFilter = { q: '', model: 'all', matchType: 'all', sort: 'default', page: 1, pageSize: smWorkbenchFilter.pageSize || 50 };
    const body = document.getElementById('smWorkbenchBody');
    if (body) body.innerHTML = '<tr><td colspan="11" class="empty-message">请先导入对比Excel</td></tr>';
    smSetProgress(0, '');
    smUpdateWorkbenchToolbarInfo(0, 0, 0);
    smUpdateWorkbenchModelFilter();
    smUpdateWorkbenchSelectedInfo();
    smUpdateReadyState();
}

async function smStartCompare() {
    const btn = document.getElementById('smCompareBtn');
    if (btn) btn.disabled = true;
    smSetProgress(1, '任务创建中...');
    try {
        if (smFaqItems.length === 0 || smKbItems.length === 0) throw new Error('请先导入包含两张工作表的对比Excel');
        const res = await api('/smart_mapping/compare/start', 'POST', {
            table: 'knowledge_base_v1',
            threshold: 0.7,
            faq_items: smFaqItems,
            kb_items: smKbItems
        });
        if (!res || !res.success) throw new Error(res && res.message ? res.message : '启动失败');
        smCompareJobId = res.job_id;
        await smPollCompareStatus();
    } catch (e) {
        smSetProgress(0, `❌ ${e.message}`);
    } finally {
        if (btn) btn.disabled = false;
        smUpdateReadyState();
    }
}

async function smPollCompareStatus() {
    if (!smCompareJobId) return;
    const jobId = smCompareJobId;
    while (true) {
        const res = await api(`/smart_mapping/compare/status?job_id=${encodeURIComponent(jobId)}`);
        if (!res || !res.success) throw new Error(res && res.message ? res.message : '任务状态获取失败');
        const total = Number(res.total || 0);
        const done = Number(res.done || 0);
        const pct = total > 0 ? Math.round((done / total) * 100) : 0;
        if (res.status === 'running') {
            smSetProgress(Math.max(1, pct), `比对中：${done}/${total}`);
            await new Promise(r => setTimeout(r, 350));
            continue;
        }
        if (res.status === 'failed') {
            throw new Error(res.message || '比对失败');
        }
        if (res.status === 'done') {
            smSetProgress(100, `完成：${done}/${total}`);
            smWorkbenchRows = Array.isArray(res.results) ? res.results : [];
            smWorkbenchRows = smWorkbenchRows.map((r) => {
                const faq = (r && r.faq) ? r.faq : {};
                const raw = String(faq.models_raw || '').trim();
                const rowModels = raw ? raw.split(/[,，]/).map(s => String(s || '').trim()).filter(Boolean) : [];
                return {
                    ...r,
                    models: rowModels,
                    decision: 'pending',
                    mode: r && r.match && r.match.type === '无匹配' ? 'create' : 'update',
                    reasonEdited: false
                };
            });
            smWorkbenchSelected = new Set();
            smWorkbenchExpanded = new Set();
            smWorkbenchFilter = {
                q: '',
                model: 'all',
                matchType: 'all',
                sort: 'default',
                page: 1,
                pageSize: smWorkbenchFilter.pageSize || 50
            };
            smRenderWorkbench();
            smUpdateReadyState();
            smSaveCompareCache();
            return;
        }
        throw new Error('未知任务状态');
    }
}

function smStatusBadge(type) {
    if (type === '问题+答案均一致') return '<span class="sm-badge ok">🟢 问题+答案均一致</span>';
    if (type === '仅问题一致') return '<span class="sm-badge warn">🟡 仅问题一致</span>';
    if (type === '仅答案一致') return '<span class="sm-badge warn">🟡 仅答案一致</span>';
    return '<span class="sm-badge bad">🔴 无匹配</span>';
}

function smStripNumberPrefix(s) {
    const t = String(s || '');
    return t
        .replace(/^\s*[\(\（]?\s*\d+\s*[\)\）]?\s*/, '')
        .replace(/^\s*\d+\s*[\.、]\s*/, '')
        .replace(/^\s*[一二三四五六七八九十]+\s*[、\.]\s*/, '');
}

function smRemovePunctAndSpace(s) {
    return String(s || '')
        .replace(/[\s\u3000]+/g, '')
        .replace(/[，,。．\.\!\！\?\？；;：:“”"'‘’（）()\[\]{}【】<>《》、\/\\|—\-_\~`·…]+/g, '');
}

function smStripParticlesEnd(s) {
    return String(s || '').replace(/[啊呀吧呢嘛哦哈]+$/g, '');
}

function smSortLines(s) {
    const raw = String(s || '');
    const parts = raw.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
    if (parts.length <= 1) return raw;
    parts.sort();
    return parts.join('\n');
}

function smNormForSim(s) {
    return smRemovePunctAndSpace(smStripParticlesEnd(smSortLines(smStripNumberPrefix(s))));
}

function smDetectDiffType(a, b) {
    const a0 = String(a || '');
    const b0 = String(b || '');
    if (!a0 || !b0) return '标点';
    if (smRemovePunctAndSpace(a0) === smRemovePunctAndSpace(b0) && a0 !== b0) return '标点';
    if (smStripParticlesEnd(a0) === smStripParticlesEnd(b0) && a0 !== b0) return '语气词';
    if (smStripNumberPrefix(a0) === smStripNumberPrefix(b0) && a0 !== b0) return '格式编号';
    if (smSortLines(a0) === smSortLines(b0) && a0 !== b0) return '换行排序';
    return '标点';
}

function smCoreMeaning(s, maxLen = 20) {
    const t = smRemovePunctAndSpace(smStripNumberPrefix(s));
    if (!t) return '核心含义';
    return t.slice(0, maxLen);
}

function smTrimReason(s, maxLen = 80) {
    let out = String(s || '').replace(/ /g, '');
    if (out.length <= maxLen) return out;
    const m = out.match(/「([^」]+)」/);
    if (!m) return out.slice(0, maxLen);
    const core = m[1];
    const keep = Math.max(4, core.length - (out.length - maxLen));
    const core2 = core.slice(0, keep);
    out = out.replace(`「${core}」`, `「${core2}」`);
    return out.slice(0, maxLen);
}

function smBuildReason(matchType, faqQ, faqA, kbQ, kbA) {
    if (matchType === '无匹配') return '未找到语义一致的问题/答案';
    if (matchType === '仅答案一致') {
        const core = smCoreMeaning(faqA);
        return smTrimReason(`答案核心为「${core}」；问题语义不同，无匹配性`);
    }
    if (matchType === '仅问题一致') {
        const diff = smDetectDiffType(faqQ, kbQ);
        const core = smCoreMeaning(faqQ);
        return smTrimReason(`忽略${diff}差异，问题核心为「${core}」；答案核心不一致`);
    }
    let diff = smDetectDiffType(faqQ, kbQ);
    if (diff === '标点') {
        const d2 = smDetectDiffType(faqA, kbA);
        if (d2 !== '标点') diff = d2;
    }
    const core = smCoreMeaning(faqQ);
    return smTrimReason(`忽略${diff}差异，问题/答案核心均为「${core}」`);
}

function smNgrams2(s) {
    const t = String(s || '');
    const grams = new Map();
    if (t.length === 0) return grams;
    if (t.length === 1) {
        grams.set(t, 1);
        return grams;
    }
    for (let i = 0; i < t.length - 1; i++) {
        const g = t.slice(i, i + 2);
        grams.set(g, (grams.get(g) || 0) + 1);
    }
    return grams;
}

function smCosineSim(a, b) {
    const aa = smNgrams2(a);
    const bb = smNgrams2(b);
    if (aa.size === 0 || bb.size === 0) return 0;
    let dot = 0;
    let na = 0;
    let nb = 0;
    aa.forEach((v) => { na += v * v; });
    bb.forEach((v) => { nb += v * v; });
    aa.forEach((va, k) => {
        const vb = bb.get(k) || 0;
        dot += va * vb;
    });
    const denom = Math.sqrt(na) * Math.sqrt(nb);
    if (!denom) return 0;
    return dot / denom;
}

function smPickMatchType(qSim, aSim, threshold = 0.7) {
    const qs = Number(qSim || 0);
    const as = Number(aSim || 0);
    if (qs >= threshold && as >= threshold) return '问题+答案均一致';
    if (qs >= threshold && as < threshold) return '仅问题一致';
    if (as >= threshold && qs < threshold) return '仅答案一致';
    return '无匹配';
}

function smSetWorkbenchFilter(key, value) {
    if (key === 'q') smWorkbenchFilter.q = String(value || '');
    if (key === 'model') smWorkbenchFilter.model = String(value || 'all');
    if (key === 'matchType') smWorkbenchFilter.matchType = String(value || 'all');
    if (key === 'sort') smWorkbenchFilter.sort = String(value || 'default');
    if (key === 'pageSize') smWorkbenchFilter.pageSize = Math.max(0, Number(value || 50));
    smWorkbenchFilter.page = 1;
    smRenderWorkbench();
    smScheduleSaveCompareCache();
}

function smPrevWorkbenchPage() {
    smWorkbenchFilter.page = Math.max(1, Number(smWorkbenchFilter.page || 1) - 1);
    smRenderWorkbench();
}

function smNextWorkbenchPage() {
    smWorkbenchFilter.page = Number(smWorkbenchFilter.page || 1) + 1;
    smRenderWorkbench();
}

function smToggleCellExpand(key, e) {
    if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
    const k = String(key || '');
    if (!k) return;
    if (smWorkbenchExpanded.has(k)) smWorkbenchExpanded.delete(k);
    else smWorkbenchExpanded.add(k);
    smRenderWorkbench();
}

function smToggleOtherInfo(idx, e) {
    if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
    const i = Number(idx);
    if (!Number.isFinite(i)) return;
    if (smWorkbenchOtherInfoOpen.has(i)) {
        smWorkbenchOtherInfoOpen.delete(i);
        smRenderWorkbench();
        return;
    }
    smWorkbenchOtherInfoOpen.add(i);
    smEnsureRowOtherInfoLoaded(i).finally(() => smRenderWorkbench());
}

function smEditOtherInfo(idx, field, value) {
    const row = smWorkbenchRows?.[idx];
    if (!row) return;
    const f = String(field || '').trim();
    if (!f) return;
    row.other_info = row.other_info && typeof row.other_info === 'object' ? row.other_info : {};
    row.other_info[f] = value;
    smScheduleSaveCompareCache();
}

async function smEnsureRowOtherInfoLoaded(idx) {
    const row = smWorkbenchRows?.[idx];
    if (!row) return;
    if (row.other_info_loaded) return;

    row.other_info = row.other_info && typeof row.other_info === 'object' ? row.other_info : {};
    const kbId = String(row.match?.kb_id || '').trim();
    if (!kbId) {
        row.other_info_loaded = true;
        return;
    }

    try {
        const res = await api(`/kb/item?table=knowledge_base_v1&id=${encodeURIComponent(kbId)}`);
        if (res && res.success && res.data && typeof res.data === 'object') {
            const d = res.data;
            row.other_info.question_type = d.question_type ?? '';
            row.other_info.if_bm25 = d.if_bm25 ?? '';
            row.other_info.similar_questions = d.similar_questions ?? '';
            row.other_info.keyword_list = d.keyword_list ?? '';
            row.other_info.image_urls = d.image_urls ?? '';
            row.other_info.video_urls = d.video_urls ?? '';
            row.other_info.file_urls = d.file_urls ?? '';
            row.other_info.link_type = d.link_type ?? '';
            row.other_info.link_url = d.link_url ?? '';
        }
    } catch {}

    row.other_info_loaded = true;
}

function smUpdateWorkbenchSelectedInfo() {
    const el = document.getElementById('smWorkbenchSelectedInfo');
    if (!el) return;
    const n = smWorkbenchSelected ? smWorkbenchSelected.size : 0;
    el.textContent = n ? `已选 ${n} 条` : '';
}

function smClearWorkbenchSelection() {
    smWorkbenchSelected = new Set();
    smRenderWorkbench();
}

function smBatchMarkSubmit() {
    if (!smWorkbenchSelected || smWorkbenchSelected.size === 0) return;
    Array.from(smWorkbenchSelected).forEach(idx => {
        const row = smWorkbenchRows[idx];
        if (row) row.decision = 'submit';
    });
    smWorkbenchSelected = new Set();
    smUpdateReadyState();
    smRenderWorkbench();
    smScheduleSaveCompareCache();
}

function smBatchMarkSkip() {
    if (!smWorkbenchSelected || smWorkbenchSelected.size === 0) return;
    Array.from(smWorkbenchSelected).forEach(idx => {
        const row = smWorkbenchRows[idx];
        if (row) row.decision = 'skip';
    });
    smWorkbenchSelected = new Set();
    smUpdateReadyState();
    smRenderWorkbench();
    smScheduleSaveCompareCache();
}

function smUpdateWorkbenchToolbarInfo(total, from, to) {
    const el = document.getElementById('smWorkbenchPageInfo');
    if (!el) return;
    const t = Number(total || 0);
    if (!t) {
        el.textContent = '';
        return;
    }
    const f = Math.max(0, Number(from || 0));
    const tt = Math.max(0, Number(to || 0));
    const ps = Number(smWorkbenchFilter.pageSize || 0);
    const pages = ps > 0 ? Math.max(1, Math.ceil(t / ps)) : 1;
    const p = Math.max(1, Math.min(pages, Number(smWorkbenchFilter.page || 1)));
    el.textContent = `第 ${p}/${pages} 页 · ${f}-${tt} / ${t}`;
}

function smUpdateWorkbenchModelFilter() {
    const sel = document.getElementById('smWorkbenchModelFilter');
    if (!sel) return;
    const models = new Set();
    (smWorkbenchRows || []).forEach(r => {
        const ms = Array.isArray(r?.models) ? r.models : [];
        ms.forEach(m => { if (m) models.add(String(m)); });
    });
    const list = Array.from(models).sort((a, b) => a.localeCompare(b, 'zh'));
    const cur = String(smWorkbenchFilter.model || 'all');
    sel.innerHTML = ['<option value="all">型号：全部</option>', ...list.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`)].join('');
    sel.value = list.includes(cur) ? cur : 'all';
    if (sel.value !== cur) smWorkbenchFilter.model = sel.value;
}

function smEnsureWorkbenchEvents() {
    if (smWorkbenchEventsBound) return;
    const body = document.getElementById('smWorkbenchBody');
    if (!body) return;
    body.addEventListener('click', (e) => {
        const sel = window.getSelection ? window.getSelection() : null;
        if (sel && !sel.isCollapsed && String(sel.toString() || '').trim()) return;
        const target = e && e.target ? e.target : null;
        if (!target) return;
        if (target.closest('textarea, input, select, button, a')) return;
        const tr = target.closest('tr[data-sm-idx]');
        if (!tr) return;
        const idx = Number(tr.getAttribute('data-sm-idx'));
        if (!Number.isFinite(idx)) return;
        if (smWorkbenchSelected.has(idx)) {
            smWorkbenchSelected.delete(idx);
            tr.classList.remove('sm-row-selected');
        } else {
            smWorkbenchSelected.add(idx);
            tr.classList.add('sm-row-selected');
        }
        smUpdateWorkbenchSelectedInfo();
    });
    smWorkbenchEventsBound = true;
}

function smRefreshWorkbenchOverflow() {
    window.requestAnimationFrame(() => {
        const cells = document.querySelectorAll('.sm-cell[data-cell-key]');
        cells.forEach(cell => {
            const key = cell.getAttribute('data-cell-key') || '';
            if (smWorkbenchExpanded.has(key)) {
                cell.classList.add('is-overflow');
                const ta = cell.querySelector('textarea');
                if (ta) {
                    ta.style.height = 'auto';
                    const h = ta.scrollHeight || 0;
                    if (h) ta.style.height = `${Math.min(520, h)}px`;
                }
                return;
            }
            const el = cell.querySelector('textarea, .sm-readonly-box');
            if (!el) return;
            if (el && el.tagName === 'TEXTAREA') el.style.height = '';
            const overflow = el.scrollHeight > el.clientHeight + 2;
            if (overflow) cell.classList.add('is-overflow');
            else cell.classList.remove('is-overflow');
        });
    });
}

function smGetWorkbenchFilteredIndices() {
    const q = String(smWorkbenchFilter.q || '').trim().toLowerCase();
    const model = String(smWorkbenchFilter.model || 'all');
    const mt = String(smWorkbenchFilter.matchType || 'all');
    const indices = [];
    (smWorkbenchRows || []).forEach((row, idx) => {
        if (!row) return;
        const faq = row.faq || {};
        const match = row.match || {};
        const type = (match.type === '问题+答案均一致' || match.type === '仅问题一致' || match.type === '仅答案一致' || match.type === '无匹配') ? match.type : '无匹配';
        if (mt !== 'all' && type !== mt) return;
        if (model !== 'all') {
            const ms = Array.isArray(row.models) ? row.models : [];
            const ok = ms.some(m => String(m || '') === model) || String(faq.models_text || '').includes(model);
            if (!ok) return;
        }
        if (q) {
            const s = [
                faq.row_number,
                faq.models_text,
                faq.question,
                faq.answer,
                match.kb_id,
                match.kb_question,
                match.kb_answer,
                row.reason
            ].map(x => String(x || '')).join(' ').toLowerCase();
            if (!s.includes(q)) return;
        }
        indices.push(idx);
    });

    const sort = String(smWorkbenchFilter.sort || 'default');
    const scoreOf = (idx) => {
        const r = smWorkbenchRows[idx] || {};
        const m = r.match || {};
        const s = m.score !== undefined && m.score !== null ? Number(m.score) : (Number(m.q_sim || 0) + Number(m.a_sim || 0)) / 2;
        return Number.isFinite(s) ? s : 0;
    };
    const rowNumOf = (idx) => {
        const r = smWorkbenchRows[idx] || {};
        const n = Number(r.faq?.row_number);
        return Number.isFinite(n) ? n : 1e9;
    };
    const decisionRank = (idx) => {
        const d = smWorkbenchRows[idx]?.decision || 'pending';
        if (d === 'pending') return 0;
        if (d === 'submit') return 1;
        return 2;
    };

    if (sort === 'pendingFirst') indices.sort((a, b) => decisionRank(a) - decisionRank(b) || a - b);
    else if (sort === 'rowNumberAsc') indices.sort((a, b) => rowNumOf(a) - rowNumOf(b) || a - b);
    else if (sort === 'matchBestFirst') indices.sort((a, b) => scoreOf(b) - scoreOf(a) || a - b);

    return indices;
}

function smRenderWorkbench() {
    const body = document.getElementById('smWorkbenchBody');
    if (!body) return;
    smUpdateWorkbenchModelFilter();
    smEnsureWorkbenchEvents();
    const all = smGetWorkbenchFilteredIndices();
    const total = all.length;
    if (!total) {
        body.innerHTML = '<tr><td colspan="11" class="empty-message">无可展示数据</td></tr>';
        smUpdateWorkbenchToolbarInfo(0, 0, 0);
        smUpdateWorkbenchSelectedInfo();
        return;
    }

    const pageSize = Number(smWorkbenchFilter.pageSize || 0);
    const pages = pageSize > 0 ? Math.max(1, Math.ceil(total / pageSize)) : 1;
    const page = Math.max(1, Math.min(pages, Number(smWorkbenchFilter.page || 1)));
    smWorkbenchFilter.page = page;
    const start = pageSize > 0 ? (page - 1) * pageSize : 0;
    const end = pageSize > 0 ? Math.min(total, start + pageSize) : total;
    const view = all.slice(start, end);
    smUpdateWorkbenchToolbarInfo(total, start + 1, end);

    body.innerHTML = view.map((idx) => {
        const row = smWorkbenchRows[idx];
        const faq = row.faq || {};
        const match = row.match || {};
        const type = (match.type === '问题+答案均一致' || match.type === '仅问题一致' || match.type === '仅答案一致' || match.type === '无匹配') ? match.type : '无匹配';
        const kbQ = String(match.kb_question || '').trim();
        const kbA = String(match.kb_answer || '').trim();
        const kbId = String(match.kb_id || '').trim();
        const reason = String(row.reason || '').trim();
        const decision = row.decision || 'pending';
        const mode = row.mode || (type === '无匹配' ? 'create' : 'update');
        const otherInfo = row.other_info && typeof row.other_info === 'object' ? row.other_info : {};

        const faqRowNum = faq.row_number !== undefined && faq.row_number !== null ? String(faq.row_number) : '';
        const faqModelText = String(faq.models_text || '未指定');

        const kbIdText = kbId ? kbId : '-';
        const kbQText = kbQ ? kbQ : '';
        const kbAText = kbA ? kbA : '';

        const matchTypeOptions = ['问题+答案均一致', '仅问题一致', '仅答案一致', '无匹配']
            .map(t => `<option value="${escapeHtml(t)}" ${t === type ? 'selected' : ''}>${escapeHtml(t)}</option>`)
            .join('');

        const decisionLabel = decision === 'submit' ? '待提交' : (decision === 'skip' ? '已跳过' : '待处理');
        const rowCls = [
            decision === 'submit' ? 'sm-row-submit' : '',
            decision === 'skip' ? 'sm-row-skip' : '',
            smWorkbenchSelected.has(idx) ? 'sm-row-selected' : ''
        ].filter(Boolean).join(' ');
        const opStatus = decision === 'submit' ? '<div class="sm-op-status">✓ 已采纳</div>' : '';
        const acceptDisabled = type === '无匹配' && mode !== 'create';
        const faqQKey = `${idx}:faq_question`;
        const faqAKey = `${idx}:faq_answer`;
        const kbQKey = `${idx}:kb_question`;
        const kbAKey = `${idx}:kb_answer`;
        const reasonKey = `${idx}:reason`;

        return `
            <tr class="${rowCls}" data-sm-idx="${idx}">
                <td style="text-align:center; font-variant-numeric: tabular-nums;">${escapeHtml(faqRowNum)}</td>
                <td style="text-align:center;">
                    <textarea class="form-control sm-model-input" rows="1" style="text-align:center; font-weight:600;" title="${escapeHtml(faqModelText)}" oninput="smEditFaqModel(${idx}, this.value); smAutoGrowTextarea(this)" ondblclick="smOpenRowText(${idx}, 'faq_models')">${escapeHtml(faqModelText)}</textarea>
                </td>
                <td>
                    <div class="sm-cell ${smWorkbenchExpanded.has(faqQKey) ? 'is-expanded' : ''}" data-cell-key="${escapeHtml(faqQKey)}">
                        <textarea rows="3" style="white-space:pre-wrap;" oninput="smEditFaq(${idx}, 'question', this.value)" ondblclick="smOpenRowText(${idx}, 'faq_question')">${escapeHtml(faq.question || '')}</textarea>
                        <button type="button" class="sm-expand-btn" onclick="smToggleCellExpand('${escapeHtml(faqQKey)}', event)">${smWorkbenchExpanded.has(faqQKey) ? '收起▲' : '展开▼'}</button>
                    </div>
                </td>
                <td>
                    <div class="sm-cell ${smWorkbenchExpanded.has(faqAKey) ? 'is-expanded' : ''}" data-cell-key="${escapeHtml(faqAKey)}">
                        <textarea rows="3" style="white-space:pre-wrap;" oninput="smEditFaq(${idx}, 'answer', this.value)" ondblclick="smOpenRowText(${idx}, 'faq_answer')">${escapeHtml(faq.answer || '')}</textarea>
                        <button type="button" class="sm-expand-btn" onclick="smToggleCellExpand('${escapeHtml(faqAKey)}', event)">${smWorkbenchExpanded.has(faqAKey) ? '收起▲' : '展开▼'}</button>
                    </div>
                </td>
                <td style="text-align:center; font-family:monospace; font-size:12px; font-weight:700; user-select:text; cursor:text;">${escapeHtml(kbIdText)}</td>
                <td>
                    <div class="sm-cell ${smWorkbenchExpanded.has(kbQKey) ? 'is-expanded' : ''}" data-cell-key="${escapeHtml(kbQKey)}">
                        <textarea rows="3" style="white-space:pre-wrap;" placeholder="-" oninput="smEditMatch(${idx}, 'kb_question', this.value)" ondblclick="smOpenRowText(${idx}, 'kb_question')">${escapeHtml(kbQText)}</textarea>
                        <button type="button" class="sm-expand-btn" onclick="smToggleCellExpand('${escapeHtml(kbQKey)}', event)">${smWorkbenchExpanded.has(kbQKey) ? '收起▲' : '展开▼'}</button>
                    </div>
                </td>
                <td>
                    <div class="sm-cell ${smWorkbenchExpanded.has(kbAKey) ? 'is-expanded' : ''}" data-cell-key="${escapeHtml(kbAKey)}">
                        <textarea rows="3" style="white-space:pre-wrap;" placeholder="-" oninput="smEditMatch(${idx}, 'kb_answer', this.value)" ondblclick="smOpenRowText(${idx}, 'kb_answer')">${escapeHtml(kbAText)}</textarea>
                        <button type="button" class="sm-expand-btn" onclick="smToggleCellExpand('${escapeHtml(kbAKey)}', event)">${smWorkbenchExpanded.has(kbAKey) ? '收起▲' : '展开▼'}</button>
                    </div>
                </td>
                <td>
                    <div class="sm-otherinfo">
                        <button type="button" class="action-btn sm-mini-btn" onclick="smToggleOtherInfo(${idx}, event)">其他信息</button>
                        <div class="sm-otherinfo-panel" style="${smWorkbenchOtherInfoOpen.has(idx) ? '' : 'display:none;'}">
                            <div class="sm-otherinfo-row">
                                <label class="form-label">产品型号</label>
                                <input class="form-control" style="height: 34px;" value="${escapeHtml(String(otherInfo.product_name ?? ''))}" oninput="smEditOtherInfo(${idx}, 'product_name', this.value)">
                            </div>
                            <div class="sm-otherinfo-row">
                                <label class="form-label">产品分类</label>
                                <input class="form-control" style="height: 34px;" value="${escapeHtml(String(otherInfo.product_category_name ?? ''))}" oninput="smEditOtherInfo(${idx}, 'product_category_name', this.value)">
                            </div>
                            <div class="sm-otherinfo-row">
                                <label class="form-label">问题类型</label>
                                <input class="form-control" style="height: 34px;" value="${escapeHtml(String(otherInfo.question_type ?? ''))}" oninput="smEditOtherInfo(${idx}, 'question_type', this.value)">
                            </div>
                            <div class="sm-otherinfo-row">
                                <label class="form-label">BM25索引</label>
                                <input class="form-control" style="height: 34px;" value="${escapeHtml(String(otherInfo.if_bm25 ?? ''))}" oninput="smEditOtherInfo(${idx}, 'if_bm25', this.value)">
                            </div>
                            <details class="sm-otherinfo-details">
                                <summary style="padding: 12px; cursor: pointer; font-weight: 600; color: #666; user-select: none; background: #fcfcfc; border-radius: 8px;">更多扩展信息 (相似问题、关键词、JSON数据)</summary>
                                <div class="sm-otherinfo-row" style="margin-top: 10px;">
                                    <label class="form-label">相似问题</label>
                                    <textarea rows="3" class="form-control" oninput="smEditOtherInfo(${idx}, 'similar_questions', this.value)">${escapeHtml(String(otherInfo.similar_questions ?? ''))}</textarea>
                                </div>
                                <div class="sm-otherinfo-row">
                                    <label class="form-label">关键词</label>
                                    <textarea rows="3" class="form-control" oninput="smEditOtherInfo(${idx}, 'keyword_list', this.value)">${escapeHtml(String(otherInfo.keyword_list ?? ''))}</textarea>
                                </div>
                                <div class="sm-otherinfo-row">
                                    <label class="form-label">图片链接</label>
                                    <textarea rows="3" class="form-control" oninput="smEditOtherInfo(${idx}, 'image_urls', this.value)">${escapeHtml(String(otherInfo.image_urls ?? ''))}</textarea>
                                </div>
                                <div class="sm-otherinfo-row">
                                    <label class="form-label">视频链接</label>
                                    <textarea rows="3" class="form-control" oninput="smEditOtherInfo(${idx}, 'video_urls', this.value)">${escapeHtml(String(otherInfo.video_urls ?? ''))}</textarea>
                                </div>
                                <div class="sm-otherinfo-row">
                                    <label class="form-label">文件链接</label>
                                    <textarea rows="3" class="form-control" oninput="smEditOtherInfo(${idx}, 'file_urls', this.value)">${escapeHtml(String(otherInfo.file_urls ?? ''))}</textarea>
                                </div>
                                <div class="sm-otherinfo-row">
                                    <label class="form-label">外链类型</label>
                                    <input class="form-control" style="height: 34px;" value="${escapeHtml(String(otherInfo.link_type ?? ''))}" oninput="smEditOtherInfo(${idx}, 'link_type', this.value)">
                                </div>
                                <div class="sm-otherinfo-row">
                                    <label class="form-label">外部链接</label>
                                    <textarea rows="2" class="form-control" oninput="smEditOtherInfo(${idx}, 'link_url', this.value)">${escapeHtml(String(otherInfo.link_url ?? ''))}</textarea>
                                </div>
                            </details>
                        </div>
                    </div>
                </td>
                <td>
                    <div class="sm-match-cell">
                        <div>${smStatusBadge(type)}</div>
                        <select class="form-control" style="height: 34px; font-size: 12px;" title="${escapeHtml(type)}" onchange="smChangeMatchType(${idx}, this.value)">
                            ${matchTypeOptions}
                        </select>
                        <div class="text-muted" style="font-size:12px;">${escapeHtml(decisionLabel)} ｜ ${mode === 'create' ? '新增' : '更新'}</div>
                    </div>
                </td>
                <td>
                    <div class="sm-cell ${smWorkbenchExpanded.has(reasonKey) ? 'is-expanded' : ''}" data-cell-key="${escapeHtml(reasonKey)}">
                        <textarea rows="3" maxlength="80" style="white-space:pre-wrap;" oninput="smEditReason(${idx}, this.value)" ondblclick="smOpenRowText(${idx}, 'reason')">${escapeHtml(reason)}</textarea>
                        <button type="button" class="sm-expand-btn" onclick="smToggleCellExpand('${escapeHtml(reasonKey)}', event)">${smWorkbenchExpanded.has(reasonKey) ? '收起▲' : '展开▼'}</button>
                    </div>
                </td>
                <td>
                    <div class="sm-op-col">
                        <div class="sm-op-label">操作方式</div>
                        <select class="form-control" style="height: 32px;" onchange="smChangeRowMode(${idx}, this.value)">
                            <option value="update" ${mode === 'update' ? 'selected' : ''}>覆盖</option>
                            <option value="create" ${mode === 'create' ? 'selected' : ''}>作为新条目</option>
                        </select>
                        <button type="button" class="primary-btn sm-accept-btn" style="height: 32px; padding: 0 12px;" onclick="smMarkSubmit(${idx})" ${acceptDisabled ? 'disabled' : ''}>✔️ 采纳</button>
                        <button type="button" class="action-btn sm-skip-btn" style="height: 32px; padding: 0 12px;" onclick="smMarkSkip(${idx})">✖️ 跳过</button>
                        <button type="button" class="action-btn sm-switch-btn" style="height: 32px; padding: 0 12px;" onclick="smOpenSearchModal(${idx})">🔄 换一条</button>
                        ${opStatus}
                    </div>
                </td>
            </tr>
        `;
    }).join('');
    smRefreshModelInputHeights();
    smRefreshWorkbenchOverflow();
    smUpdateWorkbenchSelectedInfo();
}

function smOpenTextModal(title, text) {
    const modal = document.getElementById('smTextModal');
    const titleEl = document.getElementById('smTextModalTitle');
    const bodyEl = document.getElementById('smTextModalBody');
    if (titleEl) titleEl.textContent = String(title || '查看内容');
    if (bodyEl) bodyEl.textContent = String(text || '');
    if (modal) modal.style.display = 'block';
}

function smCloseTextModal() {
    const modal = document.getElementById('smTextModal');
    if (modal) modal.style.display = 'none';
}

function smOpenRowText(idx, field) {
    const row = smWorkbenchRows[idx];
    if (!row) return;
    const faq = row.faq || {};
    const match = row.match || {};
    const map = {
        faq_models: { title: 'FAQ_型号', text: faq.models_text || faq.models_raw || '' },
        faq_question: { title: 'FAQ_问题', text: faq.question || '' },
        faq_answer: { title: 'FAQ_答案', text: faq.answer || '' },
        kb_question: { title: '知识库_问题', text: match.kb_question || '' },
        kb_answer: { title: '知识库_答案', text: match.kb_answer || '' },
        reason: { title: '判定理由', text: row.reason || '' }
    };
    const it = map[field] || { title: '查看内容', text: '' };
    smOpenTextModal(it.title, it.text);
}

function smEditFaq(idx, field, value) {
    const row = smWorkbenchRows[idx];
    if (!row || !row.faq) return;
    if (field !== 'question' && field !== 'answer') return;
    row.faq[field] = value;
    if (row.match && row.match.type && row.match.type !== '无匹配' && !row.reasonEdited) {
        row.reason = smBuildReason(row.match.type, row.faq.question, row.faq.answer, row.match.kb_question, row.match.kb_answer);
    }
    smScheduleSaveCompareCache();
}

function smEditMatch(idx, field, value) {
    const row = smWorkbenchRows[idx];
    if (!row) return;
    row.match = row.match && typeof row.match === 'object' ? row.match : {};
    if (field !== 'kb_question' && field !== 'kb_answer') return;
    row.match[field] = value;
    if (row.match && row.match.type && row.match.type !== '无匹配' && !row.reasonEdited) {
        row.reason = smBuildReason(row.match.type, row.faq?.question, row.faq?.answer, row.match.kb_question, row.match.kb_answer);
    }
    smScheduleSaveCompareCache();
}

function smEditFaqModel(idx, value) {
    const row = smWorkbenchRows[idx];
    if (!row || !row.faq) return;
    const v = String(value || '').trim();
    row.faq.models_raw = v;
    row.faq.models_text = v ? v : '未指定';
    row.models = v ? v.split(/[,，]/).map(s => String(s || '').trim()).filter(Boolean) : [];
    smUpdateReadyState();
    smScheduleSaveCompareCache();
}

function smAutoGrowTextarea(el, maxPx = 120) {
    if (!el || !el.style) return;
    el.style.height = 'auto';
    const h = el.scrollHeight || 0;
    if (!h) return;
    const next = Math.max(34, Math.min(Number(maxPx) || 120, h));
    el.style.height = `${next}px`;
}

function smRefreshModelInputHeights() {
    const els = document.querySelectorAll('textarea.sm-model-input');
    els.forEach(el => smAutoGrowTextarea(el));
}

function smEditReason(idx, value) {
    const row = smWorkbenchRows[idx];
    if (!row) return;
    row.match = row.match || {};
    if (row.match.type === '无匹配') {
        row.reasonEdited = false;
        row.reason = '未找到语义一致的问题/答案';
        smRenderWorkbench();
        smUpdateReadyState();
        smScheduleSaveCompareCache();
        return;
    }
    row.reasonEdited = true;
    row.reason = smTrimReason(String(value || ''));
    smScheduleSaveCompareCache();
}

function smChangeMatchType(idx, matchType) {
    const row = smWorkbenchRows[idx];
    if (!row) return;
    row.match = row.match || {};
    const mt = (matchType === '问题+答案均一致' || matchType === '仅问题一致' || matchType === '仅答案一致' || matchType === '无匹配') ? matchType : '无匹配';
    row.match.type = mt;
    if (mt === '无匹配') {
        row.match.kb_id = '';
        row.match.kb_question = '';
        row.match.kb_answer = '';
        row.match.kb_models = '';
        row.match.q_sim = 0;
        row.match.a_sim = 0;
        row.match.score = 0;
        row.reasonEdited = false;
        row.reason = '未找到语义一致的问题/答案';
        row.mode = 'create';
    } else if (!row.reasonEdited) {
        row.reason = smBuildReason(mt, row.faq?.question, row.faq?.answer, row.match.kb_question, row.match.kb_answer);
    }
    smRenderWorkbench();
    smUpdateReadyState();
    smScheduleSaveCompareCache();
}

function smChangeRowModels(idx, models) {
    const row = smWorkbenchRows[idx];
    if (!row) return;
    row.models = Array.isArray(models) ? models.filter(Boolean) : [];
}

function smChangeRowMode(idx, mode) {
    const row = smWorkbenchRows[idx];
    if (!row) return;
    row.mode = mode === 'create' ? 'create' : 'update';
    smRenderWorkbench();
    smUpdateReadyState();
    smScheduleSaveCompareCache();
}

function smMarkSubmit(idx) {
    const row = smWorkbenchRows[idx];
    if (!row) return;
    row.decision = 'submit';
    smUpdateReadyState();
    smRenderWorkbench();
    smScheduleSaveCompareCache();
}

function smMarkSkip(idx) {
    const row = smWorkbenchRows[idx];
    if (!row) return;
    row.decision = 'skip';
    smUpdateReadyState();
    smRenderWorkbench();
    smScheduleSaveCompareCache();
}

function smMarkAllSkip() {
    smWorkbenchRows.forEach(r => { if (r) r.decision = 'skip'; });
    smUpdateReadyState();
    smRenderWorkbench();
    smScheduleSaveCompareCache();
}

async function smExportResult() {
    if (!smWorkbenchRows || smWorkbenchRows.length === 0) {
        alert('当前没有可导出的结果');
        return;
    }
    try {
        const res = await fetch(API_BASE + '/smart_mapping/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                rows: smWorkbenchRows.map(r => ({
                    faq: r.faq,
                    match: r.match,
                    reason: r.reason
                }))
            }),
            credentials: 'same-origin'
        });
        if (res.status === 401) {
            showLogin(true);
            throw new Error('Unauthorized');
        }
        if (!res.ok) {
            let msg = '导出失败';
            try {
                const data = await res.json();
                if (data && data.message) msg = data.message;
            } catch {}
            throw new Error(msg);
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `智能映射对比结果_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '')}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + (e && e.message ? e.message : String(e)));
    }
}

function smOpenSearchModal(idx) {
    smManualSearchRowIdx = idx;
    const modal = document.getElementById('smSearchModal');
    if (modal) modal.style.display = 'block';
    const body = document.getElementById('smSearchBody');
    if (body) body.innerHTML = '<tr><td colspan="4" class="empty-message">请输入关键词搜索</td></tr>';
    smSetStatusText('smSearchStatus', '');
    const q = document.getElementById('smSearchQ');
    if (q) q.value = '';
}

function smCloseSearchModal() {
    const modal = document.getElementById('smSearchModal');
    if (modal) modal.style.display = 'none';
    smManualSearchRowIdx = null;
}

async function smDoManualSearch() {
    const input = document.getElementById('smSearchQ');
    const q = input ? input.value.trim() : '';
    if (!q) return;
    smSetStatusText('smSearchStatus', '搜索中...');
    const body = document.getElementById('smSearchBody');
    if (body) body.innerHTML = '<tr><td colspan="4" class="empty-message">搜索中...</td></tr>';

    try {
        let items = [];
        try {
            const res = await api(`/smart_mapping/kb/search?table=knowledge_base_v1&q=${encodeURIComponent(q)}&limit=50`);
            if (res && res.success) items = Array.isArray(res.items) ? res.items : [];
        } catch {}

        if (!items || items.length === 0) {
            const kw = q.toLowerCase();
            items = (smKbItems || []).filter(it => {
                const id = String(it.question_wiki_id || it.id || '').toLowerCase();
                const qq = String(it.question || '').toLowerCase();
                const aa = String(it.answer || '').toLowerCase();
                const pp = String(it.product_name || '').toLowerCase();
                return id.includes(kw) || qq.includes(kw) || aa.includes(kw) || pp.includes(kw);
            }).slice(0, 50);
        }
        smManualSearchResults = items;
        smSetStatusText('smSearchStatus', `共 ${items.length} 条（最多展示 50）`);
        if (!body) return;
        if (items.length === 0) {
            body.innerHTML = '<tr><td colspan="4" class="empty-message">无结果</td></tr>';
            return;
        }
        body.innerHTML = items.map((it, i) => `
            <tr>
                <td style="font-family:monospace; font-size:12px;">${escapeHtml(it.question_wiki_id || it.id || '')}</td>
                <td>${escapeHtml(it.question || '')}</td>
                <td>${escapeHtml(it.answer || '')}</td>
                <td><button type="button" class="primary-btn" style="height: 30px; padding: 0 10px;" onclick="smPickManualMatch(${i})">选择</button></td>
            </tr>
        `).join('');
    } catch (e) {
        smSetStatusText('smSearchStatus', `❌ ${e.message}`);
        if (body) body.innerHTML = '<tr><td colspan="4" class="empty-message">搜索失败</td></tr>';
    }
}

function smPickManualMatch(resultIndex) {
    const idx = smManualSearchRowIdx;
    if (idx === null || idx === undefined) return;
    const row = smWorkbenchRows[idx];
    if (!row) return;
    const pick = smManualSearchResults && smManualSearchResults[resultIndex] ? smManualSearchResults[resultIndex] : null;
    if (!pick) return;
    const kbId = String(pick.question_wiki_id || pick.id || '').trim();
    const kbQ = String(pick.question || '').trim();
    const kbA = String(pick.answer || '').trim();
    const kbM = String(pick.product_name || pick.models || pick.models_text || '').trim();
    row.manual_kb_id = kbId;
    row.match = row.match || {};
    row.match.kb_id = kbId;
    row.match.kb_question = kbQ;
    row.match.kb_answer = kbA;
    row.match.kb_models = kbM;
    const fq = smNormForSim(row.faq?.question || '');
    const fa = smNormForSim(row.faq?.answer || '');
    const kq = smNormForSim(kbQ);
    const ka = smNormForSim(kbA);
    const qSim = smCosineSim(fq, kq);
    const aSim = smCosineSim(fa, ka);
    row.match.q_sim = qSim;
    row.match.a_sim = aSim;
    row.match.score = (qSim + aSim) / 2;
    row.match.type = smPickMatchType(qSim, aSim, 0.7);
    row.mode = row.match.type === '无匹配' ? 'create' : (row.mode === 'create' ? 'create' : 'update');
    if (!row.reasonEdited) row.reason = smBuildReason(row.match.type, row.faq?.question, row.faq?.answer, kbQ, kbA);
    row.decision = 'pending';
    smCloseSearchModal();
    smRenderWorkbench();
    smUpdateReadyState();
    smScheduleSaveCompareCache();
}

async function smSubmitChanges() {
    const btn = document.getElementById('smSubmitBtn');
    if (btn) btn.disabled = true;
    try {
        const toSubmit = smWorkbenchRows
            .map((r, idx) => ({ r, idx }))
            .filter(x => x.r && x.r.decision === 'submit')
            .map(x => ({ ...x.r, _idx: x.idx }));

        if (toSubmit.length === 0) throw new Error('没有待提交的数据');

        const invalid = [];
        toSubmit.forEach(x => {
            const faq = x.faq || {};
            const q = String(faq.question || '').trim();
            const a = String(faq.answer || '').trim();
            const models = Array.isArray(x.models) ? x.models.filter(Boolean) : [];
            if (!q || !a || models.length === 0) invalid.push(Number(x._idx) + 1);
        });
        if (invalid.length) throw new Error(`以下行缺少内容确认或型号绑定：${invalid.join(', ')}`);

        smSetStatusText('smSummary', '提交中...');
        const payload = {
            table: 'knowledge_base_v1',
            items: toSubmit.map(x => ({
                faq: x.faq,
                models: x.models,
                mode: x.mode,
                match: x.match,
                reason: smTrimReason(String(x.reason || '')),
                other_info: x.other_info && typeof x.other_info === 'object' ? x.other_info : {}
            }))
        };
        const res = await api('/smart_mapping/submit', 'POST', payload);
        if (!res || !res.success) throw new Error(res && res.message ? res.message : '提交失败');
        const ok = Number(res.success_count || 0);
        const fail = Number(res.failed_count || 0);
        smLastOperationId = res.operation_id || null;
        alert(`提交完成：成功 ${ok} 条，失败 ${fail} 条`);
        smWorkbenchRows.forEach(r => {
            if (r && r.decision === 'submit') r.decision = 'pending';
        });
        smUpdateReadyState();
        smRenderWorkbench();
        smScheduleSaveCompareCache();
        if (typeof loadModifications === 'function') loadModifications(1);
    } catch (e) {
        alert('提交失败: ' + e.message);
    } finally {
        if (btn) btn.disabled = false;
        smUpdateReadyState();
    }
}

// ==========================================
// Link Viewer Logic
// ==========================================
function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function detectType(url) {
  const u = url.toLowerCase();
  if (u.match(/\.(png|jpg|jpeg|gif|webp|svg)(\?.*)?$/)) return 'image';
  if (u.match(/\.(mp4|webm|ogg|mov|m3u8)(\?.*)?$/)) return 'video';
  if (u.includes('youtube.com/watch') || u.includes('youtu.be/')) return 'youtube';
  return 'link';
}

function toYoutubeEmbed(url) {
  try {
    if (url.includes('youtu.be/')) {
      const id = url.split('youtu.be/')[1].split(/[?&]/)[0];
      return `https://www.youtube.com/embed/${id}`;
    }
    const u = new URL(url);
    const v = u.searchParams.get('v');
    if (v) return `https://www.youtube.com/embed/${v}`;
  } catch {}
  return url;
}

function previewUrl(url) {
    if (!url) return;
    const type = detectType(url);
    if (type === 'image') {
        openModal(url);
    } else if (type === 'video' || type === 'youtube') {
        // Enhance openModal to support video
        const modal = document.getElementById('imageModal');
        const modalImg = document.getElementById('modalImg');
        // We might need to change modal structure if it only has img
        // For now, let's just use window.open for video/youtube if modal is img-only
        // Or better, inject video/iframe into modal
        if (modal) {
             const contentContainer = modal.querySelector('.modal-content-container') || modal;
             // Check if we can replace content
             // Since I can't easily change modal HTML structure without seeing it, 
             // and existing openModal sets modalImg.src
             // I'll try to use a simple approach: if it's video/youtube, use window.open for now, 
             // unless I modify openModal.
             // But the user said "与多媒体预览是联动的", which implies using the preview logic.
             // I'll stick to window.open for non-images for safety, or try to implement a better modal later.
             // Actually, I can check if I can modify openModal.
             window.open(url, '_blank');
        }
    } else {
        window.open(url, '_blank');
    }
}

async function loadLinks(options = {}) {
  if (options.reuse && linksLoaded) {
    linkTableWidths = loadLinkTableWidths();
    renderLinkTable();
    return;
  }
  try {
    const [res] = await Promise.all([
        api('/links'),
        fetchGlobalTags()
    ]);
    // Ensure we handle both array (legacy) and object response
    currentLinks = Array.isArray(res) ? res : (res.data || []);
    linksLoaded = true;
    linkTableWidths = loadLinkTableWidths();
    renderLinkTable();
  } catch {}
}

async function addLink(url, tags) {
  const cleanUrl = url.trim();
  if (!cleanUrl) return;
  const item = {
    id: uid(),
    url: cleanUrl,
    type: detectType(cleanUrl),
    tags: tags,
    createdAt: Date.now() / 1000
  };
  const res = await api('/links', 'POST', item);
  if (!res || res.success !== true) {
    throw new Error((res && res.message) ? res.message : '单条导入失败');
  }
  try {
    localStorage.setItem('link_last_manual', JSON.stringify({ id: item.id, url: item.url, createdAt: item.createdAt }));
  } catch {}
  await loadLinks();
  return res;
}

async function addLinksBatch(urls, tags) {
  const cleanUrls = (urls || []).map(u => String(u || '').trim()).filter(Boolean);
  if (cleanUrls.length === 0) return { success: true, count: 0 };
  const base = Date.now() / 1000;
  const items = cleanUrls.map((u, idx) => ({
    id: uid(),
    url: u,
    type: detectType(u),
    tags: tags || [],
    createdAt: base + idx * 0.000001
  }));
  const res = await api('/links/batch', 'POST', items);
  if (!res || res.success !== true) {
    throw new Error((res && res.message) ? res.message : '批量导入失败');
  }
  const last = items[items.length - 1];
  try {
    localStorage.setItem('link_last_manual', JSON.stringify({ id: last.id, url: last.url, createdAt: last.createdAt }));
  } catch {}
  await loadLinks();
  return res;
}

function openLinkImportModal() {
  hideLinkAddError();
  const modal = document.getElementById('linkImportModal');
  if (modal) modal.style.display = 'block';
}

function closeLinkImportModal() {
  const modal = document.getElementById('linkImportModal');
  if (modal) modal.style.display = 'none';
}

async function addSingleWithDuplicateCheck(url, tags) {
  hideLinkAddError();
  const cleanUrl = String(url || '').trim();
  if (!cleanUrl) return false;

  if (!currentLinks || currentLinks.length === 0) {
    await loadLinks();
  }

  const key = normalizeUrlForDup(cleanUrl);
  const exists = key && getExistingUrlKeySet().has(key);
  if (exists) {
    showLinkAddError(`该URL已存在：${cleanUrl}`);
    return false;
  }

  try {
    await addLink(cleanUrl, tags);
    return true;
  } catch (e) {
    showLinkAddError((e && e.message) ? e.message : '添加失败');
    return false;
  }
}

function parseUrlsFromText(text) {
  return String(text || '')
    .split(/\r?\n/)
    .map(s => s.trim())
    .filter(Boolean);
}

function extractUrlsFromJson(jsonValue) {
  if (Array.isArray(jsonValue)) {
    if (jsonValue.every(v => typeof v === 'string')) return jsonValue;
    return jsonValue.map(v => (v && typeof v === 'object' ? v.url : '')).filter(Boolean);
  }
  if (jsonValue && typeof jsonValue === 'object') {
    if (Array.isArray(jsonValue.data)) return extractUrlsFromJson(jsonValue.data);
    if (Array.isArray(jsonValue.urls)) return extractUrlsFromJson(jsonValue.urls);
  }
  return [];
}

function openBulkDuplicateModal(lines, pendingUrls, pendingTagsValue) {
  bulkPendingUrls = pendingUrls || [];
  bulkPendingTags = pendingTagsValue || [];
  const listEl = document.getElementById('bulkDuplicateList');
  if (listEl) listEl.textContent = (lines || []).join('\n');
  const modal = document.getElementById('bulkDuplicateModal');
  if (modal) modal.style.display = 'block';
}

function closeBulkDuplicateModal() {
  bulkPendingUrls = [];
  bulkPendingTags = [];
  const modal = document.getElementById('bulkDuplicateModal');
  if (modal) modal.style.display = 'none';
}

async function prepareBulkAdd(urls, tags) {
  hideLinkAddError();
  const inputUrls = (urls || []).map(u => String(u || '').trim()).filter(Boolean);
  if (inputUrls.length === 0) {
    showLinkAddError('未检测到可添加的URL');
    return false;
  }

  if (!currentLinks || currentLinks.length === 0) {
    await loadLinks();
  }

  const existing = getExistingUrlKeySet();
  const seen = new Set();
  const toAdd = [];
  const existingDup = new Set();
  const inputDup = new Set();

  inputUrls.forEach(u => {
    const key = normalizeUrlForDup(u);
    if (!key) return;
    if (existing.has(key)) {
      existingDup.add(u);
      return;
    }
    if (seen.has(key)) {
      inputDup.add(u);
      return;
    }
    seen.add(key);
    toAdd.push(u);
  });

  if (existingDup.size || inputDup.size) {
    const lines = [];
    Array.from(existingDup).forEach(u => lines.push(`已存在于系统: ${u}`));
    Array.from(inputDup).forEach(u => lines.push(`当前输入中重复: ${u}`));
    lines.unshift(`待添加URL总数: ${inputUrls.length}`);
    lines.unshift(`可添加(去重后): ${toAdd.length}`);
    openBulkDuplicateModal(lines, toAdd, tags || []);
    return false;
  }

  try {
    await addLinksBatch(toAdd, tags || []);
    return true;
  } catch (e) {
    showLinkAddError((e && e.message) ? e.message : '批量添加失败');
    return false;
  }
}

async function updateTags(id, newTags) {
  const item = (currentLinks || []).find(i => i && i.id === id);
  const sysTags = (item?.tags || []).filter(_isSysLinkTag);
  const userTags = (newTags || []).filter(t => !_isSysLinkTag(t)).map(t => String(t).trim()).filter(Boolean);
  const merged = [];
  const seen = new Set();
  [...userTags, ...sysTags].forEach(t => {
    const s = String(t || '').trim();
    if (!s) return;
    if (seen.has(s)) return;
    seen.add(s);
    merged.push(s);
  });
  await api(`/links/${id}`, 'PUT', { tags: merged });
  await loadLinks();
}

async function deleteLink(id) {
  await api(`/links/${id}`, 'DELETE');
  await loadLinks();
}

async function batchDeleteLinks() {
  if (selectedIds.size === 0) return;
  if (!confirm(`确定删除选中的 ${selectedIds.size} 项内容吗？`)) return;
  
  await api('/links/delete_batch', 'POST', { ids: Array.from(selectedIds) });
  selectedIds.clear();
  await loadLinks();
}

async function syncKBPreview() {
    if (!confirm('确定要从知识库同步所有URL链接吗？\n这将扫描知识库中所有的URL并同步到预览列表。')) return;

    const btn = document.getElementById('syncKBPreviewBtn');
    let originalText = '';
    if (btn) {
        originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '⏳ 同步中...';
    }

    try {
        const res = await api('/links/sync_kb', 'POST');
        if (res.success) {
            alert(`同步完成！\n共发现链接: ${res.total_found}\n新增: ${res.count}\n更新: ${res.updated || 0}\n解除关联(无ID): ${res.unlinked || 0}`);
            loadLinks();
        } else {
            alert('同步失败: ' + res.message);
        }
    } catch (e) {
        console.error(e);
        alert('同步请求出错: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

async function batchCopyPreviews() {
    if (selectedIds.size === 0) return;
    
    // Find selected items
    const items = currentLinks.filter(i => selectedIds.has(i.id));
    if (items.length === 0) return;

    // Build HTML table for clipboard
    let html = '<table border="1"><thead><tr><th>预览</th><th>链接信息</th><th>链接类型</th><th>KB ID</th><th>标签</th></tr></thead><tbody>';
    
    items.forEach(item => {
      const kbId = item.kb_id && String(item.kb_id).trim() ? String(item.kb_id).trim() : '无ID';
      const typeLabel = _getLinkSourceLabel(item);
      const tags = Array.isArray(item.tags) ? item.tags.filter(t => !_isSysLinkTag(t)).join(',') : '';
      html += '<tr><td>';
      if (item.type === 'image') {
        try {
            const fullUrl = new URL(item.url, window.location.href).href;
            html += `<img src="${fullUrl}" height="100" />`;
        } catch (e) {
            html += `<img src="${item.url}" height="100" />`;
        }
      } else {
        html += `<a href="${item.url}">${item.url}</a>`;
      }
      html += `</td><td><a href="${item.url}">${item.url}</a></td><td>${escapeHtml(typeLabel)}</td><td>${escapeHtml(kbId)}</td><td>${escapeHtml(tags)}</td></tr>`;
    });
    
    html += '</tbody></table>';
    
    try {
      const blobHtml = new Blob([html], { type: 'text/html' });
      const blobText = new Blob([items.map(i => `${_getLinkSourceLabel(i)}\t${i.url || ''}`).join('\n')], { type: 'text/plain' });
      
      const data = [new ClipboardItem({ 
        'text/html': blobHtml,
        'text/plain': blobText 
      })];
      
      await navigator.clipboard.write(data);
      alert(`已复制 ${items.length} 项预览内容！\n现在可以在 Excel/飞书/Word 中直接粘贴。`);
    } catch (err) {
      console.error(err);
      alert('复制失败，请确保您使用现代浏览器且页面处于活动状态。\n' + err.message);
    }
}

function updateBatchUI() {
  const btn = document.getElementById('batchDeleteBtn');
  const copyBtn = document.getElementById('batchCopyBtn');
  const selectAll = document.getElementById('selectAll');
  
  if (btn) {
      if (selectedIds.size > 0) {
        btn.classList.remove('d-none');
        btn.style.display = 'inline-block';
        btn.textContent = `🗑️ 批量删除 (${selectedIds.size})`;
        
        if (copyBtn) {
            copyBtn.classList.remove('d-none');
            copyBtn.style.display = 'inline-block';
            copyBtn.textContent = `📋 批量复制预览 (${selectedIds.size})`;
        }
      } else {
        btn.classList.add('d-none');
        btn.style.display = 'none';
        
        if (copyBtn) {
            copyBtn.classList.add('d-none');
            copyBtn.style.display = 'none';
        }
      }
  }
  
  if (selectAll) {
      const pageItems = getLinkPageItems();
      const visibleIds = pageItems.map(i => i.id);
      const selectedVisibleCount = visibleIds.filter(id => selectedIds.has(id)).length;
      
      if (visibleIds.length > 0 && selectedVisibleCount === visibleIds.length) {
        selectAll.checked = true;
        selectAll.indeterminate = false;
      } else if (selectedVisibleCount > 0) {
        selectAll.checked = false;
        selectAll.indeterminate = true;
      } else {
        selectAll.checked = false;
        selectAll.indeterminate = false;
      }
  }
}

// Image Modal Logic
function openModal(url) {
  const modal = document.getElementById('imageModal');
  const modalImg = document.getElementById('modalImg');
  const modalVideo = document.getElementById('modalVideo');
  const downloadBtn = document.getElementById('downloadBtn');
  
  if (modal) {
      modal.style.display = 'block';
      const type = detectType(url);
      
      if (type === 'video') {
          if (modalVideo) {
              modalVideo.src = url;
              modalVideo.classList.remove('d-none');
              modalVideo.style.display = 'block';
          }
          if (modalImg) modalImg.style.display = 'none';
      } else {
          // Assume image
          if (modalImg) {
              modalImg.src = url;
              modalImg.style.display = 'block';
          }
          if (modalVideo) {
              modalVideo.pause();
              modalVideo.style.display = 'none';
              modalVideo.classList.add('d-none');
          }
      }
      
      if (downloadBtn) downloadBtn.onclick = () => downloadImage(url);
  }
}

async function downloadImage(url) {
  try {
    const response = await fetch(url);
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = url.split('/').pop().split('?')[0] || 'image.png';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
  } catch (e) {
    window.open(url, '_blank');
  }
}

function renderTagChip(tag, active) {
  const el = document.createElement('span');
  el.className = 'tag-chip' + (active ? ' active' : '');
  el.textContent = tag;
  el.setAttribute('role', 'option');
  el.setAttribute('aria-selected', active ? 'true' : 'false');
  el.addEventListener('click', () => {
    activeFilterTags = active ? activeFilterTags.filter(t => t !== tag) : [...activeFilterTags, tag];
    linkCurrentPage = 1;
    renderLinkTable();
  });
  return el;
}

function setLinkTagDropdownOpen(open) {
  const wrap = document.getElementById('linkTagSelectorWrap');
  const panel = document.getElementById('linkTagDropdown');
  const btn = document.getElementById('linkTagSelectorBtn');
  if (wrap) wrap.classList.toggle('open', open);
  if (panel) panel.classList.toggle('d-none', !open);
  if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
}

function updateLinkTagSelectorSummary() {
  const valueEl = document.getElementById('linkTagSelectorValue');
  if (!valueEl) return;
  if (!activeFilterTags.length) {
    valueEl.textContent = '未选择';
    return;
  }
  if (activeFilterTags.length <= 2) {
    valueEl.textContent = activeFilterTags.join('、');
    return;
  }
  valueEl.textContent = `已选 ${activeFilterTags.length} 个标签`;
}

function parseCreatedAtSeconds(item) {
  if (item && typeof item.createdAt === 'number' && Number.isFinite(item.createdAt)) return item.createdAt;
  if (item && typeof item.created_at === 'number' && Number.isFinite(item.created_at)) return item.created_at;
  const raw = item && (item.created_at || item.createdAt);
  if (!raw) return 0;
  const ms = Date.parse(String(raw));
  if (!Number.isFinite(ms)) return 0;
  return ms / 1000;
}

function normalizeUrlForDup(url) {
  if (!url) return '';
  const raw = String(url).replace(/`/g, '').trim();
  if (!raw) return '';
  try {
    const u = new URL(raw);
    const protocol = (u.protocol || '').toLowerCase();
    const hostname = (u.hostname || '').toLowerCase();
    const port = u.port ? `:${u.port}` : '';
    const pathname = u.pathname || '';
    const search = u.search || '';
    return `${protocol}//${hostname}${port}${pathname}${search}`.replace(/\/+$/, '');
  } catch {
    return raw.toLowerCase().replace(/\/+$/, '');
  }
}

function hideLinkAddError() {
  const el = document.getElementById('linkAddError');
  if (!el) return;
  el.classList.add('d-none');
  el.textContent = '';
}

function showLinkAddError(message) {
  const el = document.getElementById('linkAddError');
  if (!el) {
    alert(message);
    return;
  }
  el.textContent = message;
  el.classList.remove('d-none');
  el.style.display = 'block';
}

function getExistingUrlKeySet() {
  const set = new Set();
  (currentLinks || []).forEach(i => {
    const key = normalizeUrlForDup(i && i.url);
    if (key) set.add(key);
  });
  return set;
}

function buildDuplicateGroups(items) {
  const map = new Map();
  (items || []).forEach(i => {
    const key = normalizeUrlForDup(i && i.url);
    if (!key) return;
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(i);
  });
  const groups = [];
  map.forEach((arr, key) => {
    if (arr.length > 1) groups.push({ key, url: arr[0]?.url || key, items: arr });
  });
  groups.sort((a, b) => b.items.length - a.items.length);
  return groups;
}

function pickKeepItem(items) {
  const sorted = [...(items || [])].sort((a, b) => {
    const aHasKb = a && a.kb_id && String(a.kb_id).trim() ? 1 : 0;
    const bHasKb = b && b.kb_id && String(b.kb_id).trim() ? 1 : 0;
    if (aHasKb !== bHasKb) return bHasKb - aHasKb;
    const aTags = Array.isArray(a?.tags) ? a.tags.length : 0;
    const bTags = Array.isArray(b?.tags) ? b.tags.length : 0;
    if (aTags !== bTags) return bTags - aTags;
    return parseCreatedAtSeconds(b) - parseCreatedAtSeconds(a);
  });
  return sorted[0] || null;
}

function getFilteredLinkItems() {
  let items = currentLinks;

  if (activeFilterTags.length) {
    const filterMode = document.querySelector('input[name="tagFilterMode"]:checked')?.value || 'any';
    if (filterMode === 'all') {
      items = items.filter(d => {
        const itemTags = d.tags || [];
        return activeFilterTags.every(t => itemTags.includes(t));
      });
    } else {
      items = items.filter(d => (d.tags || []).some(t => activeFilterTags.includes(t)));
    }
  }

  const statusFilter = document.getElementById('linkFilterStatus');
  if (statusFilter) {
    const status = statusFilter.value;
    if (status === 'has_id') {
      items = items.filter(d => d.kb_id && String(d.kb_id).trim() !== '');
    } else if (status === 'no_id') {
      items = items.filter(d => !d.kb_id || String(d.kb_id).trim() === '');
    }
  }

  const typeFilter = document.getElementById('linkFilterType');
  if (typeFilter) {
    const t = String(typeFilter.value || '').trim();
    if (t && t !== 'all') {
      const known = ['image', 'video', 'youtube', 'link'];
      items = items.filter(d => {
        const dt = String((d && d.type) || detectType(d && d.url ? d.url : '') || '').trim();
        if (t === 'other') return dt && !known.includes(dt);
        return dt === t;
      });
    }
  }

  const kbidInput = document.getElementById('linkSearchKBID');
  if (kbidInput) {
    const term = kbidInput.value.trim().toLowerCase();
    if (term) {
      items = items.filter(d => d.kb_id && String(d.kb_id).toLowerCase().includes(term));
    }
  }

  const urlInput = document.getElementById('linkSearchURL');
  if (urlInput) {
    const term = urlInput.value.trim().toLowerCase();
    if (term) {
      items = items.filter(d => d.url && String(d.url).toLowerCase().includes(term));
    }
  }

  if (linkShowDuplicateUrlsOnly) {
    const counts = new Map();
    items.forEach(d => {
      const key = normalizeUrlForDup(d.url);
      if (!key) return;
      counts.set(key, (counts.get(key) || 0) + 1);
    });
    items = items.filter(d => {
      const key = normalizeUrlForDup(d.url);
      return key && (counts.get(key) || 0) > 1;
    });
  }

  const dir = linkSortDir === 'asc' ? 1 : -1;
  const by = linkSortBy;
  if (by) {
    items = [...items].sort((a, b) => {
      if (by === 'createdAt') return (parseCreatedAtSeconds(a) - parseCreatedAtSeconds(b)) * dir;
      if (by === 'kb_id') return String(a.kb_id || '').localeCompare(String(b.kb_id || '')) * dir;
      if (by === 'url') return String(a.url || '').localeCompare(String(b.url || '')) * dir;
      if (by === 'type') return String(_getLinkSourceLabel(a)).localeCompare(String(_getLinkSourceLabel(b))) * dir;
      if (by === 'tags') return String((a.tags || []).join(',')).localeCompare(String((b.tags || []).join(','))) * dir;
      return 0;
    });
  }

  return items;
}

function renderLinkRow(item) {
  const tr = document.createElement('tr');
  tr.dataset.linkId = item.id;

  // Checkbox
  const tdCheck = document.createElement('td');
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.checked = selectedIds.has(item.id);
  checkbox.onchange = (e) => {
    if (e.target.checked) selectedIds.add(item.id);
    else selectedIds.delete(item.id);
    updateBatchUI();
  };
  tdCheck.appendChild(checkbox);
  tr.appendChild(tdCheck);

  // Preview
  const tdPreview = document.createElement('td');
  tdPreview.className = 'preview-cell';
  const box = document.createElement('div');
  box.className = 'preview-box';
  
  if (item.type === 'image') {
    const img = document.createElement('img');
    img.src = item.url;
    img.loading = 'lazy'; // Lazy load
    img.style.cursor = 'pointer';
    img.referrerPolicy = 'no-referrer'; // Fix for hotlink protection
    img.onclick = () => openModal(item.url);
    box.appendChild(img);
  } else if (item.type === 'video') {
    // Optimization: Don't create video element until clicked to prevent lag
    const container = document.createElement('div');
    container.style.position = 'relative';
    container.style.width = '100%';
    container.style.height = '100%';
    container.style.display = 'flex';
    container.style.alignItems = 'center';
    container.style.justifyContent = 'center';
    container.style.cursor = 'pointer';
    container.style.backgroundColor = '#000';
    
    // Poster/Placeholder
    const poster = document.createElement('img');
    poster.src = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiM5OTkiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cG9seWdvbiBwb2ludHM9IjUgMyAxOSAxMiA1IDIxIDUgMyI+PC9wb2x5Z29uPjwvc3ZnPg==';
    poster.style.maxWidth = '50%';
    poster.style.maxHeight = '50%';
    container.appendChild(poster);

    container.onclick = () => {
        container.innerHTML = ''; // Clear placeholder
        const v = document.createElement('video');
        v.src = item.url;
        v.controls = true;
        v.autoplay = true;
        v.style.width = '100%';
        v.style.height = '100%';
        v.style.objectFit = 'contain';
        v.referrerPolicy = 'no-referrer';
        v.onerror = () => {
            container.innerHTML = '<span style="color:#fff;font-size:12px;">加载失败</span>';
        };
        container.appendChild(v);
        container.onclick = null; // Remove handler
    };
    
    box.appendChild(container);
  } else if (item.type === 'youtube') {
    const f = document.createElement('iframe');
    f.src = toYoutubeEmbed(item.url);
    box.appendChild(f);
  } else {
    box.innerHTML = '<span style="color:#999">无预览</span>';
  }
  tdPreview.appendChild(box);
  tr.appendChild(tdPreview);

  // KB ID
  const tdKbId = document.createElement('td');
  tdKbId.className = 'id-cell';
  tdKbId.style.maxWidth = '200px'; // Increased slightly
  // Removed overflow:hidden and text-overflow:ellipsis to allow full display
  tdKbId.style.whiteSpace = 'normal'; 
  tdKbId.title = item.kb_id || '';
  
  if (item.kb_id) {
      const rawId = item.kb_id;
      // Split by comma/chinese comma
      const ids = rawId.split(/[,，]/).map(s => s.trim()).filter(s => s);
      const idHtml = ids.map(oneId => 
         `<div class="clickable-id-row"><span class="clickable-id" onclick="searchKBById('${oneId}')" title="点击搜索此ID">${oneId}</span></div>`
      ).join('');
      tdKbId.innerHTML = idHtml;
  } else {
      tdKbId.textContent = '-';
  }
  tr.appendChild(tdKbId);

  // Info
  const tdLink = document.createElement('td');
  tdLink.className = 'link-cell';
  
  const cleanUrl = item.url.replace(/"/g, '&quot;').replace(/'/g, "\\'"); // Basic escape
  const createdAtSeconds = parseCreatedAtSeconds(item);
  const createdAtText = createdAtSeconds ? new Date(createdAtSeconds * 1000).toLocaleString() : '-';
  
  tdLink.innerHTML = `
    <div class="kb-url-row">
        <button type="button" class="kb-mini-action-btn kb-mini-action-btn-icon" onclick="copyToClipboard('${cleanUrl}')" title="复制链接"><i class="fas fa-copy"></i></button>
        <a href="javascript:void(0)" onclick="searchKBByUrl('${cleanUrl}')" title="点击搜索: ${cleanUrl}" class="kb-url-link">${item.url}</a>
        <button type="button" class="kb-mini-action-btn kb-mini-action-btn-icon" onclick="searchKBByUrl('${cleanUrl}')" title="按此链接搜索"><i class="fas fa-search"></i></button>
        <a href="${item.url}" target="_blank" title="在新标签页打开" class="kb-url-open-btn kb-mini-action-btn-icon"><i class="fas fa-external-link-alt"></i></a>
    </div>
    <div class="meta">时间: ${createdAtText}</div>`;
  tr.appendChild(tdLink);

  const tdLinkSrc = document.createElement('td');
  tdLinkSrc.className = 'link-src-cell';
  tdLinkSrc.textContent = _getLinkSourceLabel(item);
  tr.appendChild(tdLinkSrc);

  // Tags
  const tdTags = document.createElement('td');
  tdTags.className = 'tags-cell';
  tdTags.style.overflow = 'visible'; // Allow dropdown to show
  const tagList = document.createElement('div');
  tagList.className = 'tag-list';
  (item.tags || []).filter(t => !_isSysLinkTag(t)).forEach(t => {
    const el = document.createElement('span');
    el.className = 'tag';
    el.innerHTML = `${t} <span class="rm-tag">&times;</span>`;
    el.querySelector('.rm-tag').addEventListener('click', () => {
      const nextTags = (item.tags || []).filter(x => !_isSysLinkTag(x) && x !== t);
      updateTags(item.id, nextTags);
    });
    tagList.appendChild(el);
  });
  
  const addRow = document.createElement('div');
  addRow.className = 'add-tag-row';
  const inp = document.createElement('input');
  inp.placeholder = '添加标签...';
  const btn = document.createElement('button');
  btn.textContent = '添加';
  btn.addEventListener('click', () => {
    const val = inp.value.trim();
    if (!val) return;
    const newTags = val.split(/[,，]/).map(s => s.trim()).filter(Boolean);
    const unique = Array.from(new Set([...(item.tags || []).filter(t => !_isSysLinkTag(t)), ...newTags]));
    updateTags(item.id, unique);
  });
  addRow.append(inp, btn);
  
  // Setup auto-complete for row input
  setupRowTagInput(inp, addRow, (item.tags || []).filter(t => !_isSysLinkTag(t)));
  
  tdTags.append(tagList, addRow);
  tr.appendChild(tdTags);

  // Action
  const tdAction = document.createElement('td');
  const delBtn = document.createElement('button');
  delBtn.className = 'action-btn';
  delBtn.textContent = '删除';
  delBtn.addEventListener('click', () => {
    if (confirm('确定删除?')) deleteLink(item.id);
  });
  tdAction.appendChild(delBtn);
  tr.appendChild(tdAction);

  return tr;
}

function changeLinkPage(offset) {
    linkCurrentPage += offset;
    if (linkCurrentPage < 1) linkCurrentPage = 1;
    renderLinkTable();
}

function changeLinkPageSize() {
    const sel = document.getElementById('linkPageSizeSelect');
    if (sel) {
        linkPageSize = parseInt(sel.value);
        linkCurrentPage = 1;
        renderLinkTable();
    }
}

function handleLinkSort(field) {
  if (!field) return;
  if (linkSortBy === field) {
    linkSortDir = linkSortDir === 'asc' ? 'desc' : 'asc';
  } else {
    linkSortBy = field;
    linkSortDir = field === 'createdAt' ? 'desc' : 'asc';
  }
  linkCurrentPage = 1;
  renderLinkTable();
}

function toggleDuplicateUrlFilter() {
  linkShowDuplicateUrlsOnly = !linkShowDuplicateUrlsOnly;
  linkCurrentPage = 1;
  renderLinkTable();
}

async function openDuplicateUrlModal() {
  hideLinkAddError();
  if (!currentLinks || currentLinks.length === 0) {
    await loadLinks();
  }

  duplicateGroupsCache = buildDuplicateGroups(currentLinks);

  const total = (currentLinks || []).length;
  const groups = duplicateGroupsCache.length;
  const deleted = duplicateGroupsCache.reduce((sum, g) => sum + Math.max(0, (g.items || []).length - 1), 0);
  const unique = total - deleted;

  linkShowDuplicateUrlsOnly = true;
  linkCurrentPage = 1;
  renderLinkTable();

  const modal = document.getElementById('duplicateUrlModal');
  const listEl = document.getElementById('duplicateUrlList');
  const summaryEl = document.getElementById('duplicateUrlSummary');
  const btn = document.getElementById('duplicateUrlDedupBtn');

  if (summaryEl) {
    summaryEl.textContent = `原始URL总数: ${total}，发现重复组数: ${groups}，可删除重复项数量: ${deleted}，最终唯一URL数量: ${unique}`;
  }

  if (listEl) {
    if (!duplicateGroupsCache.length) {
      listEl.textContent = '未发现重复URL';
    } else {
      const lines = [];
      duplicateGroupsCache.forEach(g => {
        lines.push(`${g.url}  (重复${g.items.length}条)`);
      });
      listEl.textContent = lines.join('\n');
    }
  }

  if (btn) btn.disabled = !duplicateGroupsCache.length;
  if (modal) modal.style.display = 'block';
}

async function deduplicateUrls() {
  if (!duplicateGroupsCache || duplicateGroupsCache.length === 0) {
    alert('未发现重复URL');
    return;
  }

  const total = (currentLinks || []).length;
  const groups = duplicateGroupsCache.length;

  const deleteIds = [];
  duplicateGroupsCache.forEach(g => {
    const keep = pickKeepItem(g.items);
    (g.items || []).forEach(i => {
      if (!i || !i.id) return;
      if (keep && keep.id === i.id) return;
      deleteIds.push(i.id);
    });
  });

  const deleted = deleteIds.length;
  const unique = total - deleted;

  if (deleted === 0) {
    alert('未发现可删除的重复项');
    return;
  }
  if (!confirm(`将删除 ${deleted} 条重复记录，仅保留每个URL的1条。确定继续吗？`)) return;

  await api('/links/delete_batch', 'POST', { ids: deleteIds });
  deleteIds.forEach(id => selectedIds.delete(id));
  await loadLinks();

  duplicateGroupsCache = buildDuplicateGroups(currentLinks);

  const summaryEl = document.getElementById('duplicateUrlSummary');
  if (summaryEl) {
    summaryEl.textContent = `去重完成：原始URL总数: ${total}，发现重复组数: ${groups}，删除的重复项数量: ${deleted}，最终保留的唯一URL数量: ${unique}`;
  }
  const listEl = document.getElementById('duplicateUrlList');
  if (listEl) {
    if (!duplicateGroupsCache.length) listEl.textContent = '当前已无重复URL';
    else {
      const lines = [];
      duplicateGroupsCache.forEach(g => lines.push(`${g.url}  (重复${g.items.length}条)`));
      listEl.textContent = lines.join('\n');
    }
  }
  const btn = document.getElementById('duplicateUrlDedupBtn');
  if (btn) btn.disabled = !duplicateGroupsCache.length;
  alert(`去重完成！\n原始URL总数: ${total}\n发现的重复组数: ${groups}\n删除的重复项数量: ${deleted}\n最终保留的唯一URL数量: ${unique}`);
}

function getLinkPageItems() {
  const items = getFilteredLinkItems();
  const start = (linkCurrentPage - 1) * linkPageSize;
  const end = start + linkPageSize;
  return items.slice(start, end);
}

function toggleSelectAllLinks() {
  const selectAll = document.getElementById('selectAll');
  if (!selectAll) return;
  const pageItems = getLinkPageItems();
  if (selectAll.checked) {
    pageItems.forEach(i => selectedIds.add(i.id));
  } else {
    pageItems.forEach(i => selectedIds.delete(i.id));
  }
  updateBatchUI();
}

function csvEscape(value) {
  const s = value === null || value === undefined ? '' : String(value);
  if (/[",\r\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function exportLinkData() {
  const items = getFilteredLinkItems();
  const header = ['链接类型', '链接信息', 'KBID', '标签'];
  const rows = items.map(i => {
    const kbId = i.kb_id && String(i.kb_id).trim() ? String(i.kb_id).trim() : '无ID';
    const tags = Array.isArray(i.tags) ? i.tags.filter(t => !_isSysLinkTag(t)).join(',') : '';
    return [_getLinkSourceLabel(i), i.url || '', kbId, tags];
  });

  const csv = [header, ...rows].map(r => r.map(csvEscape).join(',')).join('\r\n');
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const fileName = `多媒体预览_导出_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}.csv`;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function cssEscapeValue(value) {
  const s = value === null || value === undefined ? '' : String(value);
  if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') return CSS.escape(s);
  return s.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function flashLinkRow(linkId) {
  if (!linkId) return;
  const tr = document.querySelector(`tr[data-link-id="${cssEscapeValue(linkId)}"]`);
  if (!tr) return;
  const original = tr.style.backgroundColor;
  tr.style.backgroundColor = 'rgba(0, 123, 255, 0.12)';
  tr.scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(() => {
    tr.style.backgroundColor = original;
  }, 1400);
}

async function showLatestManualUrl() {
  let last = null;
  try {
    last = JSON.parse(localStorage.getItem('link_last_manual') || 'null');
  } catch {}
  if (!last || (!last.id && !last.url)) {
    alert('暂无可用的手动录入记录');
    return;
  }
  if (!currentLinks || currentLinks.length === 0) {
    await loadLinks();
  }
  const latest = currentLinks.find(i => i && i.id === last.id) || { id: last.id, url: last.url };

  const urlInput = document.getElementById('linkSearchURL');
  if (urlInput) urlInput.value = latest.url || '';
  const kbidInput = document.getElementById('linkSearchKBID');
  if (kbidInput) kbidInput.value = '';
  const statusFilter = document.getElementById('linkFilterStatus');
  if (statusFilter) statusFilter.value = 'all';
  const typeFilter = document.getElementById('linkFilterType');
  if (typeFilter) typeFilter.value = 'all';

  activeFilterTags = [];
  linkShowDuplicateUrlsOnly = false;
  linkCurrentPage = 1;
  renderLinkTable();
  setTimeout(() => flashLinkRow(latest.id), 50);
}

function renderLinkTable() {
  const tbody = document.getElementById('tableBody');
  if (!tbody) return;
  tbody.innerHTML = '';
  
  const items = getFilteredLinkItems();
  applyLinkTableWidths();

  // Update Pagination Info
  const total = items.length;
  const pageInfo = document.getElementById('linkPageInfo');
  if (pageInfo) pageInfo.textContent = `共 ${total} 条`;

  // Pagination Logic
  const start = (linkCurrentPage - 1) * linkPageSize;
  const end = start + linkPageSize;
  const pageItems = items.slice(start, end);

  // Update Buttons
  const prevBtn = document.getElementById('prevLinkPageBtn');
  const nextBtn = document.getElementById('nextLinkPageBtn');
  if (prevBtn) prevBtn.disabled = linkCurrentPage <= 1;
  if (nextBtn) nextBtn.disabled = end >= total;

  if (!pageItems.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:32px;color:#666">暂无数据</td></tr>';
  } else {
    pageItems.forEach(item => tbody.appendChild(renderLinkRow(item)));
  }

  const filter = document.getElementById('tagFilter');
  if (filter) {
      filter.innerHTML = '';
      const allTags = new Set();
      currentLinks.forEach(d => (d.tags || []).forEach(t => { if (!_isSysLinkTag(t)) allTags.add(t); }));
      Array.from(allTags).sort().forEach(tag => {
        filter.appendChild(renderTagChip(tag, activeFilterTags.includes(tag)));
      });
  }
  updateLinkTagSelectorSummary();
  
  updateBatchUI();
  makeTableResizable('linkTable');
  applyLinkTableWidths();

  const dupBtn = document.getElementById('filterDupUrlBtn');
  if (dupBtn) dupBtn.classList.toggle('is-active', linkShowDuplicateUrlsOnly);

  const tagMode = document.querySelector('input[name="tagFilterMode"]:checked')?.value || 'any';
  document.querySelectorAll('[data-tag-mode]').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-tag-mode') === tagMode);
  });
}

// ==========================================
// Governance View Logic
// ==========================================
let govData = [];
let govMonths = [];
let govMonthsLoaded = false;
let govLastDataKey = '';
let govLastDashboardKey = '';
let govCurrentPage = 1;
let govPageSize = 50;
let govSortBy = 'recall_count';
let govSortDir = 'desc';
let selectedGovRows = new Set();
let currentGovMonths = []; // Store currently displayed months
let currentGovSummary = {}; // Store summary data
let govAdvancedConditions = {}; // { [month]: { recallMin, recallMax, validMin, validMax } }
let govDashboardData = [];
let govDashboardMonths = [];
let currentGovDashboardSummary = {};
let govDashboardDataById = new Map();
let currentGovDashboardMetrics = null;
let currentGovDashboardRange = { startMonth: '', endMonth: '', months: [] };
let govDashboardStatusMessage = '请选择大盘统计月份范围';
let govDashboardStatusClass = 'text-muted';

const GOV_DASHBOARD_RANGE_STORAGE_KEY = 'kbHub.govDashboard.range';

function _govParseNumber(value) {
    if (value === '' || value === null || value === undefined) return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
}

function _govFormatInteger(value) {
    const n = _govParseNumber(value);
    if (n === null) return '-';
    return Math.round(n).toLocaleString('zh-CN');
}

function _govFormatAverage(value) {
    const n = _govParseNumber(value);
    if (n === null) return '-';
    return n.toFixed(2);
}

function _govFormatPercent(value) {
    const n = _govParseNumber(value);
    if (n === null) return '-';
    return `${(n * 100).toFixed(2)}%`;
}

function _govPopulateMonthSelect(select, months, placeholder) {
    if (!select) return;
    select.innerHTML = `<option value="">${placeholder}</option>`;
    (months || []).forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        select.appendChild(opt);
    });
}

function clearGovernanceViewState() {
    govData = [];
    currentGovMonths = [];
    currentGovSummary = {};
    govCurrentPage = 1;
    selectedGovRows.clear();
    govDashboardData = [];
    govDashboardMonths = [];
    currentGovDashboardSummary = {};
    govDashboardDataById = new Map();
    currentGovDashboardMetrics = null;
    currentGovDashboardRange = { startMonth: '', endMonth: '', months: [] };
    govDashboardStatusMessage = '暂无可统计数据';
    govDashboardStatusClass = 'text-muted';

    const monthFilterSel = document.getElementById('govFilterMonths');
    if (monthFilterSel) {
        monthFilterSel.innerHTML = '<option value="">全部月份</option>';
    }

    renderGovSummaryPanel();
    renderGovTable();
    updateGovPagination();
}

function _govReadDashboardRange() {
    try {
        return JSON.parse(localStorage.getItem(GOV_DASHBOARD_RANGE_STORAGE_KEY) || '{}') || {};
    } catch (e) {
        return {};
    }
}

function _govSaveDashboardRange(startMonth, endMonth) {
    try {
        localStorage.setItem(GOV_DASHBOARD_RANGE_STORAGE_KEY, JSON.stringify({
            startMonth: startMonth || '',
            endMonth: endMonth || ''
        }));
    } catch (e) {
        console.warn('Failed to save governance dashboard range', e);
    }
}

function _govParseEffectiveMonth(kbId) {
    const match = String(kbId || '').trim().match(/^ICWIKI(\d{4})(\d{2})(\d{2})/i);
    if (!match) return null;

    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const date = new Date(year, month - 1, day);
    if (
        !Number.isFinite(year) ||
        month < 1 || month > 12 ||
        day < 1 || day > 31 ||
        date.getFullYear() !== year ||
        date.getMonth() !== month - 1 ||
        date.getDate() !== day
    ) {
        return null;
    }

    return `${match[1]}-${match[2]}`;
}

function _govGetMonthlyWeight(kbId, statMonth) {
    const effectiveMonth = _govParseEffectiveMonth(kbId);
    if (!effectiveMonth) return 1;
    return effectiveMonth <= statMonth ? 1 : 0;
}

function _govGetMonthlyCounts(item, month) {
    const mData = item?.monthly_data?.[month] || {};
    const recall = _govParseNumber(mData.recall_count) ?? 0;
    const valid = _govParseNumber(mData.valid_recall_count) ?? 0;
    return { recall, valid };
}

function _govGetFilterMonths() {
    const sel = document.getElementById('govFilterMonths');
    if (!sel) return currentGovMonths || [];
    const chosen = String(sel.value || '').trim();
    return chosen ? [chosen] : (currentGovMonths || []);
}

function _govGetTotalsForMonths(item, months) {
    let recall = 0;
    let valid = 0;
    (months || []).forEach(month => {
        const m = _govGetMonthlyCounts(item, month);
        recall += m.recall;
        valid += m.valid;
    });
    return { recall, valid };
}

function _govGetActiveAdvancedMonths() {
    return Object.keys(govAdvancedConditions || {}).filter(m => !!govAdvancedConditions[m]);
}

function _getFilteredGovData() {
    let data = [...govData];

    const filterId = document.getElementById('govFilterId')?.value.toLowerCase();
    const filterQ = document.getElementById('govFilterQuestion')?.value.toLowerCase();
    const filterRecallMin = _govParseNumber(document.getElementById('govFilterRecallMin')?.value);
    const filterRecallMax = _govParseNumber(document.getElementById('govFilterRecallMax')?.value);
    const filterValidRecallMin = _govParseNumber(document.getElementById('govFilterValidRecallMin')?.value);
    const filterValidRecallMax = _govParseNumber(document.getElementById('govFilterValidRecallMax')?.value);
    const filterStatus = document.getElementById('govFilterStatus')?.value;
    const condMonths = _govGetActiveAdvancedMonths();

    const hasAnyFilter = Boolean(
        filterId ||
        filterQ ||
        filterStatus ||
        filterRecallMin !== null ||
        filterRecallMax !== null ||
        filterValidRecallMin !== null ||
        filterValidRecallMax !== null ||
        condMonths.length > 0
    );

    if (hasAnyFilter) {
        data = data.filter(item => {
            if (filterId && !String(item.id).toLowerCase().includes(filterId)) return false;
            if (filterQ && !String(item.question).toLowerCase().includes(filterQ)) return false;
            if (filterRecallMin !== null || filterRecallMax !== null || filterValidRecallMin !== null || filterValidRecallMax !== null) {
                const totals = _govGetTotalsForSelectedMonths(item);
                if (filterRecallMin !== null && totals.recall < filterRecallMin) return false;
                if (filterRecallMax !== null && totals.recall > filterRecallMax) return false;
                if (filterValidRecallMin !== null && totals.valid < filterValidRecallMin) return false;
                if (filterValidRecallMax !== null && totals.valid > filterValidRecallMax) return false;
            }
            if (condMonths.length > 0) {
                for (const m of condMonths) {
                    const c = govAdvancedConditions[m];
                    if (!c) continue;
                    const counts = _govGetMonthlyCounts(item, m);
                    if (c.recallMin !== null && counts.recall < c.recallMin) return false;
                    if (c.recallMax !== null && counts.recall > c.recallMax) return false;
                    if (c.validMin !== null && counts.valid < c.validMin) return false;
                    if (c.validMax !== null && counts.valid > c.validMax) return false;
                }
            }
            if (filterStatus && item.status !== filterStatus) return false;
            return true;
        });
    }

    if (govSortBy) {
        data.sort((a, b) => _govCompareValues(_govGetSortValue(a, govSortBy), _govGetSortValue(b, govSortBy), govSortDir));
    }

    return data;
}

function _govGetSummaryTotalsForMonths(months) {
    let recall = 0;
    let valid = 0;
    (months || []).forEach(month => {
        const s = currentGovSummary?.[month] || {};
        recall += _govParseNumber(s.total_recall) ?? 0;
        valid += _govParseNumber(s.total_valid) ?? 0;
    });
    return { recall, valid };
}

function _govGetTotalsForSelectedMonths(item) {
    const months = _govGetFilterMonths();
    return _govGetTotalsForMonths(item, months);
}

function _govGetSummaryTotalsForSelectedMonths() {
    const months = _govGetFilterMonths();
    return _govGetSummaryTotalsForMonths(months);
}

function _govGetSortValue(item, sortKey) {
    if (!sortKey) return null;

    if (sortKey.startsWith('m|')) {
        const parts = sortKey.split('|');
        const month = parts[1];
        const metric = parts[2];
        const m = _govGetMonthlyCounts(item, month);
        const monthTotalRecall = _govParseNumber(currentGovSummary?.[month]?.total_recall) ?? 0;
        const monthTotalValid = _govParseNumber(currentGovSummary?.[month]?.total_valid) ?? 0;

        if (metric === 'recall_count') return m.recall;
        if (metric === 'valid_recall_count') return m.valid;
        if (metric === 'recall_ratio') return monthTotalRecall > 0 ? (m.recall / monthTotalRecall) : 0;
        if (metric === 'valid_recall_ratio') return monthTotalValid > 0 ? (m.valid / monthTotalValid) : 0;
        if (metric === 'valid_rate') return m.recall > 0 ? (m.valid / m.recall) : 0;
        return null;
    }

    if (sortKey === 'recall_count' || sortKey === 'valid_recall_count' || sortKey === 'recall_ratio' || sortKey === 'valid_recall_ratio' || sortKey === 'valid_rate') {
        const totals = _govGetTotalsForSelectedMonths(item);
        const sumSummary = _govGetSummaryTotalsForSelectedMonths();
        if (sortKey === 'recall_count') return totals.recall;
        if (sortKey === 'valid_recall_count') return totals.valid;
        if (sortKey === 'recall_ratio') return sumSummary.recall > 0 ? (totals.recall / sumSummary.recall) : 0;
        if (sortKey === 'valid_recall_ratio') return sumSummary.valid > 0 ? (totals.valid / sumSummary.valid) : 0;
        if (sortKey === 'valid_rate') return totals.recall > 0 ? (totals.valid / totals.recall) : 0;
    }

    if (sortKey.startsWith('weighted_')) {
        const metrics = _govGetDashboardWeightedMetricsForItem(item);
        return metrics?.[sortKey] ?? null;
    }

    if (sortKey === 'id') return item?.id ?? '';
    if (sortKey === 'question') return item?.question ?? '';
    if (sortKey === 'ai_score') return _govParseNumber(item?.ai_score) ?? -Infinity;
    if (sortKey === 'status') return item?.status ?? '';

    return item?.[sortKey] ?? null;
}

function _govCompareValues(a, b, dir) {
    const aMissing = (a === null || a === undefined || (typeof a === 'number' && !Number.isFinite(a)));
    const bMissing = (b === null || b === undefined || (typeof b === 'number' && !Number.isFinite(b)));
    if (aMissing && bMissing) return 0;
    if (aMissing) return 1;
    if (bMissing) return -1;

    const aNum = (typeof a === 'number') ? a : _govParseNumber(a);
    const bNum = (typeof b === 'number') ? b : _govParseNumber(b);
    if (aNum !== null && bNum !== null) {
        if (aNum < bNum) return dir === 'asc' ? -1 : 1;
        if (aNum > bNum) return dir === 'asc' ? 1 : -1;
        return 0;
    }

    const as = String(a).toLowerCase();
    const bs = String(b).toLowerCase();
    if (as < bs) return dir === 'asc' ? -1 : 1;
    if (as > bs) return dir === 'asc' ? 1 : -1;
    return 0;
}

function _govSortIcon(sortKey) {
    if (govSortBy !== sortKey) return '';
    return govSortDir === 'asc' ? '▲' : '▼';
}

function _govSortableHeaderHtml(label, sortKey) {
    const safeKey = String(sortKey).replace(/'/g, "\\'");
    return `<div class="sortable-header" onclick="handleGovSort('${safeKey}')">${label}<span class="sort-icon">${_govSortIcon(sortKey)}</span></div>`;
}

async function loadGovMonths(preferredMonth = '', options = {}) {
    if (options.reuse && govMonthsLoaded) {
        renderGovSummaryPanel();
        renderGovTable();
        updateGovPagination();
        return;
    }
    try {
        const res = await api('/governance/months');
        if (res.success) {
            govMonths = (res.months || []).filter(Boolean);
            govMonthsLoaded = true;
            const startSelect = document.getElementById('govStartMonth');
            const endSelect = document.getElementById('govEndMonth');
            const dashboardStartSelect = document.getElementById('govDashboardStartMonth');
            const dashboardEndSelect = document.getElementById('govDashboardEndMonth');
            const importMonth = document.getElementById('govImportMonth');
            const prevStart = startSelect?.value || '';
            const prevEnd = endSelect?.value || '';
            const prevDashboardStart = dashboardStartSelect?.value || '';
            const prevDashboardEnd = dashboardEndSelect?.value || '';
            const savedDashboardRange = _govReadDashboardRange();

            if (preferredMonth && !govMonths.includes(preferredMonth)) {
                govMonths.push(preferredMonth);
            }
            govMonths = Array.from(new Set(govMonths)).sort((a, b) => b.localeCompare(a));
            
            if (startSelect) {
                _govPopulateMonthSelect(startSelect, govMonths, '起始月份');
                if (preferredMonth && govMonths.includes(preferredMonth)) {
                    startSelect.value = preferredMonth;
                } else if (prevStart && govMonths.includes(prevStart)) {
                    startSelect.value = prevStart;
                } else if (govMonths.length > 0) {
                    startSelect.value = govMonths[0];
                }
            }
            
            if (endSelect) {
                _govPopulateMonthSelect(endSelect, govMonths, '结束月份');
                if (preferredMonth) {
                    endSelect.value = '';
                } else if (prevEnd && govMonths.includes(prevEnd)) {
                    endSelect.value = prevEnd;
                }
            }

            if (dashboardStartSelect) {
                _govPopulateMonthSelect(dashboardStartSelect, govMonths, '起始月份');
                const savedStart = savedDashboardRange.startMonth || '';
                if (prevDashboardStart && govMonths.includes(prevDashboardStart)) {
                    dashboardStartSelect.value = prevDashboardStart;
                } else if (savedStart && govMonths.includes(savedStart)) {
                    dashboardStartSelect.value = savedStart;
                } else if (govMonths.length > 0) {
                    dashboardStartSelect.value = govMonths[0];
                }
            }

            if (dashboardEndSelect) {
                _govPopulateMonthSelect(dashboardEndSelect, govMonths, '结束月份');
                const savedEnd = savedDashboardRange.endMonth || '';
                if (prevDashboardEnd && govMonths.includes(prevDashboardEnd)) {
                    dashboardEndSelect.value = prevDashboardEnd;
                } else if (savedEnd && govMonths.includes(savedEnd)) {
                    dashboardEndSelect.value = savedEnd;
                }
            }
            
            if (importMonth) {
                // Populate import month selector (maybe last month by default?)
                if (!importMonth.value) {
                    const today = new Date();
                    const lastMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1);
                    const y = lastMonth.getFullYear();
                    const m = String(lastMonth.getMonth() + 1).padStart(2, '0');
                    importMonth.value = `${y}-${m}`;
                }
            }
            
            if (govMonths.length > 0) {
                await loadGovernanceData(options);
                await loadGovDashboardData(options);
            } else {
                clearGovernanceViewState();
            }
        }
    } catch (e) {
        console.error("Failed to load gov months", e);
    }
}

async function loadGovernanceData(options = {}) {
    const startMonth = document.getElementById('govStartMonth')?.value;
    const endMonth = document.getElementById('govEndMonth')?.value;
    
    if (!startMonth) {
        if (govMonths.length === 0) await loadGovMonths();
        return;
    }

    const tbody = document.getElementById('govTableBody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="9" class="empty-message">加载中...</td></tr>';
    
    try {
        const url = `/governance/data?month=${startMonth}&end_month=${endMonth || ''}`;
        if (options.reuse && govLastDataKey === url && Array.isArray(govData)) {
            renderGovSummaryPanel();
            renderGovTable();
            updateGovPagination();
            return;
        }
        const res = await api(url);
        
        if (res.success) {
            // Process data: Keep raw data for dynamic rendering
            currentGovMonths = res.months || [];
            currentGovSummary = res.summary || {};
            govData = res.data || [];
            govLastDataKey = url;
            renderGovSummaryPanel();

            // Refresh month filter options based on currentGovMonths
            const monthFilterSel = document.getElementById('govFilterMonths');
            if (monthFilterSel) {
                const prevSelected = monthFilterSel.value || '';
                monthFilterSel.innerHTML = '<option value="">全部月份</option>';
                (currentGovMonths || []).forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m;
                    opt.textContent = m;
                    monthFilterSel.appendChild(opt);
                });
                if (prevSelected && (currentGovMonths || []).includes(prevSelected)) {
                    monthFilterSel.value = prevSelected;
                }
            }

            govCurrentPage = 1;
            renderGovTable();
            updateGovPagination();
        } else {
             if (tbody) tbody.innerHTML = `<tr><td colspan="9" class="error-message">${res.message}</td></tr>`;
        }
    } catch (e) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="9" class="error-message">加载失败: ${e.message}</td></tr>`;
    }
}

function saveGovDashboardRangeFromControls() {
    const startMonth = document.getElementById('govDashboardStartMonth')?.value || '';
    const endMonth = document.getElementById('govDashboardEndMonth')?.value || '';
    _govSaveDashboardRange(startMonth, endMonth);
}

function _govGetDashboardRangeLabel(startMonth, endMonth, months) {
    if (months && months.length > 0) {
        if (months.length === 1) return months[0];
        return `${months[0]} 至 ${months[months.length - 1]}`;
    }
    if (startMonth && endMonth) return `${startMonth} 至 ${endMonth}`;
    return startMonth || '-';
}

function _govNormalizeDashboardRange(startMonth, endMonth) {
    if (startMonth && endMonth && startMonth > endMonth) {
        return { startMonth: endMonth, endMonth: startMonth };
    }
    return { startMonth, endMonth };
}

function _govRenderDashboardMessage(message, className = 'text-muted') {
    currentGovDashboardMetrics = null;
    govDashboardStatusMessage = message || '';
    govDashboardStatusClass = className || 'text-muted';
    renderGovSummaryPanel();
}

function _govComputeDashboardMetrics(data, months, summary) {
    const items = Array.isArray(data) ? data : [];
    const statMonths = Array.isArray(months) ? months.filter(Boolean).sort() : [];

    if (items.length === 0 || statMonths.length === 0) {
        return {
            hasData: false,
            itemCount: items.length,
            monthCount: statMonths.length,
            totalRecall: null,
            totalValid: null,
            overallValidRate: null,
            totalWeight: 0,
            avgRecall: null,
            avgValidRecall: null,
            avgRecallRatio: null,
            avgValidRecallRatio: null,
            avgValidRate: null
        };
    }

    let totalRecall = 0;
    let totalValid = 0;
    let totalWeight = 0;
    let recallRatioWeightedSum = 0;
    let validRecallRatioWeightedSum = 0;
    let validRateWeightedSum = 0;

    items.forEach(item => {
        statMonths.forEach(month => {
            const counts = _govGetMonthlyCounts(item, month);
            totalRecall += counts.recall;
            totalValid += counts.valid;

            const weight = _govGetMonthlyWeight(item?.id, month);
            if (weight <= 0) return;

            const monthTotalRecall = _govParseNumber(summary?.[month]?.total_recall) ?? 0;
            const monthTotalValid = _govParseNumber(summary?.[month]?.total_valid) ?? 0;
            const recallRatio = monthTotalRecall > 0 ? counts.recall / monthTotalRecall : 0;
            const validRecallRatio = monthTotalValid > 0 ? counts.valid / monthTotalValid : 0;
            const validRate = counts.recall > 0 ? counts.valid / counts.recall : 0;

            totalWeight += weight;
            recallRatioWeightedSum += recallRatio * weight;
            validRecallRatioWeightedSum += validRecallRatio * weight;
            validRateWeightedSum += validRate * weight;
        });
    });

    return {
        hasData: true,
        itemCount: items.length,
        monthCount: statMonths.length,
        totalRecall,
        totalValid,
        overallValidRate: totalRecall > 0 ? totalValid / totalRecall : 0,
        totalWeight,
        avgRecall: totalWeight > 0 ? totalRecall / totalWeight : null,
        avgValidRecall: totalWeight > 0 ? totalValid / totalWeight : null,
        avgRecallRatio: totalWeight > 0 ? recallRatioWeightedSum / totalWeight : null,
        avgValidRecallRatio: totalWeight > 0 ? validRecallRatioWeightedSum / totalWeight : null,
        avgValidRate: totalWeight > 0 ? validRateWeightedSum / totalWeight : null
    };
}

function _govComputeItemWeightedMetrics(item, months = currentGovMonths, summary = currentGovSummary) {
    const statMonths = Array.isArray(months) ? months.filter(Boolean).sort() : [];

    let totalRecall = 0;
    let totalValid = 0;
    let totalWeight = 0;
    let recallRatioWeightedSum = 0;
    let validRecallRatioWeightedSum = 0;
    let validRateWeightedSum = 0;

    statMonths.forEach(month => {
        const counts = _govGetMonthlyCounts(item, month);
        totalRecall += counts.recall;
        totalValid += counts.valid;

        const weight = _govGetMonthlyWeight(item?.id, month);
        if (weight <= 0) return;

        const monthTotalRecall = _govParseNumber(summary?.[month]?.total_recall) ?? 0;
        const monthTotalValid = _govParseNumber(summary?.[month]?.total_valid) ?? 0;
        const recallRatio = monthTotalRecall > 0 ? counts.recall / monthTotalRecall : 0;
        const validRecallRatio = monthTotalValid > 0 ? counts.valid / monthTotalValid : 0;
        const validRate = counts.recall > 0 ? counts.valid / counts.recall : 0;

        totalWeight += weight;
        recallRatioWeightedSum += recallRatio * weight;
        validRecallRatioWeightedSum += validRecallRatio * weight;
        validRateWeightedSum += validRate * weight;
    });

    return {
        totalRecall,
        totalValid,
        totalWeight,
        weighted_avg_recall: totalWeight > 0 ? totalRecall / totalWeight : null,
        weighted_avg_valid_recall: totalWeight > 0 ? totalValid / totalWeight : null,
        weighted_avg_recall_ratio: totalWeight > 0 ? recallRatioWeightedSum / totalWeight : null,
        weighted_avg_valid_recall_ratio: totalWeight > 0 ? validRecallRatioWeightedSum / totalWeight : null,
        weighted_avg_valid_rate: totalWeight > 0 ? validRateWeightedSum / totalWeight : null
    };
}

function _govGetWeightedMetricSpecs() {
    return [
        { label: '平均召回频数', metric: 'weighted_avg_recall', type: 'number' },
        { label: '平均有效召回频数', metric: 'weighted_avg_valid_recall', type: 'number' },
        { label: '平均召回占比', metric: 'weighted_avg_recall_ratio', type: 'percent' },
        { label: '平均有效召回占比', metric: 'weighted_avg_valid_recall_ratio', type: 'percent' },
        { label: '平均有效召回率', metric: 'weighted_avg_valid_rate', type: 'percent' }
    ];
}

function _govFormatWeightedMetric(value, type) {
    return type === 'percent' ? _govFormatPercent(value) : _govFormatAverage(value);
}

function _govGetDashboardWeightedMetricsForItem(item) {
    if (!Array.isArray(govDashboardMonths) || govDashboardMonths.length === 0) return null;
    const id = String(item?.id || '').trim();
    const dashboardItem = govDashboardDataById.get(id);
    if (!dashboardItem) {
        return _govComputeItemWeightedMetrics({ id, monthly_data: {} }, govDashboardMonths, currentGovDashboardSummary);
    }
    return dashboardItem.weighted_summary || _govComputeItemWeightedMetrics(dashboardItem, govDashboardMonths, currentGovDashboardSummary);
}

function _govDashboardCardHtml(title, value, options = {}) {
    const valueClass = options.valueClass ? ` ${options.valueClass}` : '';
    const note = options.note ? `<div class="gov-summary-card-note">${options.note}</div>` : '';
    return `
        <div class="gov-summary-card ${options.cardClass || ''}">
            <div class="gov-summary-card-title">${title}</div>
            <div class="gov-summary-card-metric${valueClass}">${value}</div>
            ${note}
        </div>
    `;
}

function _govSummaryRowsCardHtml(title, totalRecall, totalValid, options = {}) {
    const validRate = totalRecall > 0 ? totalValid / totalRecall : 0;
    const recallLabel = options.isTotal ? '总召回' : '召回';
    const validLabel = options.isTotal ? '总有效' : '有效';
    return `
        <div class="gov-summary-card ${options.cardClass || ''}">
            <div class="gov-summary-card-title">${title}</div>
            <div class="gov-summary-card-body">
                <div class="gov-summary-card-row">
                    <span>${recallLabel}</span><strong>${_govFormatInteger(totalRecall)}</strong>
                </div>
                <div class="gov-summary-card-row">
                    <span>${validLabel}</span><strong class="is-success">${_govFormatInteger(totalValid)}</strong>
                </div>
                <div class="gov-summary-card-row">
                    <span>有效率</span><strong class="is-info">${_govFormatPercent(validRate)}</strong>
                </div>
            </div>
        </div>
    `;
}

function _govBuildNativeSummaryHtml() {
    const months = Array.isArray(currentGovMonths) ? currentGovMonths.filter(Boolean) : [];
    if (months.length === 0) {
        return `
            <div class="gov-summary-section">
                <div class="gov-summary-head">
                    <div>
                        <strong>选择月份范围汇总</strong>
                        <span>-</span>
                    </div>
                    <small>暂无可统计数据</small>
                </div>
                <div class="gov-summary-empty">-</div>
            </div>
        `;
    }

    let totalRecall = 0;
    let totalValid = 0;
    const monthCardsHtml = months.map(month => {
        const s = currentGovSummary?.[month] || {};
        const monthRecall = _govParseNumber(s.total_recall) ?? 0;
        const monthValid = _govParseNumber(s.total_valid) ?? 0;
        totalRecall += monthRecall;
        totalValid += monthValid;
        return _govSummaryRowsCardHtml(month, monthRecall, monthValid, { cardClass: 'gov-summary-card-month' });
    }).join('');

    const rangeLabel = months.length === 1 ? months[0] : `${months[0]} 至 ${months[months.length - 1]}`;
    return `
        <div class="gov-summary-section">
            <div class="gov-summary-head">
                <div>
                    <strong>选择月份范围汇总</strong>
                    <span>${rangeLabel}</span>
                </div>
                <small>${months.length} 个月 · 原生口径</small>
            </div>
            <div class="gov-summary-strip">
                ${_govSummaryRowsCardHtml('全部汇总', totalRecall, totalValid, { cardClass: 'gov-summary-card-total', isTotal: true })}
                <div class="gov-summary-divider"></div>
                <div class="gov-summary-month-list">
                    ${monthCardsHtml}
                </div>
            </div>
        </div>
    `;
}

function _govBuildDashboardSummaryHtml() {
    const metrics = currentGovDashboardMetrics;
    const startMonth = currentGovDashboardRange.startMonth || '';
    const endMonth = currentGovDashboardRange.endMonth || '';
    const months = currentGovDashboardRange.months || govDashboardMonths || [];

    if (!metrics?.hasData) {
        return `
            <div class="gov-summary-section">
                <div class="gov-summary-head">
                    <div>
                        <strong>周期加权大盘</strong>
                        <span>${_govGetDashboardRangeLabel(startMonth, endMonth, months)}</span>
                    </div>
                    <small>${govDashboardStatusMessage || '暂无可统计数据'}</small>
                </div>
                <div class="gov-summary-empty">-</div>
            </div>
        `;
    }

    const rangeLabel = _govGetDashboardRangeLabel(startMonth, endMonth, months);
    const metaText = `${metrics.monthCount} 个月 · ${_govFormatInteger(metrics.itemCount)} 条知识 · 权重分母 ${_govFormatInteger(metrics.totalWeight)}`;
    return `
        <div class="gov-summary-section">
            <div class="gov-summary-head">
                <div>
                    <strong>周期加权大盘</strong>
                    <span>${rangeLabel}</span>
                </div>
                <small>${metaText}</small>
            </div>
            <div class="gov-summary-strip gov-summary-strip-dashboard">
                ${_govDashboardCardHtml('总召回频数', _govFormatInteger(metrics.totalRecall), { cardClass: 'gov-summary-card-total' })}
                ${_govDashboardCardHtml('总有效召回频数', _govFormatInteger(metrics.totalValid), { valueClass: 'is-success' })}
                ${_govDashboardCardHtml('整体有效召回率', _govFormatPercent(metrics.overallValidRate), { valueClass: 'is-info' })}
                <div class="gov-summary-divider"></div>
                ${_govDashboardCardHtml('平均召回频数', _govFormatAverage(metrics.avgRecall), { note: '总召回 / 总权重' })}
                ${_govDashboardCardHtml('平均有效召回频数', _govFormatAverage(metrics.avgValidRecall), { valueClass: 'is-success', note: '总有效 / 总权重' })}
                ${_govDashboardCardHtml('平均召回占比', _govFormatPercent(metrics.avgRecallRatio), { valueClass: 'is-info', note: '按月占比加权' })}
                ${_govDashboardCardHtml('平均有效召回占比', _govFormatPercent(metrics.avgValidRecallRatio), { valueClass: 'is-info', note: '按月占比加权' })}
                ${_govDashboardCardHtml('平均有效召回率', _govFormatPercent(metrics.avgValidRate), { valueClass: 'is-info', note: '按月有效率加权' })}
            </div>
        </div>
    `;
}

function renderGovSummaryPanel() {
    const summaryEl = document.getElementById('govSummary');
    if (!summaryEl) return;
    summaryEl.innerHTML = `
        ${_govBuildNativeSummaryHtml()}
        ${_govBuildDashboardSummaryHtml()}
    `;
}

function _govRenderDashboardSummary(startMonth, endMonth, months, metrics) {
    currentGovDashboardMetrics = metrics || null;
    currentGovDashboardRange = { startMonth: startMonth || '', endMonth: endMonth || '', months: months || [] };
    govDashboardStatusMessage = metrics?.hasData ? '' : '暂无可统计数据';
    govDashboardStatusClass = 'text-muted';
    renderGovSummaryPanel();
}

async function loadGovDashboardData(options = {}) {
    const startMonth = document.getElementById('govDashboardStartMonth')?.value;
    const endMonth = document.getElementById('govDashboardEndMonth')?.value;

    if (!startMonth) {
        if (govMonths.length === 0) await loadGovMonths();
        _govRenderDashboardMessage('请选择大盘统计月份范围');
        return;
    }

    saveGovDashboardRangeFromControls();
    _govRenderDashboardMessage('大盘加载中...');

    try {
        const normalizedRange = _govNormalizeDashboardRange(startMonth, endMonth);
        const params = new URLSearchParams({ month: normalizedRange.startMonth });
        if (normalizedRange.endMonth) params.set('end_month', normalizedRange.endMonth);
        const url = `/governance/data?${params.toString()}`;
        if (options.reuse && govLastDashboardKey === url && currentGovDashboardMetrics) {
            _govRenderDashboardSummary(
                normalizedRange.startMonth,
                normalizedRange.endMonth,
                govDashboardMonths,
                currentGovDashboardMetrics
            );
            if (govData.length > 0) {
                renderGovTable();
                updateGovPagination();
            }
            return;
        }
        const res = await api(url);

        if (!res.success) {
            _govRenderDashboardMessage(res.message || '大盘加载失败', 'error-message');
            return;
        }

        govDashboardMonths = res.months || [];
        currentGovDashboardSummary = res.summary || {};
        govDashboardData = (res.data || []).map(item => ({
            ...item,
            weighted_summary: _govComputeItemWeightedMetrics(item, govDashboardMonths, currentGovDashboardSummary)
        }));
        govDashboardDataById = new Map(govDashboardData.map(item => [String(item.id || '').trim(), item]));

        const metrics = _govComputeDashboardMetrics(govDashboardData, govDashboardMonths, currentGovDashboardSummary);
        govLastDashboardKey = url;
        _govRenderDashboardSummary(normalizedRange.startMonth, normalizedRange.endMonth, govDashboardMonths, metrics);
        if (govData.length > 0) {
            renderGovTable();
            updateGovPagination();
        }
    } catch (e) {
        _govRenderDashboardMessage(`大盘加载失败: ${e.message}`, 'error-message');
    }
}

function renderGovTable() {
    const tbody = document.getElementById('govTableBody');
    const thead = document.getElementById('govThead');
    if (!tbody || !thead) return;
    
    // 1. Rebuild Headers dynamically
    thead.innerHTML = '';
    
    // Row 1
    const tr1 = document.createElement('tr');
    
    // Fixed Columns (WikiID, Question, AI Score)
    ['WikiID', '问题', 'AI评分'].forEach(text => {
        const th = document.createElement('th');
        th.rowSpan = 2;
        th.style.verticalAlign = 'middle';
        th.style.backgroundColor = '#f8f9fa';
        th.textContent = text;
        // Basic sorting support for fixed columns
        if (text === 'WikiID') {
             th.innerHTML = _govSortableHeaderHtml('WikiID', 'id');
             th.className = 'col-id';
        } else if (text === '问题') {
             th.innerHTML = _govSortableHeaderHtml('问题', 'question');
             th.className = 'col-question';
        } else if (text === 'AI评分') {
             th.innerHTML = _govSortableHeaderHtml('AI评分', 'ai_score');
             th.className = 'col-score';
        }
        tr1.appendChild(th);
    });
    
    // Dynamic Month Columns
    currentGovMonths.forEach(month => {
        const th = document.createElement('th');
        th.colSpan = 5; // 5 sub-columns
        th.className = 'text-center';
        th.style.borderBottom = '1px solid #dee2e6';
        th.style.backgroundColor = '#e9ecef';
        th.innerHTML = `<b>${month}</b>`;
        tr1.appendChild(th);
    });

    const thWeighted = document.createElement('th');
    thWeighted.colSpan = 5;
    thWeighted.className = 'text-center gov-weighted-group';
    thWeighted.style.borderBottom = '1px solid #dee2e6';
    thWeighted.style.backgroundColor = '#e0f2fe';
    thWeighted.innerHTML = '<b>大盘周期加权汇总</b>';
    tr1.appendChild(thWeighted);
    
    // Status Column
    const thStatus = document.createElement('th');
    thStatus.rowSpan = 2;
    thStatus.style.verticalAlign = 'middle';
    thStatus.style.backgroundColor = '#f8f9fa';
    thStatus.innerHTML = _govSortableHeaderHtml('状态', 'status');
    thStatus.className = 'col-status';
    tr1.appendChild(thStatus);
    
    thead.appendChild(tr1);
    
    // Row 2 (Sub-columns)
    const tr2 = document.createElement('tr');
    currentGovMonths.forEach(month => {
        const specs = [
            { label: '召回频数', metric: 'recall_count', className: 'col-count' },
            { label: '有效召回频数', metric: 'valid_recall_count', className: 'col-count' },
            { label: '召回占比', metric: 'recall_ratio', className: 'col-ratio' },
            { label: '有效召回占比', metric: 'valid_recall_ratio', className: 'col-ratio' },
            { label: '有效召回率', metric: 'valid_rate', className: 'col-ratio' }
        ];

        specs.forEach(spec => {
             const th = document.createElement('th');
             th.className = spec.className;
             th.style.fontSize = '0.9em';
             th.style.color = '#666';
             const sortKey = `m|${month}|${spec.metric}`;
             th.innerHTML = _govSortableHeaderHtml(spec.label, sortKey);
             tr2.appendChild(th);
        });
    });

    _govGetWeightedMetricSpecs().forEach(spec => {
        const th = document.createElement('th');
        th.className = 'col-weighted';
        th.style.fontSize = '0.9em';
        th.style.color = '#0369a1';
        th.innerHTML = _govSortableHeaderHtml(spec.label, spec.metric);
        tr2.appendChild(th);
    });
    thead.appendChild(tr2);

    // 2. Render Rows
    tbody.innerHTML = '';
    
    const data = _getFilteredGovData();
    
    // Pagination
    const start = (govCurrentPage - 1) * govPageSize;
    const end = start + govPageSize;
    const pageData = data.slice(start, end);
    
    if (pageData.length === 0) {
         // Calculate colspan: 3 (fixed) + months * 5 + 5 (weighted summary) + 1 (status)
         const totalCols = 3 + (currentGovMonths.length * 5) + 5 + 1;
         tbody.innerHTML = `<tr><td colspan="${totalCols}" class="empty-message">暂无数据</td></tr>`;
         document.getElementById('govPageInfo').innerText = '共 0 条';
         document.getElementById('prevGovPageBtn').disabled = true;
         document.getElementById('nextGovPageBtn').disabled = true;
         return;
    }
    
    pageData.forEach(item => {
        const tr = document.createElement('tr');
        
        // ID
        tr.innerHTML += `<td>${item.id}</td>`;
        
        // Question
        tr.innerHTML += `<td class="gov-question-cell" title="${escapeHtml(item.question)}">${escapeHtml(item.question)}</td>`;
        
        // Score
        const score = item.ai_score;
        let scoreClass = 'score-na';
        if (score >= 80) scoreClass = 'score-high';
        else if (score >= 60) scoreClass = 'score-medium';
        else if (score > 0) scoreClass = 'score-low';
        tr.innerHTML += `<td><span class="score-badge ${scoreClass}">${score || '-'}</span></td>`;
        
        // Monthly Data
        currentGovMonths.forEach(month => {
            const mData = item.monthly_data && item.monthly_data[month] ? item.monthly_data[month] : { recall_count: 0, valid_recall_count: 0 };
            const recall = mData.recall_count || 0;
            const valid = mData.valid_recall_count || 0;
            
            // Ratios need total for that month
            const monthTotalRecall = currentGovSummary[month]?.total_recall || 0;
            const monthTotalValid = currentGovSummary[month]?.total_valid || 0;
            
            const recallRatio = monthTotalRecall > 0 ? ((recall / monthTotalRecall) * 100).toFixed(2) + '%' : '0.00%';
            const validRecallRatio = monthTotalValid > 0 ? ((valid / monthTotalValid) * 100).toFixed(2) + '%' : '0.00%';
            const validRate = recall > 0 ? ((valid / recall) * 100).toFixed(2) + '%' : '0.00%';
            
            tr.innerHTML += `
                <td class="text-center">${recall}</td>
                <td class="text-center">${valid}</td>
                <td class="text-center text-muted">${recallRatio}</td>
                <td class="text-center text-muted">${validRecallRatio}</td>
                <td class="text-center">${validRate}</td>
            `;
        });

        const weightedMetrics = _govGetDashboardWeightedMetricsForItem(item);
        _govGetWeightedMetricSpecs().forEach(spec => {
            tr.innerHTML += `<td class="text-center gov-weighted-cell">${_govFormatWeightedMetric(weightedMetrics?.[spec.metric], spec.type)}</td>`;
        });
        
        // Status
        const statusClass = item.status === '使用中' ? 'status-active' : 'status-deleted';
        tr.innerHTML += `<td><span class="status-badge ${statusClass}">${item.status}</span></td>`;
        
        tbody.appendChild(tr);
    });

    document.getElementById('govPageInfo').innerText = `共 ${data.length} 条`;
    document.getElementById('prevGovPageBtn').disabled = govCurrentPage === 1;
    document.getElementById('nextGovPageBtn').disabled = end >= data.length;
    makeTableResizable('govTable');
}


function changeGovPage(offset) {
    govCurrentPage += offset;
    if (govCurrentPage < 1) govCurrentPage = 1;
    renderGovTable();
}

function changeGovPageSize() {
    govPageSize = parseInt(document.getElementById('govPageSizeSelect').value);
    govCurrentPage = 1;
    renderGovTable();
}

function handleGovSort(field) {
    if (govSortBy === field) {
        govSortDir = govSortDir === 'asc' ? 'desc' : 'asc';
    } else {
        govSortBy = field;
        govSortDir = 'desc';
    }
    renderGovTable();
}

function applyGovFilter() {
    govCurrentPage = 1;
    renderGovTable();
}

function _updateGovAdvancedSummary() {
    const summary = document.getElementById('govAdvancedSummary');
    if (!summary) return;
    const months = _govGetActiveAdvancedMonths();
    if (months.length === 0) {
        summary.innerHTML = '<strong>当前已启用：</strong> 未启用按月高级条件';
        return;
    }
    summary.innerHTML = `<strong>当前已启用：</strong> ${months.join('、')}`;
}

function _updateGovAdvancedIndicator(isExpanded = null) {
    const btn = document.getElementById('govAdvancedToggleBtn');
    if (!btn) return;
    const count = _govGetActiveAdvancedMonths().length;
    const expanded = (isExpanded === null)
        ? !(document.getElementById('govAdvancedInlineBar')?.classList.contains('d-none'))
        : !!isExpanded;
    const suffix = expanded ? '▲' : '▼';
    btn.textContent = count > 0 ? `高级条件(${count}) ${suffix}` : `高级条件 ${suffix}`;
    _updateGovAdvancedSummary();
}

function toggleGovAdvancedBar(forceExpand = null) {
    const bar = document.getElementById('govAdvancedInlineBar');
    const btn = document.getElementById('govAdvancedToggleBtn');
    if (!bar || !btn) return;

    const shouldExpand = (forceExpand === null) ? bar.classList.contains('d-none') : !!forceExpand;
    bar.classList.toggle('d-none', !shouldExpand);
    _updateGovAdvancedIndicator(shouldExpand);
}

function resetGovFilter() {
    document.getElementById('govFilterId').value = '';
    document.getElementById('govFilterQuestion').value = '';
    if (document.getElementById('govFilterMonths')) document.getElementById('govFilterMonths').value = '';
    if (document.getElementById('govFilterRecallMin')) document.getElementById('govFilterRecallMin').value = '';
    if (document.getElementById('govFilterRecallMax')) document.getElementById('govFilterRecallMax').value = '';
    if (document.getElementById('govFilterValidRecallMin')) document.getElementById('govFilterValidRecallMin').value = '';
    if (document.getElementById('govFilterValidRecallMax')) document.getElementById('govFilterValidRecallMax').value = '';
    document.getElementById('govFilterStatus').value = '';
    govAdvancedConditions = {};
    toggleGovAdvancedBar(false);
    _updateGovAdvancedIndicator(false);
    applyGovFilter();
}

function openGovAdvancedFilterModal() {
    const modal = document.getElementById('govAdvancedFilterModal');
    const tbody = document.getElementById('govAdvancedFilterTableBody');
    if (!modal || !tbody) return;
    tbody.innerHTML = '';
    (currentGovMonths || []).forEach(month => {
        const c = govAdvancedConditions[month] || {};
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="font-weight:500;">${month}</td>
            <td>
                <div style="display:flex; gap:4px; align-items:center;">
                    <input type="number" class="form-control gov-adv-recall-min" data-month="${month}" placeholder="≥" style="width:70px;" min="0" step="1" value="${c.recallMin ?? ''}">
                    <span style="font-size:12px;color:#999;">~</span>
                    <input type="number" class="form-control gov-adv-recall-max" data-month="${month}" placeholder="≤" style="width:70px;" min="0" step="1" value="${c.recallMax ?? ''}">
                </div>
            </td>
            <td>
                <div style="display:flex; gap:4px; align-items:center;">
                    <input type="number" class="form-control gov-adv-valid-min" data-month="${month}" placeholder="≥" style="width:70px;" min="0" step="1" value="${c.validMin ?? ''}">
                    <span style="font-size:12px;color:#999;">~</span>
                    <input type="number" class="form-control gov-adv-valid-max" data-month="${month}" placeholder="≤" style="width:70px;" min="0" step="1" value="${c.validMax ?? ''}">
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
    modal.style.display = 'block';
}

function closeGovAdvancedFilterModal() {
    const modal = document.getElementById('govAdvancedFilterModal');
    if (modal) modal.style.display = 'none';
}

function clearGovAdvancedConditions() {
    govAdvancedConditions = {};
    const tbody = document.getElementById('govAdvancedFilterTableBody');
    if (tbody) {
        tbody.querySelectorAll('input').forEach(input => input.value = '');
    }
    _updateGovAdvancedIndicator();
}

function applyGovAdvancedConditions() {
    const tbody = document.getElementById('govAdvancedFilterTableBody');
    if (!tbody) return;
    const next = {};
    (currentGovMonths || []).forEach(month => {
        const recallMinInput = tbody.querySelector(`.gov-adv-recall-min[data-month="${month}"]`);
        const recallMaxInput = tbody.querySelector(`.gov-adv-recall-max[data-month="${month}"]`);
        const validMinInput = tbody.querySelector(`.gov-adv-valid-min[data-month="${month}"]`);
        const validMaxInput = tbody.querySelector(`.gov-adv-valid-max[data-month="${month}"]`);
        const c = {
            recallMin: _govParseNumber(recallMinInput?.value ?? ''),
            recallMax: _govParseNumber(recallMaxInput?.value ?? ''),
            validMin: _govParseNumber(validMinInput?.value ?? ''),
            validMax: _govParseNumber(validMaxInput?.value ?? '')
        };
        if (c.recallMin !== null || c.recallMax !== null || c.validMin !== null || c.validMax !== null) {
            next[month] = c;
        }
    });
    govAdvancedConditions = next;
    closeGovAdvancedFilterModal();
    _updateGovAdvancedIndicator();
    applyGovFilter();
}

async function exportGovernanceFilteredExcel() {
    const btn = document.getElementById('govExportBtn');
    const originalText = btn ? btn.innerText : '导出 Excel';
    const data = _getFilteredGovData();
    const months = Array.isArray(currentGovMonths) ? [...currentGovMonths] : [];
    const rows = data.map(item => ({
        ...item,
        weighted_summary: _govGetDashboardWeightedMetricsForItem(item)
    }));

    if (data.length === 0) {
        alert('当前筛选结果为空，无法导出。');
        return;
    }

    try {
        if (btn) {
            btn.disabled = true;
            btn.innerText = '导出中...';
        }
        const resp = await fetch(`${API_BASE}/governance/export`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ months, rows })
        });
        if (!resp.ok) {
            let message = '导出失败';
            try {
                const err = await resp.json();
                message = err.message || message;
            } catch (_) {}
            throw new Error(message);
        }
        const blob = await resp.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `知识库治理筛选结果_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.xlsx`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + (e?.message || String(e)));
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = originalText;
        }
    }
}

function openGovImportModal() {
    document.getElementById('govImportModal').style.display = 'block';
}

function closeGovImportModal() {
    document.getElementById('govImportModal').style.display = 'none';
}

async function deleteGovernanceData() {
    const month = document.getElementById('govStartMonth')?.value;
    if (!month) {
        alert('请先选择要删除的月份。');
        return;
    }

    const confirmed = confirm(`确认删除 ${month} 的知识库治理召回数据吗？此操作不可恢复。`);
    if (!confirmed) return;

    try {
        const res = await api('/governance/delete', 'POST', { month });
        if (!res.success) {
            alert('删除失败: ' + (res.message || '未知错误'));
            return;
        }

        const deletedText = (res.deleted === null || res.deleted === undefined)
            ? ''
            : `，共删除 ${res.deleted} 条`;
        alert(`已删除 ${month} 数据${deletedText}。`);
        await loadGovMonths();
    } catch (e) {
        alert('删除异常: ' + (e?.message || String(e)));
    }
}

async function confirmGovImport() {
    const month = document.getElementById('govImportMonth').value;
    const fileInput = document.getElementById('govImportFileModal');
    
    if (!month) { alert('请选择月份'); return; }
    if (!fileInput.files.length) { alert('请选择文件'); return; }
    
    const formData = new FormData();
    formData.append('month', month);
    formData.append('file', fileInput.files[0]);
    
    const btn = document.getElementById('confirmImportBtn');
    btn.disabled = true;
    btn.innerText = '导入中...';
    
    try {
        const res = await fetch('/api/governance/import', {
            method: 'POST',
            body: formData
        }).then(r => r.json());
        
        if (res.success) {
            alert(`导入成功！共导入 ${res.count} 条数据`);
            closeGovImportModal();
            await loadGovMonths(month);
        } else {
            alert('导入失败: ' + res.message);
        }
    } catch (e) {
        alert('导入异常: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.innerText = '开始导入';
    }
}

function downloadGovernanceTemplate() {
    // Generate a simple CSV template
    const headers = ['WikiID', '召回频数', '有效召回频数'];
    const csvContent = "data:text/csv;charset=utf-8," + headers.join(",");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "recall_data_template.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// ==========================================
// Quality Control Center Logic
// ==========================================
let qcPools = [];
let qcActivePoolId = null;
let qcRawPage = 1;
let qcRawTotal = 0;
let qcRawPageSize = 50;
let qcTaskPage = 1;
let qcTaskTotal = 0;
let qcTaskPageSize = 20;
let qcSelectedRaw = new Set();
let qcSelectedTasks = new Set();
let qcLastTasks = [];
let qcLoadedOnce = false;
let qcActivePane = 'tasks';
let qcWizardStep = 1;
let qcWizardEditingPoolId = null;
let qcWizardSavedPoolId = null;
let qcWizardScanResult = null;
let qcConditionSeq = 0;
let qcMappingDraftBySource = {};

const QC_SOURCE_LABELS = {
    scoring: '知识库评分',
    governance: '知识库治理',
    external: '外部检测'
};
const QC_STATUS_LABELS = {
    pending: '待处理',
    processing: '处理中',
    completed: '已完成',
    ignored: '已忽略'
};
const QC_FIELD_OPTIONS = {
    scoring: [
        ['kb_id', 'WikiID', 'text'],
        ['question_content', '问题', 'text'],
        ['answer_content', '答案', 'text'],
        ['status', '评分状态', 'text'],
        ['total_score', '总评分', 'number'],
        ['remarks', '处理建议/备注', 'text'],
        ['updated_at', '评分更新时间', 'text']
    ],
    governance: [
        ['kb_id', 'WikiID', 'text'],
        ['question', '问题', 'text'],
        ['conclusion', '结论', 'text'],
        ['analysis', '分析评价', 'text'],
        ['suggestion', '优化建议', 'text'],
        ['remarks', '处理建议/备注', 'text'],
        ['status', '知识库状态', 'text'],
        ['month', '月份', 'text'],
        ['recall_count', '每月召回频数', 'number'],
        ['valid_recall_count', '每月有效召回频数', 'number'],
        ['valid_rate', '每月有效召回率', 'number'],
        ['avg_recall_count', '平均召回频数', 'number'],
        ['avg_valid_recall_count', '平均有效召回频数', 'number'],
        ['avg_valid_rate', '平均有效召回率', 'number'],
        ['weighted_avg_recall', '大盘周期加权_平均召回频数', 'number'],
        ['weighted_avg_valid_recall', '大盘周期加权_平均有效召回频数', 'number'],
        ['weighted_avg_recall_ratio', '大盘周期加权_平均召回占比', 'number'],
        ['weighted_avg_valid_recall_ratio', '大盘周期加权_平均有效召回占比', 'number'],
        ['weighted_avg_valid_rate', '大盘周期加权_平均有效召回率', 'number']
    ],
    external: [
        ['wiki_id', 'WikiID', 'text'],
        ['issue_text', '问题', 'text'],
        ['remediation_reference', '建议操作', 'text'],
        ['priority', '优先级', 'text']
    ]
};
const QC_MAPPING_FIELDS = [
    ['wiki_id', 'WikiID 字段', false],
    ['issue', '问题字段', true],
    ['action', '建议操作字段', true],
    ['priority', '优先级字段', true]
];
const QC_MAPPING_DEFAULTS = {
    scoring: { wiki_id: 'kb_id', issue: '', action: 'remarks', priority: '' },
    governance: { wiki_id: 'kb_id', issue: '', action: 'suggestion', priority: '' },
    external: { wiki_id: 'wiki_id', issue: 'issue_text', action: 'remediation_reference', priority: 'priority' }
};
const QC_OPERATOR_OPTIONS = [
    ['contains', '包含'],
    ['eq', '等于'],
    ['neq', '不等于'],
    ['gt', '大于'],
    ['gte', '大于等于'],
    ['lt', '小于'],
    ['lte', '小于等于'],
    ['between', '区间'],
    ['empty', '为空'],
    ['not_empty', '不为空']
];

function qcStatusLabel(status) {
    return QC_STATUS_LABELS[status] || status || '-';
}

function qcSourceLabel(source) {
    return QC_SOURCE_LABELS[source] || source || '-';
}

function qcPriorityLabel(priority) {
    return String(priority || '').toUpperCase() || '-';
}

function qcSetText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = String(text ?? '');
}

function qcResetWizardAggregationState() {
    qcWizardSavedPoolId = null;
    qcWizardScanResult = null;
    qcRenderWizardPreview(null, '待扫描');
}

function qcRenderWizardPreview(result, message = '') {
    const summary = result?.raw_summary || result || {};
    const sourceCounts = summary.source_counts || {};
    qcSetText('qcWizardPreviewRaw', summary.raw_count ?? '--');
    qcSetText('qcWizardPreviewWiki', summary.wiki_count ?? '--');
    qcSetText('qcWizardPreviewScoring', sourceCounts.scoring ?? '--');
    qcSetText('qcWizardPreviewGovernance', sourceCounts.governance ?? '--');
    qcSetText('qcWizardPreviewExternal', sourceCounts.external ?? '--');
    qcSetText('qcWizardPreviewMessage', message || (result ? '扫描完成' : '待扫描'));
}

function qcWizardHasNoPendingAggregation() {
    if (!qcWizardScanResult) return false;
    const summary = qcWizardScanResult.raw_summary || {};
    return Number(summary.raw_count || 0) <= 0;
}

function qcGetGovernanceRuleRange() {
    const saved = (typeof _govReadDashboardRange === 'function') ? _govReadDashboardRange() : {};
    const startMonth = (
        document.getElementById('govDashboardStartMonth')?.value ||
        currentGovDashboardRange?.startMonth ||
        saved.startMonth ||
        ''
    );
    const endMonth = (
        document.getElementById('govDashboardEndMonth')?.value ||
        currentGovDashboardRange?.endMonth ||
        saved.endMonth ||
        ''
    );
    if (typeof _govNormalizeDashboardRange === 'function') {
        return _govNormalizeDashboardRange(startMonth, endMonth);
    }
    return (startMonth && endMonth && startMonth > endMonth)
        ? { startMonth: endMonth, endMonth: startMonth }
        : { startMonth, endMonth };
}

function qcGetActivePool() {
    return qcPools.find(p => String(p.id) === String(qcActivePoolId)) || null;
}

function qcGetRulePayload() {
    const rows = Array.from(document.querySelectorAll('#qcConditionRows .qc-condition-row'));
    const conditions = rows.map(row => {
        const source = row.querySelector('.qc-cond-source')?.value || '';
        const fieldEl = row.querySelector('.qc-cond-field');
        const field = fieldEl?.value || '';
        const fieldLabel = fieldEl?.selectedOptions?.[0]?.textContent || field;
        const operatorEl = row.querySelector('.qc-cond-operator');
        const operator = operatorEl?.value || 'contains';
        const operatorLabel = operatorEl?.selectedOptions?.[0]?.textContent || operator;
        const value = String(row.querySelector('.qc-cond-value')?.value ?? '').trim();
        const value2 = String(row.querySelector('.qc-cond-value2')?.value ?? '').trim();
        if (!source || !field || (!['empty', 'not_empty'].includes(operator) && !value && operator !== 'between')) return null;
        return { source, field, field_label: fieldLabel, operator, operator_label: operatorLabel, value, value2 };
    }).filter(Boolean);
    const payload = {
        version: 2,
        logic: document.getElementById('qcRuleLogic')?.value || 'AND',
        conditions
    };
    const selectedSources = qcGetSelectedSources();
    const hasGovernanceCondition = conditions.some(c => c.source === 'governance') || selectedSources.includes('governance');
    if (hasGovernanceCondition) {
        const range = qcGetGovernanceRuleRange();
        if (range.startMonth) payload.governance_month_start = range.startMonth;
        if (range.endMonth) payload.governance_month_end = range.endMonth;
    }
    return payload;
}

function qcGetSelectedSources() {
    return Array.from(document.querySelectorAll('#qcPoolWizardModal .qc-source-check:checked'))
        .map(cb => cb.value)
        .filter(Boolean);
}

function qcDefaultConditionForSource(source) {
    const defaults = {
        scoring: { source: 'scoring', field: 'total_score', operator: 'lte', value: '70' },
        governance: { source: 'governance', field: 'weighted_avg_recall', operator: 'gt', value: '0' },
        external: { source: 'external', field: 'issue_text', operator: 'not_empty', value: '' }
    };
    return defaults[source] || defaults.governance;
}

function qcDefaultMappingForSource(source) {
    return { ...(QC_MAPPING_DEFAULTS[source] || QC_MAPPING_DEFAULTS.external) };
}

function qcMappingAliasValue(source, key, value) {
    const norm = String(value || '').trim().replace(/[\s_：:]+/g, '').toLowerCase();
    if (!norm) return '';
    const aliases = {
        scoring: {
            wiki_id: { wikiid: 'kb_id', kbid: 'kb_id', 知识库id: 'kb_id' },
            issue: { 问题: 'question_content', 问题描述: 'question_content', 建议操作: 'remarks', 处理建议: 'remarks', 备注: 'remarks' },
            action: { 建议操作: 'remarks', 处理建议: 'remarks', 备注: 'remarks' },
            priority: { 优先级: '' }
        },
        governance: {
            wiki_id: { wikiid: 'kb_id', kbid: 'kb_id', 知识库id: 'kb_id' },
            issue: { 问题: 'question' },
            action: { 建议操作: 'suggestion', 优化建议: 'suggestion', 处理建议: 'suggestion', 分析评价: 'analysis', 结论: 'conclusion', 备注: 'remarks' },
            priority: { 优先级: '' }
        },
        external: {
            wiki_id: { wikiid: 'wiki_id', kbid: 'wiki_id', 知识库id: 'wiki_id' },
            issue: { 问题: 'issue_text', 问题描述: 'issue_text', 检测问题: 'issue_text' },
            action: { 建议操作: 'remediation_reference', 建议: 'remediation_reference', 处理建议: 'remediation_reference' },
            priority: { 优先级: 'priority', p级别: 'priority', 等级: 'priority' }
        }
    };
    const sourceAliases = aliases[source]?.[key] || {};
    return Object.prototype.hasOwnProperty.call(sourceAliases, norm) ? sourceAliases[norm] : null;
}

function qcResolveMappingValueForSource(source, key, value) {
    const raw = String(value ?? '').trim();
    if (!raw) return '';
    const alias = qcMappingAliasValue(source, key, raw);
    if (alias !== null) return alias;
    const norm = raw.replace(/[\s_：:]+/g, '').toLowerCase();
    const option = (QC_FIELD_OPTIONS[source] || []).find(([fieldValue, label]) => {
        return [fieldValue, label].some(item => String(item || '').replace(/[\s_：:]+/g, '').toLowerCase() === norm);
    });
    return option ? option[0] : raw;
}

function qcNormalizeMappingConfig(mapping = {}, sources = []) {
    const selectedSources = (sources && sources.length) ? sources : ['governance'];
    const bySource = mapping?.by_source || mapping?.bySource || mapping?.source_mappings || {};
    const hasBySource = bySource && typeof bySource === 'object' && !Array.isArray(bySource);
    const out = {};
    selectedSources.forEach(source => {
        const defaults = qcDefaultMappingForSource(source);
        const raw = hasBySource ? (bySource[source] || {}) : (mapping || {});
        const item = {};
        QC_MAPPING_FIELDS.forEach(([key]) => {
            const hasRawValue = raw && Object.prototype.hasOwnProperty.call(raw, key);
            const resolved = hasRawValue ? qcResolveMappingValueForSource(source, key, raw?.[key]) : '';
            item[key] = hasRawValue ? resolved : (defaults[key] || '');
        });
        out[source] = item;
    });
    return out;
}

function qcReadMappingDraftFromDom() {
    const next = { ...qcMappingDraftBySource };
    document.querySelectorAll('#qcMappingRows .qc-mapping-card').forEach(card => {
        const source = card.dataset.source;
        if (!source) return;
        const item = {};
        card.querySelectorAll('.qc-map-field').forEach(select => {
            const key = select.dataset.mapKey;
            if (key) item[key] = String(select.value || '').trim();
        });
        next[source] = { ...qcDefaultMappingForSource(source), ...item };
    });
    qcMappingDraftBySource = next;
    return next;
}

function qcMappingFieldOptionsForSource(source, selected = '', allowEmpty = true) {
    const options = [...(QC_FIELD_OPTIONS[source] || [])];
    const hasSelected = !selected || options.some(([value]) => value === selected);
    const emptyOption = allowEmpty ? '<option value="">不设置</option>' : '';
    const customOption = (!hasSelected && selected)
        ? `<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)}</option>`
        : '';
    return `${emptyOption}${customOption}${options.map(([value, label]) => {
        return `<option value="${escapeHtml(value)}" ${value === selected ? 'selected' : ''}>${escapeHtml(label)}</option>`;
    }).join('')}`;
}

function qcRenderMappingRows(options = {}) {
    const host = document.getElementById('qcMappingRows');
    if (!host) return;
    if (options.preserveDom !== false) qcReadMappingDraftFromDom();
    const sources = qcGetSelectedSources();
    if (!sources.length) {
        host.innerHTML = '<div class="qc-empty-panel">请先选择数据来源</div>';
        return;
    }
    qcMappingDraftBySource = qcNormalizeMappingConfig({ by_source: qcMappingDraftBySource }, sources);
    host.innerHTML = sources.map(source => {
        const mapping = qcMappingDraftBySource[source] || qcDefaultMappingForSource(source);
        const fields = QC_MAPPING_FIELDS.map(([key, label, allowEmpty]) => `
            <label>
                <span>${escapeHtml(label)}</span>
                <select class="form-select qc-map-field" data-map-key="${escapeHtml(key)}" onchange="qcReadMappingDraftFromDom()">
                    ${qcMappingFieldOptionsForSource(source, mapping[key] || '', allowEmpty)}
                </select>
            </label>
        `).join('');
        return `
            <div class="qc-mapping-card" data-source="${escapeHtml(source)}">
                <div class="qc-mapping-card-head">
                    <b>${escapeHtml(qcSourceLabel(source))}</b>
                </div>
                <div class="qc-mapping-grid">${fields}</div>
            </div>
        `;
    }).join('');
}

function qcBuildFieldMappingPayload() {
    const sources = qcGetSelectedSources();
    const bySource = qcNormalizeMappingConfig({ by_source: qcReadMappingDraftFromDom() }, sources);
    qcMappingDraftBySource = bySource;
    const primary = bySource[sources[0]] || {};
    return {
        version: 2,
        ...primary,
        by_source: bySource
    };
}

function qcApplyPoolToForm(pool) {
    const setVal = (id, value = '') => {
        const el = document.getElementById(id);
        if (el) el.value = value ?? '';
    };
    setVal('qcPoolName', pool?.name || '');
    const rule = pool?.rule_config || {};
    setVal('qcRuleLogic', rule.logic || 'AND');
    const sources = new Set(pool?.sources || ['scoring', 'governance']);
    document.querySelectorAll('#qcPoolWizardModal .qc-source-check').forEach(cb => {
        cb.checked = sources.has(cb.value);
    });
    qcMappingDraftBySource = qcNormalizeMappingConfig(pool?.field_mapping || {}, Array.from(sources));
    qcRenderMappingRows({ preserveDom: false });
    qcRenderConditionRows(rule.conditions || []);
}

function qcFieldOptionsForSource(source, selected = '') {
    const list = QC_FIELD_OPTIONS[source] || [];
    return list.map(([value, label]) => `<option value="${escapeHtml(value)}" ${value === selected ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('');
}

function qcSourceOptions(selected = '') {
    const selectedSources = qcGetSelectedSources();
    const values = selectedSources.length ? selectedSources : Object.keys(QC_SOURCE_LABELS);
    const unique = selected && !values.includes(selected) ? [selected, ...values] : values;
    return unique.map(value => `<option value="${escapeHtml(value)}" ${value === selected ? 'selected' : ''}>${escapeHtml(qcSourceLabel(value))}</option>`).join('');
}

function qcOperatorOptions(selected = '') {
    return QC_OPERATOR_OPTIONS.map(([value, label]) => `<option value="${escapeHtml(value)}" ${value === selected ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('');
}

function qcRenderConditionRows(conditions = []) {
    const host = document.getElementById('qcConditionRows');
    if (!host) return;
    host.innerHTML = '';
    const defaultSource = qcGetSelectedSources()[0] || 'governance';
    const rows = Array.isArray(conditions) && conditions.length ? conditions : [qcDefaultConditionForSource(defaultSource)];
    rows.forEach(c => qcAddConditionRow(c));
    qcNormalizeConditionRowsForSources();
}

function qcAddConditionRow(condition = {}) {
    const host = document.getElementById('qcConditionRows');
    if (!host) return;
    const selectedSources = qcGetSelectedSources();
    let source = condition.source || selectedSources[0] || 'governance';
    if (selectedSources.length && !selectedSources.includes(source)) source = selectedSources[0];
    const rowId = `qc-cond-${++qcConditionSeq}`;
    const row = document.createElement('div');
    row.className = 'qc-condition-row';
    row.dataset.rowId = rowId;
    row.innerHTML = `
        <select class="form-select qc-cond-source" onchange="qcUpdateConditionFieldOptions(this)">
            ${qcSourceOptions(source)}
        </select>
        <select class="form-select qc-cond-field">${qcFieldOptionsForSource(source, condition.field || '')}</select>
        <select class="form-select qc-cond-operator" onchange="qcSyncConditionValueInputs(this)">${qcOperatorOptions(condition.operator || 'contains')}</select>
        <input class="form-control qc-cond-value" type="text" placeholder="值" value="${escapeHtml(condition.value ?? '')}">
        <input class="form-control qc-cond-value2" type="text" placeholder="结束值" value="${escapeHtml(condition.value2 ?? '')}">
        <button type="button" class="danger-btn qc-icon-btn" title="删除条件" onclick="this.closest('.qc-condition-row').remove()"><i class="fas fa-trash"></i></button>
    `;
    host.appendChild(row);
    qcSyncConditionValueInputs(row.querySelector('.qc-cond-operator'));
}

function qcNormalizeConditionRowsForSources() {
    const rows = Array.from(document.querySelectorAll('#qcConditionRows .qc-condition-row'));
    const selectedSources = qcGetSelectedSources();
    if (!rows.length) {
        if (selectedSources.length) qcRenderConditionRows([qcDefaultConditionForSource(selectedSources[0])]);
        qcRenderMappingRows();
        return;
    }
    rows.forEach(row => {
        const sourceSelect = row.querySelector('.qc-cond-source');
        const fieldSelect = row.querySelector('.qc-cond-field');
        if (!sourceSelect || !fieldSelect) return;
        let source = sourceSelect.value || selectedSources[0] || 'governance';
        if (selectedSources.length && !selectedSources.includes(source)) source = selectedSources[0];
        const previousField = fieldSelect.value;
        sourceSelect.innerHTML = qcSourceOptions(source);
        sourceSelect.value = source;
        fieldSelect.innerHTML = qcFieldOptionsForSource(source, previousField);
        if (!fieldSelect.value && fieldSelect.options.length) fieldSelect.selectedIndex = 0;
    });
    qcRenderMappingRows();
}

function qcUpdateConditionFieldOptions(sourceSelect) {
    const row = sourceSelect.closest('.qc-condition-row');
    const field = row?.querySelector('.qc-cond-field');
    if (!field) return;
    field.innerHTML = qcFieldOptionsForSource(sourceSelect.value);
}

function qcSyncConditionValueInputs(operatorSelect) {
    const row = operatorSelect?.closest('.qc-condition-row');
    if (!row) return;
    const op = operatorSelect.value;
    const value = row.querySelector('.qc-cond-value');
    const value2 = row.querySelector('.qc-cond-value2');
    const noValue = ['empty', 'not_empty'].includes(op);
    if (value) value.style.display = noValue ? 'none' : '';
    if (value2) value2.style.display = op === 'between' ? '' : 'none';
}

function qcRenderPoolOptions() {
    const activeSelect = document.getElementById('qcActivePoolSelect');
    const taskPoolSelect = document.getElementById('qcTaskPoolFilter');
    const options = qcPools.map(pool => `<option value="${escapeHtml(pool.id)}">${escapeHtml(pool.name)}</option>`).join('');
    if (activeSelect) {
        activeSelect.innerHTML = qcPools.length ? options : '<option value="">暂无任务池</option>';
        activeSelect.value = qcActivePoolId ? String(qcActivePoolId) : '';
    }
    if (taskPoolSelect) {
        const current = taskPoolSelect.value;
        taskPoolSelect.innerHTML = `<option value="">全部任务池</option>${options}`;
        taskPoolSelect.value = current;
    }
    qcSetText('qcMetricPools', qcPools.length);
    qcRenderPoolCards();
}

function qcRenderPoolCards() {
    const host = document.getElementById('qcPoolCards');
    if (!host) return;
    const kw = String(document.getElementById('qcPoolSearch')?.value || '').trim().toLowerCase();
    const pools = qcPools.filter(pool => {
        if (!kw) return true;
        return [pool.name, pool.rule_summary, ...(pool.source_labels || [])].join(' ').toLowerCase().includes(kw);
    });
    if (!pools.length) {
        host.innerHTML = '<div class="qc-empty-panel">暂无任务池</div>';
        return;
    }
    host.innerHTML = pools.map(pool => `
        <article class="qc-pool-card ${String(pool.id) === String(qcActivePoolId) ? 'is-active' : ''}">
            <div class="qc-pool-card-head">
                <div>
                    <h3>${escapeHtml(pool.name || '-')}</h3>
                    <span class="qc-pill ${pool.status === 'active' ? 'qc-pill-completed' : 'qc-pill-ignored'}">${pool.status === 'active' ? '启用中' : '已停用'}</span>
                </div>
                <button type="button" class="danger-btn qc-icon-btn" onclick="qcDeletePool(${Number(pool.id)})" title="删除任务池"><i class="fas fa-trash"></i></button>
            </div>
            <div class="qc-source-list">${(pool.source_labels || []).map(s => `<span class="qc-source-pill">${escapeHtml(s)}</span>`).join('')}</div>
            <div class="qc-rule-summary">${escapeHtml(pool.rule_summary || '未设置筛选条件')}</div>
            <div class="qc-pool-stats">
                <span>原始数据 <b>${Number(pool.raw_count || 0)}</b></span>
                <span>已聚合 <b>${Number(pool.aggregated_count || pool.task_count || 0)}</b></span>
                <span>待处理 <b>${Number(pool.pending_count || 0)}</b></span>
                <span>处理中 <b>${Number(pool.processing_count || 0)}</b></span>
                <span>已完成 <b>${Number(pool.completed_count || 0)}</b></span>
            </div>
            <div class="qc-pool-card-actions">
                <button type="button" class="action-btn" onclick="qcViewPoolTasks(${Number(pool.id)})"><i class="fas fa-eye"></i> 查看任务</button>
                <button type="button" class="action-btn" onclick="qcOpenPoolWizard(${Number(pool.id)})"><i class="fas fa-edit"></i> 编辑规则</button>
                <button type="button" class="action-btn" onclick="qcScanPool(${Number(pool.id)})"><i class="fas fa-search"></i> 重新扫描</button>
                <button type="button" class="primary-btn" onclick="qcActivatePoolForAggregation(${Number(pool.id)})">继续聚合</button>
            </div>
        </article>
    `).join('');
}

function qcNewPool() {
    qcOpenPoolWizard();
}

async function qcLoadPools() {
    const res = await api('/quality/pools');
    if (!res?.success) throw new Error(res?.message || '任务池加载失败');
    qcPools = Array.isArray(res.pools) ? res.pools : [];
    if (!qcActivePoolId && qcPools.length) qcActivePoolId = qcPools[0].id;
    if (qcActivePoolId && !qcPools.some(p => String(p.id) === String(qcActivePoolId))) {
        qcActivePoolId = qcPools.length ? qcPools[0].id : null;
    }
    qcRenderPoolOptions();
    qcApplyPoolToForm(qcGetActivePool());
}

async function qcLoadAll() {
    try {
        await qcLoadPools();
        await Promise.all([qcLoadRawIssues(1), qcLoadTasks(1)]);
        qcLoadedOnce = true;
    } catch (e) {
        showToast('管控中心加载失败: ' + (e?.message || String(e)), 'error');
    }
}

function qcSelectPool(value) {
    qcActivePoolId = value ? Number(value) : null;
    qcSelectedRaw.clear();
    qcApplyPoolToForm(qcGetActivePool());
    qcLoadRawIssues(1);
}

function qcSwitchPane(pane) {
    qcActivePane = pane || 'tasks';
    document.querySelectorAll('.qc-inner-tab').forEach(btn => {
        btn.classList.toggle('is-active', btn.dataset.qcPane === qcActivePane);
    });
    document.querySelectorAll('#controlCenterView .qc-pane').forEach(el => {
        const active = el.id === `qcPane${qcActivePane.charAt(0).toUpperCase()}${qcActivePane.slice(1)}`;
        el.classList.toggle('is-active', active);
        el.classList.toggle('d-none', !active);
    });
    if (qcActivePane === 'pools') {
        qcRenderPoolCards();
        const detail = document.getElementById('qcPoolDetailPanel');
        if (detail && !detail.classList.contains('d-none')) qcLoadRawIssues(qcRawPage);
    } else if (qcActivePane === 'tasks') {
        qcLoadTasks(qcTaskPage);
    }
}

function qcOpenPoolWizard(poolId = null) {
    qcWizardEditingPoolId = poolId;
    qcWizardStep = 1;
    qcResetWizardAggregationState();
    const pool = poolId ? qcPools.find(p => String(p.id) === String(poolId)) : null;
    const modal = document.getElementById('qcPoolWizardModal');
    const title = document.getElementById('qcWizardTitle');
    if (title) title.textContent = pool ? '编辑任务池' : '新建任务池';
    const manualOnly = document.getElementById('qcWizardManualOnly');
    if (manualOnly) manualOnly.checked = false;
    qcApplyPoolToForm(pool);
    if (!pool) {
        document.querySelectorAll('#qcPoolWizardModal .qc-source-check').forEach(cb => {
            cb.checked = cb.value === 'governance';
        });
        qcRenderConditionRows([]);
    }
    qcSyncWizardStep();
    if (modal) modal.style.display = 'block';
}

function qcClosePoolWizard() {
    const modal = document.getElementById('qcPoolWizardModal');
    if (modal) modal.style.display = 'none';
    qcWizardEditingPoolId = null;
}

function qcShowPoolDetail(poolId) {
    qcActivePoolId = poolId ? Number(poolId) : qcActivePoolId;
    const select = document.getElementById('qcActivePoolSelect');
    if (select && qcActivePoolId) select.value = String(qcActivePoolId);
    const detail = document.getElementById('qcPoolDetailPanel');
    if (detail) detail.classList.remove('d-none');
    qcSwitchPane('pools');
}

function qcHidePoolDetail() {
    const detail = document.getElementById('qcPoolDetailPanel');
    if (detail) detail.classList.add('d-none');
}

function qcSyncWizardStep() {
    document.querySelectorAll('#qcPoolWizardModal .qc-wizard-step').forEach(el => {
        const active = Number(el.dataset.step) === qcWizardStep;
        el.classList.toggle('d-none', !active);
    });
    document.querySelectorAll('#qcPoolWizardModal .qc-wizard-step-pill').forEach(el => {
        const step = Number(el.dataset.step);
        el.classList.toggle('is-active', step === qcWizardStep);
        el.classList.toggle('is-done', step < qcWizardStep);
    });
    const prev = document.getElementById('qcWizardPrevBtn');
    const next = document.getElementById('qcWizardNextBtn');
    if (prev) prev.disabled = qcWizardStep <= 1;
    if (next) {
        if (qcWizardStep < 4) {
            next.textContent = '下一步';
        } else if (!qcWizardScanResult) {
            next.textContent = '保存并扫描';
        } else if (qcWizardHasNoPendingAggregation()) {
            next.textContent = '完成';
        } else if (document.getElementById('qcWizardManualOnly')?.checked) {
            next.textContent = '完成';
        } else {
            next.textContent = '聚合生成任务';
        }
    }
}

function qcWizardPrev() {
    if (qcWizardStep === 4) {
        qcWizardScanResult = null;
        qcRenderWizardPreview(null, '待扫描');
    }
    qcWizardStep = Math.max(1, qcWizardStep - 1);
    qcSyncWizardStep();
}

async function qcWizardNext() {
    if (qcWizardStep < 4) {
        if (qcWizardStep === 1) {
            const name = String(document.getElementById('qcPoolName')?.value || '').trim();
            if (!name) {
                showToast('请填写任务池名称', 'warning');
                return;
            }
            if (!qcGetSelectedSources().length) {
                showToast('至少选择一个数据来源', 'warning');
                return;
            }
            qcNormalizeConditionRowsForSources();
        }
        qcWizardStep += 1;
        qcSyncWizardStep();
        return;
    }
    if (!qcWizardScanResult) {
        const saveResult = await qcSavePool({
            fromWizard: true,
            closeWizard: false,
            scanAfterSave: true,
            quietSuccess: true
        });
        if (!saveResult?.success || !saveResult.scanOk) return;
        qcWizardSavedPoolId = saveResult.pool?.id || qcActivePoolId;
        qcWizardScanResult = saveResult.scanResult || { raw_summary: saveResult.pool?.raw_summary || {} };
        const removedText = Number(qcWizardScanResult.removed_raw_count || 0) > 0 ? `，清理 ${qcWizardScanResult.removed_raw_count} 条旧命中` : '';
        const noPendingText = qcWizardHasNoPendingAggregation() ? '，暂无新的待聚合项' : '';
        qcRenderWizardPreview(qcWizardScanResult, `扫描完成：命中 ${qcWizardScanResult.matched_count || 0} 条${removedText}${noPendingText}`);
        qcSyncWizardStep();
        return;
    }
    if (qcWizardHasNoPendingAggregation()) {
        qcClosePoolWizard();
        qcSwitchPane('pools');
        await Promise.all([qcLoadPools(), qcLoadTasks(1), qcLoadRawIssues(1)]);
        showToast('命中项已全部聚合，无需重复生成任务', 'info');
        return;
    }
    if (document.getElementById('qcWizardManualOnly')?.checked) {
        qcClosePoolWizard();
        qcSwitchPane('pools');
        qcShowPoolDetail(qcWizardSavedPoolId || qcActivePoolId);
        showToast('原始问题已保存，可稍后人工聚合', 'success');
        return;
    }
    await qcAggregateAllRawForActivePool({
        closeWizard: true,
        priority: document.getElementById('qcWizardDefaultPriority')?.value || 'p2'
    });
}

async function qcSavePool(options = {}) {
    const name = String(document.getElementById('qcPoolName')?.value || '').trim();
    if (!name) {
        showToast('请填写任务池名称', 'warning');
        return;
    }
    const payload = {
        name,
        sources: qcGetSelectedSources(),
        rule_config: qcGetRulePayload(),
        field_mapping: qcBuildFieldMappingPayload()
    };
    try {
        const editingId = options.fromWizard ? (qcWizardEditingPoolId || qcWizardSavedPoolId) : (qcWizardEditingPoolId || qcActivePoolId);
        const path = editingId ? `/quality/pools/${editingId}` : '/quality/pools';
        const method = editingId ? 'PATCH' : 'POST';
        const res = await api(path, method, payload);
        if (!res?.success) throw new Error(res?.message || '保存失败');
        qcActivePoolId = res.pool?.id || qcActivePoolId;
        if (options.fromWizard) qcWizardSavedPoolId = qcActivePoolId;
        await qcLoadPools();
        const shouldScan = !!options.scanAfterSave;
        let scanOk = true;
        let scanResult = null;
        if (shouldScan && qcActivePoolId) {
            scanResult = await qcScanActivePool({ silent: true, returnResult: true });
            scanOk = !!scanResult;
        }
        if (options.closeWizard) {
            const defaultPriority = document.getElementById('qcWizardDefaultPriority')?.value || 'p2';
            const aggregatePriority = document.getElementById('qcAggregatePriority');
            if (aggregatePriority) aggregatePriority.value = defaultPriority;
            qcClosePoolWizard();
            qcSwitchPane('pools');
            qcShowPoolDetail(qcActivePoolId);
        }
        if (!options.quietSuccess) {
            showToast(shouldScan ? (scanOk ? '任务池已保存并扫描完成' : '任务池已保存，扫描未完成') : '任务池规则已保存', scanOk ? 'success' : 'warning');
        }
        return { success: true, pool: res.pool, scanOk, scanResult };
    } catch (e) {
        showToast('保存任务池失败: ' + (e?.message || String(e)), 'error');
        return { success: false };
    }
}

function qcViewPoolTasks(poolId) {
    const filter = document.getElementById('qcTaskPoolFilter');
    if (filter) filter.value = String(poolId);
    qcSwitchPane('tasks');
    qcLoadTasks(1);
}

function qcActivatePoolForAggregation(poolId) {
    qcShowPoolDetail(poolId);
}

async function qcScanPool(poolId) {
    qcActivePoolId = poolId;
    const select = document.getElementById('qcActivePoolSelect');
    if (select) select.value = String(poolId);
    qcShowPoolDetail(poolId);
    return qcScanActivePool();
}

async function qcDeletePool(poolId) {
    qcActivePoolId = poolId;
    await qcDeleteActivePool();
}

async function qcDeleteActivePool() {
    if (!qcActivePoolId) {
        showToast('请先选择任务池', 'warning');
        return;
    }
    const pool = qcGetActivePool();
    if (!confirm(`确认删除任务池“${pool?.name || qcActivePoolId}”及其生成的任务吗？`)) return;
    try {
        const res = await api(`/quality/pools/${qcActivePoolId}`, 'DELETE');
        if (!res?.success) throw new Error(res?.message || '删除失败');
        qcActivePoolId = null;
        qcSelectedRaw.clear();
        qcSelectedTasks.clear();
        await qcLoadAll();
        showToast('任务池已删除', 'success');
    } catch (e) {
        showToast('删除任务池失败: ' + (e?.message || String(e)), 'error');
    }
}

async function qcScanActivePool(options = {}) {
    if (!qcActivePoolId) {
        showToast('请先选择任务池', 'warning');
        return false;
    }
    try {
        const pool = qcGetActivePool();
        const scanPayload = {};
        if ((pool?.sources || []).includes('governance')) {
            const range = qcGetGovernanceRuleRange();
            if (range.startMonth) scanPayload.governance_month_start = range.startMonth;
            if (range.endMonth) scanPayload.governance_month_end = range.endMonth;
        }
        const res = await api(`/quality/pools/${qcActivePoolId}/scan`, 'POST', scanPayload);
        if (!res?.success) throw new Error(res?.message || '扫描失败');
        await qcLoadPools();
        await qcLoadRawIssues(1);
        const removedText = Number(res.removed_raw_count || 0) > 0 ? `，清理 ${res.removed_raw_count} 条旧命中` : '';
        if (!options.silent) showToast(`扫描完成：命中 ${res.matched_count || 0} 条${removedText}`, 'success');
        return options.returnResult ? res : true;
    } catch (e) {
        showToast('扫描失败: ' + (e?.message || String(e)), 'error');
        return options.returnResult ? null : false;
    }
}

async function qcImportExternalFile() {
    const input = document.getElementById('qcImportFile');
    if (!input?.files?.length) {
        showToast('请选择外部检测文件', 'warning');
        return;
    }
    const formData = new FormData();
    formData.append('file', input.files[0]);
    if (qcActivePoolId) formData.append('target_pool_id', qcActivePoolId);
    try {
        const resp = await fetch(`${API_BASE}/quality/import`, {
            method: 'POST',
            credentials: 'same-origin',
            body: formData
        });
        const res = await resp.json();
        if (!res?.success) throw new Error(res?.message || '导入失败');
        qcActivePoolId = res.pool?.id || qcActivePoolId;
        input.value = '';
        await qcLoadPools();
        await Promise.all([qcLoadRawIssues(1), qcLoadTasks(1)]);
        const job = res.job || {};
        showToast(`导入完成：成功 ${job.success_count || 0} 条，失败 ${job.failed_count || 0} 条`, job.failed_count ? 'warning' : 'success');
        if (job.failed_count && Array.isArray(job.failed_detail)) {
            console.warn('[Quality Import Failed Detail]', job.failed_detail);
        }
    } catch (e) {
        showToast('导入失败: ' + (e?.message || String(e)), 'error');
    }
}

async function qcLoadRawIssues(page = qcRawPage) {
    qcRawPage = Math.max(1, Number(page) || 1);
    const tbody = document.getElementById('qcRawTableBody');
    if (!qcActivePoolId) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="empty-message">请先创建或选择任务池</td></tr>';
        qcSetText('qcRawPageInfo', '共 0 条');
        return;
    }
    const params = new URLSearchParams({
        page: String(qcRawPage),
        pageSize: String(qcRawPageSize)
    });
    const keyword = String(document.getElementById('qcRawKeyword')?.value || '').trim();
    const source = String(document.getElementById('qcRawSource')?.value || '').trim();
    const onlyUnlinked = !!document.getElementById('qcOnlyUnlinked')?.checked;
    if (keyword) params.set('keyword', keyword);
    if (source) params.set('source', source);
    if (onlyUnlinked) params.set('only_unlinked', '1');
    try {
        const res = await api(`/quality/pools/${qcActivePoolId}/raw_issues?${params.toString()}`);
        if (!res?.success) throw new Error(res?.message || '原始问题加载失败');
        qcRawTotal = Number(res.total || 0);
        qcRenderRawIssues(res.raw_issues || []);
    } catch (e) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="error-message">加载失败: ${escapeHtml(e.message)}</td></tr>`;
    }
}

function qcRenderRawIssues(rows) {
    const tbody = document.getElementById('qcRawTableBody');
    if (!tbody) return;
    if (!Array.isArray(rows) || !rows.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-message">暂无原始问题</td></tr>';
    } else {
        tbody.innerHTML = rows.map(item => {
            const id = String(item.id);
            const checked = qcSelectedRaw.has(id) ? 'checked' : '';
            const linked = item.linked_task_id ? `已聚合 #${item.linked_task_id}` : (item.ignored ? '已忽略' : '未聚合');
            return `
                <tr>
                    <td class="qc-col-check"><input type="checkbox" ${checked} onchange="qcToggleRaw('${escapeHtml(id)}', this.checked)"></td>
                    <td><span class="mod-id-text">${escapeHtml(item.wiki_id || '')}</span></td>
                    <td><span class="qc-source-pill">${escapeHtml(qcSourceLabel(item.source_type))}</span></td>
                    <td><div class="qc-text-cell" title="${escapeHtml(item.issue_text || '')}">${escapeHtml(item.issue_text || '-')}</div></td>
                    <td><span class="qc-pill">${escapeHtml(linked)}</span></td>
                </tr>
            `;
        }).join('');
    }
    const totalPages = Math.max(1, Math.ceil(qcRawTotal / qcRawPageSize));
    qcSetText('qcRawPageInfo', `第 ${Math.min(qcRawPage, totalPages)}/${totalPages} 页 ｜ 共 ${qcRawTotal} 条`);
    const all = document.getElementById('qcSelectAllRaw');
    if (all) all.checked = rows.length > 0 && rows.every(r => qcSelectedRaw.has(String(r.id)));
}

function qcToggleRaw(id, checked) {
    if (checked) qcSelectedRaw.add(String(id));
    else qcSelectedRaw.delete(String(id));
}

function qcToggleAllRaw(checked) {
    document.querySelectorAll('#qcRawTableBody input[type="checkbox"]').forEach(cb => {
        cb.checked = !!checked;
        const match = cb.getAttribute('onchange')?.match(/qcToggleRaw\('([^']+)'/);
        if (match) qcToggleRaw(match[1], !!checked);
    });
}

function qcChangeRawPage(delta) {
    const totalPages = Math.max(1, Math.ceil(qcRawTotal / qcRawPageSize));
    const next = Math.min(totalPages, Math.max(1, qcRawPage + Number(delta || 0)));
    if (next !== qcRawPage) qcLoadRawIssues(next);
}

const qcDebouncedLoadRawImpl = debounce(() => qcLoadRawIssues(1), 300);
function qcDebouncedLoadRaw() {
    qcDebouncedLoadRawImpl();
}

async function qcAggregateAllRawForActivePool(options = {}) {
    if (!qcActivePoolId) {
        showToast('请先选择任务池', 'warning');
        return false;
    }
    const priority = options.priority || document.getElementById('qcAggregatePriority')?.value || 'p2';
    try {
        const res = await api(`/quality/pools/${qcActivePoolId}/aggregate_all`, 'POST', {
            priority,
            only_unlinked: true
        });
        if (!res?.success) throw new Error(res?.message || '聚合失败');
        qcSelectedRaw.clear();
        await Promise.all([qcLoadPools(), qcLoadTasks(1), qcLoadRawIssues(1)]);
        if (options.closeWizard) {
            qcClosePoolWizard();
            const filter = document.getElementById('qcTaskPoolFilter');
            if (filter) filter.value = String(qcActivePoolId);
            qcSwitchPane('tasks');
        }
        if (Number(res.linked_count || 0) <= 0 && res.message) {
            showToast(res.message, 'info');
        } else {
            showToast(`聚合完成：${res.wiki_count || 0} 个 WikiID，关联 ${res.linked_count || 0} 条原始问题`, 'success');
        }
        return true;
    } catch (e) {
        showToast('聚合失败: ' + (e?.message || String(e)), 'error');
        return false;
    }
}

async function qcAggregateSelectedRaw() {
    if (!qcActivePoolId) {
        showToast('请先选择任务池', 'warning');
        return;
    }
    const ids = Array.from(qcSelectedRaw);
    if (!ids.length) {
        showToast('请选择原始问题', 'warning');
        return;
    }
    const priority = document.getElementById('qcAggregatePriority')?.value || 'p2';
    try {
        const res = await api(`/quality/pools/${qcActivePoolId}/aggregate`, 'POST', {
            raw_issue_ids: ids,
            priority
        });
        if (!res?.success) throw new Error(res?.message || '聚合失败');
        qcSelectedRaw.clear();
        await Promise.all([qcLoadRawIssues(qcRawPage), qcLoadTasks(1), qcLoadPools()]);
        showToast(`聚合完成：关联 ${res.linked_count || 0} 条`, 'success');
    } catch (e) {
        showToast('聚合失败: ' + (e?.message || String(e)), 'error');
    }
}

async function qcLoadTasks(page = qcTaskPage) {
    qcTaskPage = Math.max(1, Number(page) || 1);
    const params = new URLSearchParams({
        page: String(qcTaskPage),
        pageSize: String(qcTaskPageSize)
    });
    ['Status', 'Priority', 'Source'].forEach(name => {
        const el = document.getElementById(`qcTask${name}`);
        const key = name.toLowerCase();
        if (el?.value) params.set(key, el.value);
    });
    const poolFilter = document.getElementById('qcTaskPoolFilter')?.value;
    if (poolFilter) params.set('pool_id', poolFilter);
    const keyword = String(document.getElementById('qcTaskKeyword')?.value || '').trim();
    if (keyword) params.set('keyword', keyword);
    const tbody = document.getElementById('qcTaskTableBody');
    try {
        const res = await api(`/quality/tasks?${params.toString()}`);
        if (!res?.success) throw new Error(res?.message || '任务加载失败');
        qcTaskTotal = Number(res.total || 0);
        qcLastTasks = Array.isArray(res.tasks) ? res.tasks : [];
        qcRenderTasks(qcLastTasks);
        qcUpdateMetrics(res.summary || {});
    } catch (e) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="error-message">加载失败: ${escapeHtml(e.message)}</td></tr>`;
    }
}

function qcUpdateMetrics(summary) {
    qcSetText('qcMetricPending', summary.pending || 0);
    qcSetText('qcMetricProcessing', summary.processing || 0);
    qcSetText('qcMetricCompleted', summary.completed || 0);
}

function qcCleanSuggestionText(value) {
    const parts = String(value || '')
        .split(/[；;\n]/)
        .map(item => item.trim())
        .filter(item => item && !/^[-+]?\d+(?:\.\d+)?%?$/.test(item));
    return Array.from(new Set(parts)).join('；');
}

function qcRenderTasks(tasks) {
    const tbody = document.getElementById('qcTaskTableBody');
    if (!tbody) return;
    if (!Array.isArray(tasks) || !tasks.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-message">暂无任务</td></tr>';
    } else {
        tbody.innerHTML = tasks.map(task => {
            const id = String(task.id);
            const checked = qcSelectedTasks.has(id) ? 'checked' : '';
            const sources = (task.source_tags || []).map(s => `<span class="qc-source-pill">${escapeHtml(s.source_label)}${s.count ? ` ${s.count}` : ''}</span>`).join('');
            const issueText = task.issue_tag_text || `共 ${task.issue_count || 0} 条问题 ｜ ${((task.pool_names || []).join('、') || '未关联任务池')}`;
            const suggestionText = qcCleanSuggestionText(task.suggested_action_text) || '-';
            return `
                <tr>
                    <td class="qc-col-check"><input type="checkbox" ${checked} onchange="qcToggleTask('${escapeHtml(id)}', this.checked)"></td>
                    <td><span class="qc-pill qc-pill-${escapeHtml(task.status || '')}">${escapeHtml(qcStatusLabel(task.status))}</span></td>
                    <td><span class="mod-id-text">${escapeHtml(task.wiki_id || '')}</span></td>
                    <td><div class="qc-text-cell" title="${escapeHtml(task.question || '')}">${escapeHtml(task.question || '-')}</div></td>
                    <td><div class="qc-text-cell" title="${escapeHtml(suggestionText)}">${escapeHtml(suggestionText)}</div></td>
                    <td><div class="qc-text-cell" title="${escapeHtml(issueText)}">${escapeHtml(issueText)}</div></td>
                    <td>
                        <div class="qc-source-list">${sources || '-'}</div>
                    </td>
                    <td>
                        <div class="qc-action-cell">
                            <button type="button" class="primary-btn" onclick="qcOpenTaskEditor(${Number(task.id)})" title="编辑"><i class="fas fa-edit"></i></button>
                            <button type="button" class="action-btn" onclick="qcPatchTask(${Number(task.id)}, { status: 'completed' })" title="完成"><i class="fas fa-check"></i></button>
                            <button type="button" class="action-btn" onclick="qcPatchTask(${Number(task.id)}, { status: 'ignored' })" title="忽略"><i class="fas fa-ban"></i></button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    }
    const totalPages = Math.max(1, Math.ceil(qcTaskTotal / qcTaskPageSize));
    qcSetText('qcTaskPageInfo', `第 ${Math.min(qcTaskPage, totalPages)}/${totalPages} 页 ｜ 共 ${qcTaskTotal} 条`);
    const pageSizeEl = document.getElementById('qcTaskPageSize');
    if (pageSizeEl && pageSizeEl.value !== String(qcTaskPageSize)) pageSizeEl.value = String(qcTaskPageSize);
    const all = document.getElementById('qcSelectAllTasks');
    if (all) all.checked = tasks.length > 0 && tasks.every(t => qcSelectedTasks.has(String(t.id)));
}

function qcToggleTask(id, checked) {
    if (checked) qcSelectedTasks.add(String(id));
    else qcSelectedTasks.delete(String(id));
}

function qcToggleAllTasks(checked) {
    (qcLastTasks || []).forEach(task => qcToggleTask(String(task.id), !!checked));
    document.querySelectorAll('#qcTaskTableBody input[type="checkbox"]').forEach(cb => {
        cb.checked = !!checked;
    });
}

function qcChangeTaskPage(delta) {
    const totalPages = Math.max(1, Math.ceil(qcTaskTotal / qcTaskPageSize));
    const next = Math.min(totalPages, Math.max(1, qcTaskPage + Number(delta || 0)));
    if (next !== qcTaskPage) qcLoadTasks(next);
}

function qcChangeTaskPageSize(value) {
    const next = Number(value);
    qcTaskPageSize = [10, 20, 50].includes(next) ? next : 20;
    qcLoadTasks(1);
}

const qcDebouncedLoadTasksImpl = debounce(() => qcLoadTasks(1), 300);
function qcDebouncedLoadTasks() {
    qcDebouncedLoadTasksImpl();
}

async function qcPatchTask(taskId, payload) {
    try {
        const res = await api(`/quality/tasks/${taskId}`, 'PATCH', payload || {});
        if (!res?.success) throw new Error(res?.message || '更新失败');
        await qcLoadTasks(qcTaskPage);
    } catch (e) {
        showToast('更新任务失败: ' + (e?.message || String(e)), 'error');
    }
}

async function qcBatchTask(action) {
    const ids = Array.from(qcSelectedTasks);
    if (!ids.length) {
        showToast('请选择任务', 'warning');
        return;
    }
    const label = action === 'complete' ? '提交完成' : action === 'ignore' ? '忽略' : '更新';
    if (!confirm(`确认${label}当前选中的 ${ids.length} 条任务吗？`)) return;
    try {
        const res = await api('/quality/tasks/batch', 'POST', { task_ids: ids, action });
        if (!res?.success) throw new Error(res?.message || '批量操作失败');
        qcSelectedTasks.clear();
        await qcLoadTasks(qcTaskPage);
        showToast(`已处理 ${res.changed || 0} 条任务`, 'success');
    } catch (e) {
        showToast('批量操作失败: ' + (e?.message || String(e)), 'error');
    }
}

async function qcOpenTaskEditor(taskId) {
    try {
        const res = await api(`/quality/tasks/${taskId}`);
        if (!res?.success) throw new Error(res?.message || '任务详情加载失败');
        const task = res.task || {};
        const item = res.kb_item;
        if (!item) {
            showToast('知识库主库未找到该 WikiID，无法编辑', 'error');
            return;
        }
        await openKBEditModal(task.wiki_id, {
            item,
            qualityTask: {
                task_id: task.id,
                wiki_id: task.wiki_id,
                base_update_time: item.update_time || ''
            }
        });
    } catch (e) {
        showToast('打开任务失败: ' + (e?.message || String(e)), 'error');
    }
}

async function qcExportTasks() {
    const ids = Array.from(qcSelectedTasks);
    try {
        const resp = await fetch(`${API_BASE}/quality/tasks/export`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ task_ids: ids })
        });
        if (!resp.ok) {
            let msg = '导出失败';
            try {
                const err = await resp.json();
                msg = err.message || msg;
            } catch (_) {}
            throw new Error(msg);
        }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `管控中心任务_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (e) {
        showToast('导出失败: ' + (e?.message || String(e)), 'error');
    }
}

// ==========================================
// Modifications View Logic
// ==========================================
let modCurrentPage = 1;
let modPageSize = 20;
let modTotal = 0;
let currentModifications = [];
let selectedModifications = new Set();
let modDupOnly = false;
let modSortBy = '';
let modSortDir = 'asc';
let modAutoRefreshTimer = null;
let modAutoRefreshInFlight = false;
let modAutoRefreshEnabled = false;
let renderedModifications = [];
let tdCellExpanded = new Set();

function _hasOwn(obj, key) {
    return !!obj && Object.prototype.hasOwnProperty.call(obj, key);
}

function _escapeAttr(value) {
    return String(value ?? '').replace(/"/g, '&quot;');
}

function _escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function getModDuplicateIdSet(rows = []) {
    const counts = {};
    rows.forEach((item) => {
        const id = String(item?.question_wiki_id || item?.kb_id || '').trim();
        if (!id) return;
        counts[id] = (counts[id] || 0) + 1;
    });
    return new Set(Object.keys(counts).filter((id) => counts[id] >= 2));
}

function getRenderedModificationsRows() {
    let rows = Array.isArray(currentModifications) ? currentModifications.slice() : [];
    const duplicateIds = getModDuplicateIdSet(rows);
    if (modDupOnly && rows.length > 0) {
        rows = rows.filter((item) => {
            const id = String(item?.question_wiki_id || item?.kb_id || '').trim();
            return id && duplicateIds.has(id);
        });
        rows.sort((a, b) => {
            const idA = String(a?.question_wiki_id || a?.kb_id || '').trim();
            const idB = String(b?.question_wiki_id || b?.kb_id || '').trim();
            if (idA !== idB) return idA.localeCompare(idB);
            const timeA = new Date(a?.modification_time || a?.modify_time || 0).getTime();
            const timeB = new Date(b?.modification_time || b?.modify_time || 0).getTime();
            return timeB - timeA;
        });
    }
    return { rows, duplicateIds };
}

function updateModSummary() {
    const { rows, duplicateIds } = getRenderedModificationsRows();
    const duplicateRowCount = rows.filter((item) => {
        const id = String(item?.question_wiki_id || item?.kb_id || '').trim();
        return id && duplicateIds.has(id);
    }).length;
    const totalPages = modDupOnly ? 1 : Math.max(1, Math.ceil((modTotal || 0) / Math.max(modPageSize || 1, 1)));
    const selectedCount = selectedModifications.size;
    const activeFilters = [];
    const sortLabelMap = {
        question: '问题',
        kb_id: '问题编号',
        modification_time: '修改时间'
    };
    const kbId = document.getElementById('modSearchId')?.value.trim();
    const question = document.getElementById('modSearchQuestion')?.value.trim();
    const product = document.getElementById('modSearchProduct')?.value.trim();
    const answer = document.getElementById('modSearchAnswer')?.value.trim();
    const source = document.getElementById('modSourceSelect')?.value.trim();
    const operation = document.getElementById('modOpSelect')?.value.trim();
    const startTime = document.getElementById('modStartTime')?.value.trim();
    const endTime = document.getElementById('modEndTime')?.value.trim();

    if (kbId) activeFilters.push(`编号=${kbId}`);
    if (question) activeFilters.push('问题检索');
    if (product) activeFilters.push(`产品=${product}`);
    if (answer) activeFilters.push('答案检索');
    if (source) activeFilters.push(`来源=${source}`);
    if (operation) activeFilters.push(`操作=${operation}`);
    if (startTime || endTime) activeFilters.push('时间范围');
    if (modDupOnly) activeFilters.push('仅重复项');

    const summaryTotalEl = document.getElementById('modSummaryTotal');
    const summaryDupEl = document.getElementById('modSummaryDuplicates');
    const summarySelectedEl = document.getElementById('modSummarySelected');
    const summaryRefreshEl = document.getElementById('modSummaryRefresh');
    const activeFiltersEl = document.getElementById('modActiveFilters');
    const sortSummaryEl = document.getElementById('modSortSummary');
    const resultSummaryEl = document.getElementById('modResultSummary');
    const selectionSummaryEl = document.getElementById('modSelectionSummary');
    const pageJumpInput = document.getElementById('modPageJumpInput');

    if (summaryTotalEl) summaryTotalEl.textContent = `${modTotal || 0} 条`;
    if (summaryDupEl) summaryDupEl.textContent = `${duplicateRowCount} 条`;
    if (summarySelectedEl) summarySelectedEl.textContent = `${selectedCount} 条`;
    if (summaryRefreshEl) summaryRefreshEl.textContent = modAutoRefreshEnabled ? '自动刷新中' : '手动刷新';
    if (activeFiltersEl) activeFiltersEl.textContent = activeFilters.length ? `当前筛选：${activeFilters.join(' / ')}` : '当前筛选：未设置';
    if (sortSummaryEl) {
        sortSummaryEl.textContent = modSortBy
            ? `排序：${sortLabelMap[modSortBy] || modSortBy} · ${modSortDir === 'desc' ? '倒序' : '正序'}`
            : '排序：默认顺序';
    }
    if (resultSummaryEl) {
        resultSummaryEl.textContent = modDupOnly
            ? `结果：重复记录 ${rows.length} 条`
            : `结果：第 ${Math.min(modCurrentPage || 1, totalPages)} / ${totalPages} 页，共 ${modTotal || 0} 条`;
    }
    if (selectionSummaryEl) selectionSummaryEl.textContent = `已选 ${selectedCount} 条`;
    if (pageJumpInput) {
        pageJumpInput.max = String(totalPages);
        pageJumpInput.placeholder = modDupOnly ? '1' : `${totalPages}`;
    }
}

function kbRenderCompactText(value, placeholder = '-') {
    const text = String((value === null || value === undefined || value === '') ? placeholder : value);
    return `<span class="kb-cell-ellipsis">${_escapeHtml(text)}</span>`;
}

function kbGetPlainCellText(td) {
    if (!td) return '';
    const explicit = td.dataset ? td.dataset.fullText : '';
    if (explicit) return explicit;
    return String(td.innerText || td.textContent || '').trim();
}

function kbPrepareCompactCell(td, col, text, options = {}) {
    if (!td || !col || col.key === 'checkbox' || col.key === 'action') return;
    const key = String(col.key || '');
    const isUrlCol = key === 'image_urls' || key === 'video_urls' || key === 'file_urls' || key === 'link_url';
    const isIdCol = key === 'id';
    const value = String((text === null || text === undefined) ? '' : text).trim();
    td.classList.add('kb-compact-cell');
    td.dataset.colKey = key;
    td.dataset.colTitle = col.title || '';
    td.dataset.fullText = value;
    td.dataset.modalAllowed = (!isIdCol && !isUrlCol && options.modalAllowed !== false) ? '1' : '0';
}

function kbRefreshCompactOverflow(root = document) {
    window.requestAnimationFrame(() => {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('#kbTable td.kb-compact-cell').forEach(td => {
            const target = td.querySelector('.kb-cell-ellipsis') || td.querySelector('.kb-url-link') || td.querySelector('.tags-cell') || td;
            const overflow = target.scrollWidth > target.clientWidth + 1 || target.scrollHeight > target.clientHeight + 1;
            td.classList.toggle('is-overflow', overflow);
            const text = kbGetPlainCellText(td);
            if (overflow && text && text !== '-') td.title = text;
            else td.removeAttribute('title');
        });
    });
}

function kbApplyStableTableWidth() {
    const table = document.getElementById('kbTable');
    if (!table) return;
    const visibleColumns = kbColumns.filter(col => col.visible !== false);
    const total = visibleColumns.reduce((sum, col) => {
        const raw = String(col.width || '').trim();
        const n = parseFloat(raw);
        return sum + (Number.isFinite(n) ? n : 120);
    }, 0);
    table.style.width = `${Math.max(960, total)}px`;
    table.style.minWidth = '100%';
}

function kbOpenCellDetail(td) {
    if (!td || !td.dataset || td.dataset.modalAllowed !== '1') return;
    const text = kbGetPlainCellText(td);
    if (!text || text === '-') return;
    const title = td.dataset.colTitle || '单元格内容';
    let modal = document.getElementById('kbCellDetailModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'kbCellDetailModal';
        modal.className = 'kb-cell-detail-modal';
        modal.innerHTML = `
            <div class="kb-cell-detail-card" role="dialog" aria-modal="true">
                <div class="kb-cell-detail-head">
                    <div class="kb-cell-detail-title"></div>
                    <div class="kb-cell-detail-tools">
                        <button type="button" class="kb-cell-detail-copy" onclick="kbCopyCellDetail()" title="复制"><i class="fas fa-copy"></i></button>
                        <button type="button" class="kb-cell-detail-close" onclick="kbCloseCellDetail()" title="关闭">×</button>
                    </div>
                </div>
                <div class="kb-cell-detail-body"></div>
            </div>`;
        modal.addEventListener('click', event => {
            if (event.target === modal) kbCloseCellDetail();
        });
        document.body.appendChild(modal);
    }
    modal.dataset.copyText = text;
    const card = modal.querySelector('.kb-cell-detail-card');
    const body = modal.querySelector('.kb-cell-detail-body');
    const titleEl = modal.querySelector('.kb-cell-detail-title');
    const isLarge = text.length > 160 || /[\n\r]/.test(text);
    if (card) card.classList.toggle('is-large', isLarge);
    if (titleEl) titleEl.textContent = `查看内容 - [${title}]`;
    if (body) body.textContent = text;
    modal.classList.add('is-open');
}

function kbCloseCellDetail() {
    const modal = document.getElementById('kbCellDetailModal');
    if (modal) modal.classList.remove('is-open');
}

function kbCopyCellDetail() {
    const modal = document.getElementById('kbCellDetailModal');
    const text = modal ? (modal.dataset.copyText || '') : '';
    if (!text) return;
    copyToClipboard(text);
    setTimeout(() => showToast('复制成功', 'success', 1800), 40);
}

function kbBindCompactTableInteractions() {
    const table = document.getElementById('kbTable');
    if (!table || table.dataset.compactBound === '1') return;
    table.dataset.compactBound = '1';
    table.addEventListener('dblclick', event => {
        if (event.target.closest('button, a, input, .col-resizer, .resizer')) return;
        const td = event.target.closest('td.kb-compact-cell');
        if (td) kbOpenCellDetail(td);
    });
}

function matrixBindCompactTableInteractions() {
    const table = document.getElementById('matrixTable');
    if (!table || table.dataset.compactBound === '1') return;
    table.dataset.compactBound = '1';
    table.addEventListener('dblclick', event => {
        if (event.target.closest('button, a, input, .col-resizer, .resizer')) return;
        const td = event.target.closest('td.matrix-detail-cell');
        if (td) kbOpenCellDetail(td);
    });
}

function modBindCellDetailInteractions() {
    const table = document.getElementById('modTable');
    if (!table || table.dataset.detailModalBound === '1') return;
    table.dataset.detailModalBound = '1';
    table.addEventListener('dblclick', event => {
        if (event.target.closest('button, a, input, .col-resizer, .resizer')) return;
        const td = event.target.closest('td[data-modal-allowed="1"]');
        if (td) kbOpenCellDetail(td);
    });
}

function matrixRefreshCompactOverflow(root = document) {
    window.requestAnimationFrame(() => {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('#matrixTable td.matrix-detail-cell').forEach(td => {
            const target = td.querySelector('textarea') || td;
            const overflow = target.scrollWidth > target.clientWidth + 1 || target.scrollHeight > target.clientHeight + 1;
            td.classList.toggle('is-overflow', overflow);
            const text = kbGetPlainCellText(td);
            if (overflow && text && text !== '-') {
                td.title = text;
                if (target !== td) target.title = text;
            } else {
                td.removeAttribute('title');
                if (target !== td) target.removeAttribute('title');
            }
        });
    });
}

document.addEventListener('keydown', event => {
    if (event.key === 'Escape') kbCloseCellDetail();
});

window.kbCloseCellDetail = kbCloseCellDetail;
window.kbCopyCellDetail = kbCopyCellDetail;

function tdToggleCellExpandBtn(btn, event) {
    if (event) event.stopPropagation();
    const cell = btn && btn.closest ? btn.closest('.td-cell[data-cell-key]') : null;
    if (!cell) return;
    const key = cell.getAttribute('data-cell-key') || '';
    if (!key) return;
    if (tdCellExpanded.has(key)) {
        tdCellExpanded.delete(key);
        cell.classList.remove('is-expanded');
    } else {
        tdCellExpanded.add(key);
        cell.classList.add('is-expanded');
    }
    if (btn) btn.textContent = tdCellExpanded.has(key) ? '收起' : '展开';
    tdRefreshCellOverflow(cell.closest('table') || document);
}

function tdRefreshCellOverflow(root = document) {
    window.requestAnimationFrame(() => {
        const scope = root && root.querySelectorAll ? root : document;
        const cells = scope.querySelectorAll('.td-cell[data-cell-key]');
        cells.forEach(cell => {
            const key = cell.getAttribute('data-cell-key') || '';
            const ta = cell.querySelector('textarea');
            if (!ta) return;
            _applyCellTitle(ta, ta.value);
            if (tdCellExpanded.has(key)) {
                cell.classList.add('is-overflow');
                ta.style.height = 'auto';
                const h = ta.scrollHeight || 0;
                if (h) ta.style.height = `${Math.min(520, h)}px`;
                return;
            }
            ta.style.height = '';
            const overflow = ta.scrollHeight > ta.clientHeight + 2;
            if (overflow) cell.classList.add('is-overflow');
            else cell.classList.remove('is-overflow');
        });
    });
}

function _applyCellTitle(el, value) {
    if (!el) return;
    const text = value === null || value === undefined ? '' : String(value);
    el.title = text;
}

function tdRenderExpandableText(cellKey, text, options = {}) {
    const key = String(cellKey || '');
    const raw = (text === null || text === undefined) ? '' : String(text);
    const placeholder = (options && options.placeholder !== undefined) ? String(options.placeholder) : '-';
    const readOnly = (options && options.readOnly !== undefined) ? !!options.readOnly : true;
    const textareaClass = (options && options.textareaClass) ? String(options.textareaClass) : '';
    const cellClass = (options && options.cellClass) ? String(options.cellClass) : '';
    const showExpandButton = !(options && options.showExpandButton === false);
    const isExpanded = tdCellExpanded.has(key);
    const value = raw || '';
    return `
        <div class="td-cell ${cellClass} ${isExpanded ? 'is-expanded' : ''}" data-cell-key="${_escapeAttr(key)}">
            <textarea rows="3" style="white-space:pre-wrap;" ${readOnly ? 'readonly' : ''} class="${_escapeAttr(textareaClass)}" placeholder="${_escapeAttr(placeholder)}" title="${_escapeAttr(value)}">${_escapeHtml(value)}</textarea>
            ${showExpandButton ? `<button type="button" class="td-expand-btn" onclick="tdToggleCellExpandBtn(this, event)">${isExpanded ? '收起' : '展开'}</button>` : ''}
        </div>
    `;
}

function getModLatestField(item, field) {
    const after = item?.after;
    const before = item?.before;
    if (_hasOwn(after, field)) return after[field];
    if (_hasOwn(before, field)) return before[field];
    return item?.[field];
}

function normalizeProductsListText(value) {
    if (Array.isArray(value)) {
        const parts = value.map(v => normalizeMatrixProductName(v)).filter(Boolean);
        return parts.join(',');
    }
    const s = String(value ?? '');
    const parts = s
        .split(/[,\n，]+/)
        .map(v => normalizeMatrixProductName(v))
        .filter(Boolean);
    return parts.join(',');
}

function _normalizeModScalar(v) {
    if (v === null || v === undefined) return '';
    const s = String(v).trim();
    if (!s || s === '-' || s.toLowerCase() === 'null') return '';
    return s;
}

function _normalizeModListLike(v, options = {}) {
    const parts = parseSmartListValue(v, { ...options, splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true });
    const out = [];
    const seen = new Set();
    for (const x of parts) {
        const s = String(x ?? '').trim();
        if (!s) continue;
        if (seen.has(s)) continue;
        seen.add(s);
        out.push(s);
    }
    out.sort();
    return out.join('\n');
}

function _normalizeModFieldValue(field, value) {
    const f = String(field || '').trim();
    if (!f) return _normalizeModScalar(value);
    if (f === 'products') return normalizeProductsListText(value);
    if (f === 'image_urls' || f === 'video_urls' || f === 'file_urls') return _normalizeModListLike(value, { isUrlList: true });
    if (f === 'link_url') return _normalizeModListLike(value, { isUrlList: true });
    if (f === 'keyword_list' || f === 'error_list' || f === 'similar_questions') return _normalizeModListLike(value, { isUrlList: false });
    if (f === 'if_bm25') return _normalizeModScalar(value).toLowerCase();
    if (f === 'link_type' || f === 'answer_type' || f === 'question_type') return _normalizeModScalar(value);
    return _normalizeModScalar(value);
}

function isModFieldChanged(item, field) {
    const arr = item?.changed_fields || item?.changedFields || [];
    if (!Array.isArray(arr) || !arr.includes(field)) return false;
    const beforeObj = item?.before || {};
    const afterObj = item?.after || {};

    // products 兼容旧字段 product_name
    if (field === 'products') {
        const bv = _hasOwn(beforeObj, 'products') ? beforeObj.products : (_hasOwn(beforeObj, 'product_name') ? beforeObj.product_name : '');
        const av = _hasOwn(afterObj, 'products') ? afterObj.products : (_hasOwn(afterObj, 'product_name') ? afterObj.product_name : '');
        return normalizeProductsListText(bv) !== normalizeProductsListText(av);
    }

    // 其他字段：后端可能“宣称 changed”，但前端再做一次 before/after 归一化比对，避免误报
    const bv = _hasOwn(beforeObj, field) ? beforeObj[field] : '';
    const av = _hasOwn(afterObj, field) ? afterObj[field] : '';
    return _normalizeModFieldValue(field, bv) !== _normalizeModFieldValue(field, av);
}

function isAnyModFieldChanged(item, fields) {
    if (!Array.isArray(fields) || fields.length === 0) return false;
    return fields.some(f => isModFieldChanged(item, f));
}

function getModLatestUrlsList(item) {
    const opts = { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true };
    const all = [];
    ['image_urls', 'video_urls', 'file_urls'].forEach(k => {
        const v = getModLatestField(item, k);
        all.push(...parseSmartListValue(v, opts));
    });
    all.push(...parseSmartListValue(getModLatestField(item, 'link_url'), opts));
    const out = [];
    const seen = new Set();
    all.forEach(u => {
        const s = String(u || '').trim();
        if (!s) return;
        if (seen.has(s)) return;
        seen.add(s);
        out.push(s);
    });
    return out;
}

function _tokenizeForDiff(text) {
    const s = String(text ?? '');
    return s.match(/(\s+|[^\s]+)/g) || [];
}

function _myersDiff(a, b) {
    const n = a.length;
    const m = b.length;
    const max = n + m;
    const offset = max;
    let v = new Array(2 * max + 1).fill(0);
    const trace = [];

    for (let d = 0; d <= max; d++) {
        trace.push(v.slice());
        for (let k = -d; k <= d; k += 2) {
            const kIdx = k + offset;
            let x;
            if (k === -d || (k !== d && v[kIdx - 1] < v[kIdx + 1])) {
                x = v[kIdx + 1];
            } else {
                x = v[kIdx - 1] + 1;
            }
            let y = x - k;
            while (x < n && y < m && a[x] === b[y]) {
                x++;
                y++;
            }
            v[kIdx] = x;
            if (x >= n && y >= m) {
                trace.push(v.slice());
                return { trace, a, b };
            }
        }
    }
    trace.push(v.slice());
    return { trace, a, b };
}

function _buildDiffOps(aTokens, bTokens) {
    const { trace, a, b } = _myersDiff(aTokens, bTokens);
    const n = a.length;
    const m = b.length;
    const max = n + m;
    const offset = max;
    let x = n;
    let y = m;
    const ops = [];

    for (let d = trace.length - 1; d > 0; d--) {
        const v = trace[d - 1];
        const k = x - y;
        const kIdx = k + offset;
        let prevK;
        if (k === - (d - 1) || (k !== (d - 1) && v[kIdx - 1] < v[kIdx + 1])) {
            prevK = k + 1;
        } else {
            prevK = k - 1;
        }
        const prevX = v[prevK + offset];
        const prevY = prevX - prevK;

        while (x > prevX && y > prevY) {
            ops.push({ type: 'equal', value: a[x - 1] });
            x--;
            y--;
        }

        if (d === 0) break;

        if (x === prevX) {
            ops.push({ type: 'insert', value: b[y - 1] });
            y--;
        } else {
            ops.push({ type: 'delete', value: a[x - 1] });
            x--;
        }
    }

    while (x > 0 && y > 0) {
        ops.push({ type: 'equal', value: a[x - 1] });
        x--;
        y--;
    }
    while (x > 0) {
        ops.push({ type: 'delete', value: a[x - 1] });
        x--;
    }
    while (y > 0) {
        ops.push({ type: 'insert', value: b[y - 1] });
        y--;
    }

    ops.reverse();
    return ops;
}

function _renderDiff(beforeText, afterText) {
    const a = _tokenizeForDiff(beforeText);
    const b = _tokenizeForDiff(afterText);
    const ops = _buildDiffOps(a, b);

    let beforeHtml = '';
    let afterHtml = '';

    for (let i = 0; i < ops.length; i++) {
        const cur = ops[i];
        if (cur.type === 'equal') {
            const t = _escapeHtml(cur.value);
            beforeHtml += t;
            afterHtml += t;
            continue;
        }

        if (cur.type === 'delete') {
            const del = [];
            while (i < ops.length && ops[i].type === 'delete') {
                del.push(ops[i].value);
                i++;
            }
            const ins = [];
            while (i < ops.length && ops[i].type === 'insert') {
                ins.push(ops[i].value);
                i++;
            }
            i--;
            const delText = del.join('');
            const insText = ins.join('');
            if (ins.length > 0) {
                beforeHtml += `<span class="diff-mod">${_escapeHtml(delText)}</span>`;
                afterHtml += `<span class="diff-mod">${_escapeHtml(insText)}</span>`;
            } else {
                beforeHtml += `<span class="diff-del">${_escapeHtml(delText)}</span>`;
            }
            continue;
        }

        if (cur.type === 'insert') {
            const ins = [];
            while (i < ops.length && ops[i].type === 'insert') {
                ins.push(ops[i].value);
                i++;
            }
            i--;
            const insText = ins.join('');
            afterHtml += `<span class="diff-add">${_escapeHtml(insText)}</span>`;
        }
    }

    return { beforeHtml, afterHtml };
}

function startModAutoRefresh() {
    if (!modAutoRefreshEnabled) return;
    if (modAutoRefreshTimer) return;
    modAutoRefreshTimer = setInterval(async () => {
        if (currentTab !== 'modificationsView') return;
        if (modAutoRefreshInFlight) return;
        modAutoRefreshInFlight = true;
        try {
            await loadModifications(modCurrentPage);
        } finally {
            modAutoRefreshInFlight = false;
        }
    }, 10000);
}

function stopModAutoRefresh() {
    if (!modAutoRefreshTimer) return;
    clearInterval(modAutoRefreshTimer);
    modAutoRefreshTimer = null;
}

function setModAutoRefreshEnabled(enabled) {
    modAutoRefreshEnabled = !!enabled;
    if (modAutoRefreshEnabled) startModAutoRefresh();
    else stopModAutoRefresh();
    updateModSummary();
}
window.setModAutoRefreshEnabled = setModAutoRefreshEnabled;

async function loadModifications(page = 1) {
    const tbody = document.getElementById('modTableBody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="20" class="empty-message">加载中...</td></tr>';
    
    // 读取“仅显示重复 question_wiki_id”开关，若开启则一次性拉取更多数据用于前端判重
    const dupToggle = document.getElementById('modDupOnlyToggle');
    modDupOnly = !!(dupToggle && dupToggle.checked);
    const effectivePage = modDupOnly ? 1 : page;
    const effectivePageSize = modDupOnly ? 10000 : modPageSize;

    const kbId = document.getElementById('modSearchId')?.value || '';
    const product = document.getElementById('modSearchProduct')?.value || '';
    const question = document.getElementById('modSearchQuestion')?.value || '';
    const answer = document.getElementById('modSearchAnswer')?.value || '';
    const sourceModule = document.getElementById('modSourceSelect')?.value || '';
    const operation = document.getElementById('modOpSelect')?.value || '';
    const startTime = document.getElementById('modStartTime')?.value || '';
    const endTime = document.getElementById('modEndTime')?.value || '';
    
    const params = new URLSearchParams({
        page: effectivePage,
        pageSize: effectivePageSize,
        kb_id: kbId,
        product: product,
        question: question,
        answer: answer,
        source_module: sourceModule,
        operation: operation,
        start_time: startTime,
        end_time: endTime,
        sort_by: modSortBy || '',
        sort_dir: modSortDir || ''
    });
    
    try {
        const res = await api(`/kb/modifications?${params.toString()}`);
        if (res.success) {
            currentModifications = res.data || [];
            modTotal = res.total || 0;
            modCurrentPage = effectivePage;
            selectedModifications.clear();
            renderModificationsTable();
            updateModPagination();
            updateModSummary();
        } else {
             if (tbody) tbody.innerHTML = `<tr><td colspan="20" class="error-message">${res.message}</td></tr>`;
             updateModSummary();
        }
    } catch (e) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="20" class="error-message">加载失败: ${e.message}</td></tr>`;
        updateModSummary();
    }
}

function _getModRowKey(item, fallbackIdx) {
    const sid = item?.supabase_id;
    if (sid !== null && sid !== undefined && String(sid).trim() !== '') return String(sid);
    const kb = String(item?.kb_id || item?.question_wiki_id || '').trim();
    const mt = String(item?.modification_time || item?.modify_time || '').trim();
    const src = String(item?.source_module || item?.source || '').trim();
    const ct = String(item?.change_type || item?.operation || '').trim();
    if (kb && mt) return `${kb}@@${mt}@@${src}@@${ct}`;
    return `idx:${fallbackIdx}`;
}

function _modKeyIsDeletable(item) {
    const sid = item?.supabase_id;
    return sid !== null && sid !== undefined && String(sid).trim() !== '';
}

function updateModSelectAllCheckbox() {
    const el = document.getElementById('modSelectAll');
    if (!el) return;
    const deletableKeys = (currentModifications || []).filter(_modKeyIsDeletable).map((it, idx) => _getModRowKey(it, idx));
    if (deletableKeys.length === 0) {
        el.checked = false;
        el.indeterminate = false;
        el.disabled = true;
        updateModSummary();
        return;
    }
    el.disabled = false;
    const selectedCount = deletableKeys.filter(k => selectedModifications.has(k)).length;
    el.checked = selectedCount > 0 && selectedCount === deletableKeys.length;
    el.indeterminate = selectedCount > 0 && selectedCount < deletableKeys.length;
    updateModSummary();
}

function toggleModSelectAll(checked) {
    const want = !!checked;
    selectedModifications.clear();
    if (want) {
        (currentModifications || []).forEach((it, idx) => {
            if (!_modKeyIsDeletable(it)) return;
            selectedModifications.add(_getModRowKey(it, idx));
        });
    }
    renderModificationsTable();
}
window.toggleModSelectAll = toggleModSelectAll;

function toggleModRowSelection(key, checked) {
    const k = String(key || '');
    if (!k) return;
    if (checked) selectedModifications.add(k);
    else selectedModifications.delete(k);
    updateModSelectAllCheckbox();
}
window.toggleModRowSelection = toggleModRowSelection;

async function deleteSelectedModifications() {
    const keys = Array.from(selectedModifications);
    if (!keys.length) {
        alert('请先勾选要删除的记录（仅支持删除当前页勾选的记录）');
        return;
    }
    const ids = [];
    keys.forEach(k => {
        if (/^\d+$/.test(k)) ids.push(parseInt(k, 10));
        else ids.push(k);
    });
    const ok = confirm(`确认删除选中的 ${ids.length} 条修改记录？此操作不可恢复。`);
    if (!ok) return;
    try {
        const res = await api('/kb/modifications/delete', 'POST', { ids });
        if (!res?.success) {
            alert(`删除失败：${res?.message || 'unknown error'}`);
            return;
        }
        selectedModifications.clear();
        await loadModifications(modCurrentPage);
        alert(`已删除 ${res.deleted || ids.length} 条`);
    } catch (e) {
        alert(`删除失败：${e?.message || e}`);
    }
}
window.deleteSelectedModifications = deleteSelectedModifications;

function renderModificationsTable() {
    const tbody = document.getElementById('modTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    const dupToggle = document.getElementById('modDupOnlyToggle');
    modDupOnly = !!(dupToggle && dupToggle.checked);
    const { rows, duplicateIds } = getRenderedModificationsRows();
    renderedModifications = rows;
    if (modDupOnly) modTotal = rows.length;

    if (rows.length === 0) {
        renderedModifications = [];
        tbody.innerHTML = '<tr><td colspan="20" class="empty-message">暂无数据</td></tr>';
        updateModSelectAllCheckbox();
        return;
    }
    
    rows.forEach((item, idx) => {
        const tr = document.createElement('tr');
        const rowKey = _getModRowKey(item, idx);
        const deletable = _modKeyIsDeletable(item);
        const wikiId = String(item.question_wiki_id || item.kb_id || '').trim();
        const isDuplicate = wikiId && duplicateIds.has(wikiId);
        if (isDuplicate) tr.classList.add('mod-row-duplicate');
        
        const tdCheck = document.createElement('td');
        tdCheck.style.textAlign = 'center';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.disabled = !deletable;
        cb.checked = deletable && selectedModifications.has(rowKey);
        cb.onchange = () => toggleModRowSelection(rowKey, cb.checked);
        tdCheck.appendChild(cb);
        tr.appendChild(tdCheck);
        
        const changeType = item.change_type || item.operation || item.modification_type || 'edit';
        const opLabel = changeType === 'create' ? '增加' : (changeType === 'delete' ? '删除' : '修改');
        let badgeClass = 'badge-warning';
        if (changeType === 'create') badgeClass = 'badge-success';
        else if (changeType === 'delete') badgeClass = 'badge-danger';
        
        const tdOp = document.createElement('td');
        tdOp.innerHTML = `<span class="badge ${badgeClass}">${opLabel}</span>`;
        tr.appendChild(tdOp);

        const tdWikiId = document.createElement('td');
        tdWikiId.innerHTML = `
            <div class="mod-id-cell">
                <span class="mod-id-text">${_escapeHtml(wikiId || '-')}</span>
                ${isDuplicate ? '<span class="mod-dup-badge">重复</span>' : ''}
            </div>
        `;
        tdWikiId.style.userSelect = 'text';
        tdWikiId.style.cursor = 'text';
        tr.appendChild(tdWikiId);

        const tdQuestion = document.createElement('td');
        const qText = getModLatestField(item, 'question') || '';
        if (isModFieldChanged(item, 'question')) tdQuestion.classList.add('mod-cell-changed');
        tdQuestion.innerHTML = tdRenderExpandableText(`mod:${item.kb_id || item.question_wiki_id || idx}:question`, qText, {
            textareaClass: isModFieldChanged(item, 'question') ? 'mod-value-changed' : '',
            cellClass: 'is-modal-trigger',
            showExpandButton: false
        });
        tdQuestion.dataset.modalAllowed = '1';
        tdQuestion.dataset.colTitle = '问题';
        tr.appendChild(tdQuestion);

        const tdQType = document.createElement('td');
        const qType = getModLatestField(item, 'question_type');
        if (isModFieldChanged(item, 'question_type')) tdQType.classList.add('mod-cell-changed');
        tdQType.innerHTML = `<div class="${isModFieldChanged(item, 'question_type') ? 'mod-value-changed' : ''}">${qType ?? '-'}</div>`;
        tr.appendChild(tdQType);

        const tdAnswer = document.createElement('td');
        const aText = getModLatestField(item, 'answer') || '';
        if (isModFieldChanged(item, 'answer')) tdAnswer.classList.add('mod-cell-changed');
        tdAnswer.innerHTML = tdRenderExpandableText(`mod:${item.kb_id || item.question_wiki_id || idx}:answer`, aText, {
            textareaClass: isModFieldChanged(item, 'answer') ? 'mod-value-changed' : '',
            cellClass: 'is-modal-trigger',
            showExpandButton: false
        });
        tdAnswer.dataset.modalAllowed = '1';
        tdAnswer.dataset.colTitle = '答案';
        tr.appendChild(tdAnswer);

        const tdAType = document.createElement('td');
        const aType = getModLatestField(item, 'answer_type');
        if (isModFieldChanged(item, 'answer_type')) tdAType.classList.add('mod-cell-changed');
        tdAType.innerHTML = `<div class="${isModFieldChanged(item, 'answer_type') ? 'mod-value-changed' : ''}">${aType ?? '-'}</div>`;
        tr.appendChild(tdAType);

        const tdError = document.createElement('td');
        const errVal = getModLatestField(item, 'error_list');
        if (isModFieldChanged(item, 'error_list')) tdError.classList.add('mod-cell-changed');
        tdError.innerHTML = `<div class="${isModFieldChanged(item, 'error_list') ? 'mod-value-changed' : ''}">${formatJsonCell(errVal)}</div>`;
        tr.appendChild(tdError);

        const tdKeyword = document.createElement('td');
        const kwVal = getModLatestField(item, 'keyword_list');
        if (isModFieldChanged(item, 'keyword_list')) tdKeyword.classList.add('mod-cell-changed');
        tdKeyword.innerHTML = `<div class="${isModFieldChanged(item, 'keyword_list') ? 'mod-value-changed' : ''}">${formatJsonCell(kwVal)}</div>`;
        tr.appendChild(tdKeyword);

        const tdSimilar = document.createElement('td');
        const simVal = getModLatestField(item, 'similar_questions');
        if (isModFieldChanged(item, 'similar_questions')) tdSimilar.classList.add('mod-cell-changed');
        const simText = parseSmartListValue(simVal, { splitOnAsciiComma: true }).join(',');
        tdSimilar.innerHTML = tdRenderExpandableText(`mod:${item.kb_id || item.question_wiki_id || idx}:similar_questions`, simText, {
            textareaClass: isModFieldChanged(item, 'similar_questions') ? 'mod-value-changed' : '',
            cellClass: 'is-modal-trigger',
            showExpandButton: false
        });
        tdSimilar.dataset.modalAllowed = '1';
        tdSimilar.dataset.colTitle = '相似提问';
        tr.appendChild(tdSimilar);

        const tdBm25 = document.createElement('td');
        const bm25Val = getModLatestField(item, 'if_bm25');
        if (isModFieldChanged(item, 'if_bm25')) tdBm25.classList.add('mod-cell-changed');
        const bm25Text = (bm25Val === true) ? '是' : (bm25Val === false ? '否' : (bm25Val ?? '-'));
        tdBm25.innerHTML = `<div class="${isModFieldChanged(item, 'if_bm25') ? 'mod-value-changed' : ''}">${_escapeHtml(bm25Text)}</div>`;
        tr.appendChild(tdBm25);

        const tdProducts = document.createElement('td');
        const productsText = normalizeProductsListText(getModLatestField(item, 'products') ?? getModLatestField(item, 'product_name') ?? '-');
        if (isModFieldChanged(item, 'products')) tdProducts.classList.add('mod-cell-changed');
        tdProducts.innerHTML = tdRenderExpandableText(`mod:${item.kb_id || item.question_wiki_id || idx}:products`, productsText, {
            textareaClass: isModFieldChanged(item, 'products') ? 'mod-value-changed' : '',
            cellClass: 'is-modal-trigger',
            showExpandButton: false
        });
        tdProducts.dataset.modalAllowed = '1';
        tdProducts.dataset.colTitle = '机型';
        tr.appendChild(tdProducts);

        const urlOpts = { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true };
        const tdImage = document.createElement('td');
        const imgVal = getModLatestField(item, 'image_urls');
        const imgText = parseSmartListValue(imgVal, urlOpts).join(',');
        if (isModFieldChanged(item, 'image_urls')) tdImage.classList.add('mod-cell-changed');
        tdImage.innerHTML = tdRenderExpandableText(`mod:${item.kb_id || item.question_wiki_id || idx}:image_urls`, imgText, {
            textareaClass: isModFieldChanged(item, 'image_urls') ? 'mod-value-changed' : '',
            cellClass: 'is-modal-trigger',
            showExpandButton: false
        });
        tdImage.dataset.modalAllowed = '1';
        tdImage.dataset.colTitle = '图片链接';
        tr.appendChild(tdImage);

        const tdVideo = document.createElement('td');
        const videoVal = getModLatestField(item, 'video_urls');
        const videoText = parseSmartListValue(videoVal, urlOpts).join(',');
        if (isModFieldChanged(item, 'video_urls')) tdVideo.classList.add('mod-cell-changed');
        tdVideo.innerHTML = tdRenderExpandableText(`mod:${item.kb_id || item.question_wiki_id || idx}:video_urls`, videoText, {
            textareaClass: isModFieldChanged(item, 'video_urls') ? 'mod-value-changed' : '',
            cellClass: 'is-modal-trigger',
            showExpandButton: false
        });
        tdVideo.dataset.modalAllowed = '1';
        tdVideo.dataset.colTitle = '视频链接';
        tr.appendChild(tdVideo);

        const tdFile = document.createElement('td');
        const fileVal = getModLatestField(item, 'file_urls');
        const fileText = parseSmartListValue(fileVal, urlOpts).join(',');
        if (isModFieldChanged(item, 'file_urls')) tdFile.classList.add('mod-cell-changed');
        tdFile.innerHTML = tdRenderExpandableText(`mod:${item.kb_id || item.question_wiki_id || idx}:file_urls`, fileText, {
            textareaClass: isModFieldChanged(item, 'file_urls') ? 'mod-value-changed' : '',
            cellClass: 'is-modal-trigger',
            showExpandButton: false
        });
        tdFile.dataset.modalAllowed = '1';
        tdFile.dataset.colTitle = '文件链接';
        tr.appendChild(tdFile);

        const tdLinkType = document.createElement('td');
        const linkTypeText = String(getModLatestField(item, 'link_type') ?? '').trim() || '-';
        if (isModFieldChanged(item, 'link_type')) tdLinkType.classList.add('mod-cell-changed');
        tdLinkType.innerHTML = `<div class="${isModFieldChanged(item, 'link_type') ? 'mod-value-changed' : ''}">${_escapeHtml(linkTypeText)}</div>`;
        tr.appendChild(tdLinkType);

        const tdLinkUrl = document.createElement('td');
        const linkUrlVal = getModLatestField(item, 'link_url');
        const linkUrlText = parseSmartListValue(linkUrlVal, urlOpts).join(',');
        if (isModFieldChanged(item, 'link_url')) tdLinkUrl.classList.add('mod-cell-changed');
        tdLinkUrl.innerHTML = tdRenderExpandableText(`mod:${item.kb_id || item.question_wiki_id || idx}:link_url`, linkUrlText, {
            textareaClass: isModFieldChanged(item, 'link_url') ? 'mod-value-changed' : '',
            cellClass: 'is-modal-trigger',
            showExpandButton: false
        });
        tdLinkUrl.dataset.modalAllowed = '1';
        tdLinkUrl.dataset.colTitle = '跳转链接（url/key）';
        tr.appendChild(tdLinkUrl);

        const tdSource = document.createElement('td');
        tdSource.innerHTML = `<span class="mod-source-pill">${_escapeHtml(String(item.source_module || item.source || '-'))}</span>`;
        tr.appendChild(tdSource);

        const tdTime = document.createElement('td');
        tdTime.innerHTML = `<span class="mod-time-text">${_escapeHtml(item.modification_time ? new Date(item.modification_time).toLocaleString() : '-')}</span>`;
        tr.appendChild(tdTime);

        const tdActions = document.createElement('td');
        tdActions.innerHTML = `
            <div class="kb-cell-actions-inline kb-cell-actions-center">
                <button class="kb-mini-action-btn kb-mini-action-btn-icon" onclick="openModDetails(${idx})" title="查看详情"><i class="fas fa-circle-info"></i></button>
                <button class="kb-mini-action-btn kb-mini-action-btn-icon" onclick="copyModRow(${idx})" title="复制记录"><i class="fas fa-copy"></i></button>
            </div>
        `;
        tr.appendChild(tdActions);
        
        tbody.appendChild(tr);
    });
    
    const selectAllEl = document.getElementById('modSelectAll');
    if (selectAllEl && !selectAllEl.dataset.bound) {
        selectAllEl.dataset.bound = '1';
        selectAllEl.addEventListener('change', () => toggleModSelectAll(selectAllEl.checked));
    }
    updateModSelectAllCheckbox();
    makeTableResizable('modTable');
    modBindCellDetailInteractions();
    tdRefreshCellOverflow(document.getElementById('modTable') || document);
}

function initModSortHeaders() {
    const table = document.getElementById('modTable');
    if (!table) return;
    const ths = table.querySelectorAll('th.sortable[data-mod-sort-by]');
    ths.forEach(th => {
        if (th.dataset.modSortBound) return;
        th.dataset.modSortBound = '1';
        th.addEventListener('click', () => {
            const field = th.getAttribute('data-mod-sort-by') || '';
            if (!field) return;
            if (modSortBy === field) {
                modSortDir = modSortDir === 'asc' ? 'desc' : 'asc';
            } else {
                modSortBy = field;
                modSortDir = 'asc';
            }
            loadModifications(1);
        });
    });
}

function _formatDetailsKV(obj, changedFields, diffMap, side) {
    const fields = [
        'question', 'answer', 'products', 'question_type', 'answer_type', 'error_list',
        'image_urls', 'video_urls', 'file_urls', 'link_type', 'link_url',
        'similar_questions', 'keyword_list', 'if_bm25'
    ];
    const labelMap = {
        question: '问题',
        answer: '答案',
        products: '机型',
        question_type: '问题类型',
        answer_type: '答案类型',
        error_list: '错误列表',
        image_urls: '图片链接',
        video_urls: '视频链接',
        file_urls: '文件链接',
        link_type: '跳转链接类型',
        link_url: '跳转链接（url/key）',
        similar_questions: '相似提问',
        keyword_list: '关键词',
        if_bm25: 'BM25'
    };
    const wrap = document.createElement('div');
    wrap.className = 'mod-details-kv';
    fields.forEach(k => {
        const row = document.createElement('div');
        row.className = 'mod-details-row';
        const key = document.createElement('div');
        key.className = 'mod-details-key';
        key.textContent = labelMap[k] || k;
        const val = document.createElement('div');
        val.className = 'mod-details-val';
        const v = obj && _hasOwn(obj, k) ? obj[k] : null;
        if (Array.isArray(changedFields) && changedFields.includes(k)) {
            val.classList.add('mod-value-changed');
        }
        if (diffMap && diffMap[k] && typeof diffMap[k][side] === 'string') {
            const diffHtml = diffMap[k][side];
            const plain = (diffHtml || '').replace(/<[^>]*>/g, '').trim();
            if (side === 'before' && !plain) {
                val.textContent = '-';
            } else {
                val.innerHTML = diffHtml;
            }
        } else if (typeof v === 'string') {
            if (k === 'products') {
                val.textContent = normalizeProductsListText(v);
            } else if (k === 'similar_questions') {
                val.textContent = parseSmartListValue(v, { splitOnAsciiComma: true }).join(',');
            } else if (k === 'keyword_list') {
                val.textContent = parseSmartListValue(v, { splitOnAsciiComma: true }).join(',');
            } else if (k === 'error_list') {
                val.textContent = formatJsonCell(v);
            } else if (k === 'image_urls' || k === 'video_urls' || k === 'file_urls' || k === 'link_url') {
                val.textContent = parseSmartListValue(v, { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true }).join(',');
            } else {
                val.textContent = v;
            }
        } else if (Array.isArray(v)) {
            if (k === 'products') {
                val.textContent = normalizeProductsListText(v);
            } else if (k === 'similar_questions') {
                val.textContent = parseSmartListValue(v, { splitOnAsciiComma: true }).join(',');
            } else if (k === 'keyword_list') {
                val.textContent = parseSmartListValue(v, { splitOnAsciiComma: true }).join(',');
            } else if (k === 'error_list') {
                val.textContent = formatJsonCell(v);
            } else if (k === 'image_urls' || k === 'video_urls' || k === 'file_urls' || k === 'link_url') {
                val.textContent = parseSmartListValue(v, { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true }).join(',');
            } else {
                val.textContent = v.map(x => (x === null || x === undefined) ? '' : String(x)).filter(Boolean).join(',');
            }
        } else if (typeof v === 'boolean') {
            val.textContent = (k === 'if_bm25') ? (v ? '是' : '否') : String(v);
        } else if (v == null) {
            val.textContent = '-';
        } else {
            try {
                val.textContent = JSON.stringify(v, null, 2);
            } catch {
                val.textContent = String(v);
            }
        }
        row.appendChild(key);
        row.appendChild(val);
        wrap.appendChild(row);
    });
    return wrap;
}

function _openModDetailsByItem(item) {
    if (!item) return;
    const modal = document.getElementById('modDetailsModal');
    if (!modal) return;
    const beforeEl = document.getElementById('modDetailsBefore');
    const afterEl = document.getElementById('modDetailsAfter');
    const metaEl = document.getElementById('modDetailsMeta');
    const changedEl = document.getElementById('modDetailsChanged');

    const wikiId = item.question_wiki_id || item.kb_id || '-';
    const source = item.source_module || item.source || '-';
    const timeText = item.modification_time ? new Date(item.modification_time).toLocaleString() : '-';
    metaEl.textContent = `问题编号: ${wikiId} ｜ 来源: ${source} ｜ 修改时间: ${timeText}`;

    const rawChangedFields = item.changed_fields || item.changedFields || [];
    const beforeObj = item.before || {};
    const afterObj = item.after || {};
    const allFields = [
        'question', 'answer', 'products', 'question_type', 'answer_type', 'error_list',
        'image_urls', 'video_urls', 'file_urls', 'link_type', 'link_url',
        'similar_questions', 'keyword_list', 'if_bm25'
    ];
    const normalizeVal = (k, v) => {
        if (v === undefined || v === null) return null;
        if (k === 'if_bm25') return v === true ? '1' : (v === false ? '0' : String(v));
        if (k === 'products') return normalizeProductsListText(v);
        if (Array.isArray(v)) {
            return v.map(x => String(x ?? '').trim()).filter(Boolean).sort().join(',');
        }
        if (typeof v === 'string') return v.trim();
        try {
            return JSON.stringify(v);
        } catch {
            return String(v);
        }
    };
    let changedFields = (Array.isArray(rawChangedFields) ? rawChangedFields : []).slice();
    if (changedFields.length > 0) {
        const hasSnapshot = (item.before && typeof item.before === 'object') || (item.after && typeof item.after === 'object');
        if (hasSnapshot) {
            changedFields = changedFields.filter(k => isModFieldChanged(item, k));
        }
    }
    if (changedFields.length === 0) {
        changedFields = allFields.filter(k => normalizeVal(k, beforeObj && _hasOwn(beforeObj, k) ? beforeObj[k] : null) !== normalizeVal(k, afterObj && _hasOwn(afterObj, k) ? afterObj[k] : null));
    }
    if (changedFields.length > 0) {
        const labelMap = {
            question: '问题',
            answer: '答案',
            products: '机型',
            question_type: '问题类型',
            answer_type: '答案类型',
            error_list: '错误列表',
            keyword_list: '关键词',
            similar_questions: '相似提问',
            if_bm25: 'BM25',
            image_urls: '图片链接',
            video_urls: '视频链接',
            file_urls: '文件链接',
            link_type: '跳转链接类型',
            link_url: '跳转链接（url/key）'
        };
        const changedText = changedFields.map(k => labelMap[k] || k).join(', ');
        changedEl.innerHTML = `<span style="color:#666;">变更字段：</span><span class="mod-value-changed">${changedText}</span>`;
    } else {
        changedEl.innerHTML = `<span style="color:#666;">变更字段：</span>-`;
    }

    const diffMap = {};
    ['question', 'answer', 'products'].forEach(k => {
        if (!changedFields.includes(k)) return;
        const bv = beforeObj && _hasOwn(beforeObj, k) ? beforeObj[k] : '';
        const av = afterObj && _hasOwn(afterObj, k) ? afterObj[k] : '';
        const bText = (k === 'products') ? normalizeProductsListText(bv) : (typeof bv === 'string' ? bv : String(bv ?? ''));
        const aText = (k === 'products') ? normalizeProductsListText(av) : (typeof av === 'string' ? av : String(av ?? ''));
        const r = _renderDiff(bText, aText);
        diffMap[k] = { before: r.beforeHtml, after: r.afterHtml };
    });

    if (beforeEl) {
        beforeEl.innerHTML = '';
        beforeEl.appendChild(_formatDetailsKV(beforeObj, changedFields, diffMap, 'before'));
    }
    if (afterEl) {
        afterEl.innerHTML = '';
        afterEl.appendChild(_formatDetailsKV(afterObj, changedFields, diffMap, 'after'));
    }

    modal.style.display = 'block';
}

function openModDetails(index) {
    const item = renderedModifications[index] || currentModifications[index];
    _openModDetailsByItem(item);
}

function closeModDetailsModal() {
    const modal = document.getElementById('modDetailsModal');
    if (modal) modal.style.display = 'none';
}
window.openModDetails = openModDetails;
window.closeModDetailsModal = closeModDetailsModal;

function updateModPagination() {
    const info = document.getElementById('modPageInfo');
    const prev = document.getElementById('prevModPageBtn');
    const next = document.getElementById('nextModPageBtn');
    const totalPages = modDupOnly ? 1 : Math.max(1, Math.ceil((modTotal || 0) / Math.max(modPageSize || 1, 1)));
    
    if (modDupOnly) {
        if (prev) prev.disabled = true;
        if (next) next.disabled = true;
    } else {
        if (prev) prev.disabled = modCurrentPage <= 1;
        if (next) next.disabled = modCurrentPage * modPageSize >= modTotal;
    }
    if (info) {
        info.innerText = modDupOnly
            ? `重复记录 ${modTotal} 条`
            : `第 ${Math.min(modCurrentPage || 1, totalPages)} / ${totalPages} 页，共 ${modTotal || 0} 条`;
    }
}

function changeModPage(offset) {
    loadModifications(modCurrentPage + offset);
}

function changeModPageSize() {
    modPageSize = parseInt(document.getElementById('modPageSizeSelect').value);
    loadModifications(1);
}

function jumpModPage() {
    if (modDupOnly) return;
    const input = document.getElementById('modPageJumpInput');
    if (!input) return;
    const totalPages = Math.max(1, Math.ceil((modTotal || 0) / Math.max(modPageSize || 1, 1)));
    const target = Math.min(totalPages, Math.max(1, parseInt(input.value || '1', 10) || 1));
    input.value = String(target);
    loadModifications(target);
}
window.jumpModPage = jumpModPage;

function resetModificationsFilter() {
    document.getElementById('modSearchId').value = '';
    document.getElementById('modSearchProduct').value = '';
    document.getElementById('modSearchQuestion').value = '';
    document.getElementById('modSearchAnswer').value = '';
    const s = document.getElementById('modSourceSelect');
    if (s) s.value = '';
    const op = document.getElementById('modOpSelect');
    if (op) op.value = '';
    const st = document.getElementById('modStartTime');
    const et = document.getElementById('modEndTime');
    if (st) st.value = '';
    if (et) et.value = '';
    const dup = document.getElementById('modDupOnlyToggle');
    if (dup) dup.checked = false;
    loadModifications(1);
}

function _buildModFilterParams() {
    const kbId = document.getElementById('modSearchId')?.value || '';
    const product = document.getElementById('modSearchProduct')?.value || '';
    const question = document.getElementById('modSearchQuestion')?.value || '';
    const answer = document.getElementById('modSearchAnswer')?.value || '';
    const sourceModule = document.getElementById('modSourceSelect')?.value || '';
    const operation = document.getElementById('modOpSelect')?.value || '';
    const startTime = document.getElementById('modStartTime')?.value || '';
    const endTime = document.getElementById('modEndTime')?.value || '';
    return { kb_id: kbId, product, question, answer, source_module: sourceModule, operation, start_time: startTime, end_time: endTime };
}

async function copyModRow(index) {
    const item = renderedModifications[index] || currentModifications[index];
    if (!item) return;
    const out = {
        opera: item.opera || item.change_type || item.operation || item.modification_type || 'edit',
        question_wiki_id: item.question_wiki_id || item.kb_id || '',
        question: getModLatestField(item, 'question') || '',
        question_type: getModLatestField(item, 'question_type') ?? null,
        answer: getModLatestField(item, 'answer') || '',
        answer_type: getModLatestField(item, 'answer_type') ?? null,
        error_list: getModLatestField(item, 'error_list') ?? null,
        keyword_list: getModLatestField(item, 'keyword_list') ?? null,
        similar_questions: getModLatestField(item, 'similar_questions') ?? null,
        if_bm25: getModLatestField(item, 'if_bm25') ?? null,
        products: getModLatestField(item, 'products') ?? getModLatestField(item, 'product_name') ?? null,
        image_urls: getModLatestField(item, 'image_urls') ?? null,
        video_urls: getModLatestField(item, 'video_urls') ?? null,
        file_urls: getModLatestField(item, 'file_urls') ?? null,
        link_type: getModLatestField(item, 'link_type') ?? null,
        link_url: getModLatestField(item, 'link_url') ?? null,
        urls: getModLatestUrlsList(item),
        source_module: item.source_module || item.source || '',
        modify_time: item.modify_time || item.modification_time || '',
        before: item.before ?? null,
        after: item.after ?? null
    };
    const text = JSON.stringify(out, null, 2);
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
        } else {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            ta.remove();
        }
        showToast('已复制到剪贴板');
    } catch (e) {
        alert('复制失败: ' + (e && e.message ? e.message : String(e)));
    }
}
window.copyModRow = copyModRow;

function exportRawModifications() {
    const params = new URLSearchParams(_buildModFilterParams());
    downloadByUrl(`${API_BASE}/kb/modifications/export_raw?${params.toString()}`);
}
window.exportRawModifications = exportRawModifications;

function smartMergeExportModifications() {
    const params = new URLSearchParams(_buildModFilterParams());
    downloadByUrl(`${API_BASE}/kb/modifications/smart_merge_export?${params.toString()}`);
}
window.smartMergeExportModifications = smartMergeExportModifications;

async function downloadByUrl(url) {
    try {
        const resp = await fetch(url, { method: 'GET', credentials: 'include' });
        if (!resp.ok) {
            const text = await resp.text();
            throw new Error(text || `HTTP ${resp.status}`);
        }
        const cd = resp.headers.get('content-disposition') || '';
        let filename = '';
        const m1 = cd.match(/filename\\*=UTF-8''([^;]+)/i);
        const m2 = cd.match(/filename=\"?([^\";]+)\"?/i);
        if (m1 && m1[1]) filename = decodeURIComponent(m1[1]);
        else if (m2 && m2[1]) filename = m2[1];

        const blob = await resp.blob();
        const href = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = href;
        if (filename) a.download = filename;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            try { URL.revokeObjectURL(href); } catch (e) {}
            try { a.remove(); } catch (e) {}
        }, 1000);
    } catch (e) {
        showToast('导出失败: ' + (e && e.message ? e.message : String(e)), 'error');
    }
}
window.downloadByUrl = downloadByUrl;

async function createArchiveFromCurrent() {
    openArchiveNameModal();
}
window.createArchiveFromCurrent = createArchiveFromCurrent;

function openArchiveNameModal(operationId = null) {
    const modal = document.getElementById('archiveNameModal');
    const input = document.getElementById('archiveNameInput');
    const btn = document.getElementById('archiveNameConfirmBtn');
    const impact = document.getElementById('archiveImpactPreview');
    if (btn) btn.disabled = false;
    if (impact) {
        impact.textContent = '正在读取待归档记录数...';
        fetchArchivePreview(operationId)
            .then(preview => {
                const scope = operationId ? '本次提交待归档' : '当前待归档';
                impact.textContent = `${scope} ${preview.count || 0} 条；确认后会从当前修改记录列表删除 ${preview.delete_count || 0} 条对应记录。`;
            })
            .catch(e => {
                impact.textContent = `归档预览读取失败：${e && e.message ? e.message : String(e)}`;
            });
    }
    if (input) {
        const now = new Date();
        const pad2 = (n) => String(n).padStart(2, '0');
        const preset = `${now.getFullYear()}${pad2(now.getMonth() + 1)}${pad2(now.getDate())}_${pad2(now.getHours())}${pad2(now.getMinutes())}${pad2(now.getSeconds())}`;
        if (!String(input.value || '').trim()) input.value = preset;
    }
    if (modal) modal.style.display = 'block';
    if (input) setTimeout(() => input.focus(), 0);
}
window.openArchiveNameModal = openArchiveNameModal;

function closeArchiveNameModal() {
    const modal = document.getElementById('archiveNameModal');
    if (modal) modal.style.display = 'none';
    const impact = document.getElementById('archiveImpactPreview');
    if (impact) impact.textContent = '';
    if (_smArchiveModalBackup) {
        const title = modal?.querySelector('.modal-header h3');
        const input = document.getElementById('archiveNameInput');
        const btn = document.getElementById('archiveNameConfirmBtn');
        if (title && _smArchiveModalBackup.titleText !== null && _smArchiveModalBackup.titleText !== undefined) title.textContent = _smArchiveModalBackup.titleText;
        if (input) input.onkeydown = _smArchiveModalBackup.inputKeydown;
        if (btn) btn.onclick = _smArchiveModalBackup.btnClick;
        _smArchiveModalBackup = null;
    }
}
window.closeArchiveNameModal = closeArchiveNameModal;

async function confirmCreateArchiveFromCurrent() {
    const input = document.getElementById('archiveNameInput');
    const btn = document.getElementById('archiveNameConfirmBtn');
    const name = String(input?.value || '').trim();
    if (!name) {
        showToast('请填写归档批次名称', 'warning');
        if (input) input.focus();
        return;
    }
    if (btn) btn.disabled = true;
    try {
        const preview = await confirmArchiveImpact();
        const res = await api('/archives', 'POST', {
            batch_name: name,
            confirm_archive: true,
            expected_count: preview.count || 0
        });
        if (res && res.success) {
            closeArchiveNameModal();
            showToast(`归档成功：${res.record_count || 0} 条`, 'success');
            switchTab('archiveView');
        } else {
            showToast(res && res.message ? res.message : '归档失败', 'error');
        }
    } catch (e) {
        showToast('归档失败: ' + (e && e.message ? e.message : String(e)), 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}
window.confirmCreateArchiveFromCurrent = confirmCreateArchiveFromCurrent;

let archiveBatches = [];
async function loadArchives() {
    const tbody = document.getElementById('archiveTableBody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="empty-message">加载中...</td></tr>';
    const q = document.getElementById('archiveSearchQ')?.value || '';
    try {
        const res = await api(`/archives?q=${encodeURIComponent(q)}`);
        if (res && res.success) {
            archiveBatches = res.data || [];
            renderArchivesTable();
        } else {
            if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="error-message">加载失败</td></tr>';
        }
    } catch (e) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="error-message">加载失败: ${_escapeHtml(e.message)}</td></tr>`;
    }
}
window.loadArchives = loadArchives;

function renderArchivesTable() {
    const tbody = document.getElementById('archiveTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (!archiveBatches || archiveBatches.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-message">暂无数据</td></tr>';
        return;
    }
    archiveBatches.forEach(b => {
        const tr = document.createElement('tr');
        const tdId = document.createElement('td');
        tdId.textContent = b.id;
        tr.appendChild(tdId);
        const tdName = document.createElement('td');
        tdName.textContent = b.batch_name || '-';
        tr.appendChild(tdName);
        const tdCnt = document.createElement('td');
        tdCnt.textContent = (b.record_count ?? 0);
        tr.appendChild(tdCnt);
        const tdBy = document.createElement('td');
        tdBy.textContent = b.created_by || '-';
        tr.appendChild(tdBy);
        const tdAt = document.createElement('td');
        tdAt.textContent = b.created_at ? new Date(b.created_at).toLocaleString() : '-';
        tr.appendChild(tdAt);
        const tdAct = document.createElement('td');
        tdAct.innerHTML = `
            <div class="kb-cell-actions-inline kb-cell-actions-center">
                <button class="kb-mini-action-btn kb-mini-action-btn-icon" onclick="openArchiveRecordsModal(${b.id}, '${_escapeAttr(b.batch_name || '')}')" title="查看批次"><i class="fas fa-eye"></i></button>
                <button class="kb-mini-action-btn kb-mini-action-btn-icon" onclick="exportArchiveBatch(${b.id})" title="导出批次"><i class="fas fa-file-export"></i></button>
            </div>
        `;
        tr.appendChild(tdAct);
        tbody.appendChild(tr);
    });
    makeTableResizable('archiveTable');
}

function resetArchivesFilter() {
    const q = document.getElementById('archiveSearchQ');
    if (q) q.value = '';
    loadArchives();
}
window.resetArchivesFilter = resetArchivesFilter;

async function createArchiveBatch() {
    const input = document.getElementById('archiveBatchName');
    const status = document.getElementById('archiveStatus');
    const name = String(input?.value || '').trim();
    if (!name) {
        alert('请填写批次名称');
        return;
    }
    if (status) status.textContent = '归档中...';
    try {
        const preview = await confirmArchiveImpact();
        const res = await api('/archives', 'POST', {
            batch_name: name,
            confirm_archive: true,
            expected_count: preview.count || 0
        });
        if (res && res.success) {
            if (status) status.textContent = `归档成功：${res.record_count || 0} 条`;
            if (input) input.value = '';
            await loadArchives();
        } else {
            if (status) status.textContent = '';
            alert(res && res.message ? res.message : '归档失败');
        }
    } catch (e) {
        if (status) status.textContent = '';
        alert('归档失败: ' + (e && e.message ? e.message : String(e)));
    }
}
window.createArchiveBatch = createArchiveBatch;

function exportArchiveBatch(batchId) {
    window.location = `${API_BASE}/archives/${batchId}/export`;
}
window.exportArchiveBatch = exportArchiveBatch;

let archiveCurrentBatchId = null;
let archiveCurrentBatchName = '';
let archiveRecCurrentPage = 1;
let archiveRecPageSize = 20;
let archiveRecTotal = 0;
let currentArchiveRecords = [];

function openArchiveRecordsModal(batchId, batchName) {
    archiveCurrentBatchId = batchId;
    archiveCurrentBatchName = batchName || '';
    const title = document.getElementById('archiveRecordsTitle');
    if (title) title.textContent = `归档记录：${archiveCurrentBatchName || batchId}`;
    const modal = document.getElementById('archiveRecordsModal');
    if (modal) modal.style.display = 'block';
    loadArchiveRecords(1);
}
window.openArchiveRecordsModal = openArchiveRecordsModal;

function closeArchiveRecordsModal() {
    const modal = document.getElementById('archiveRecordsModal');
    if (modal) modal.style.display = 'none';
}
window.closeArchiveRecordsModal = closeArchiveRecordsModal;

function _buildArchiveRecFilterParams() {
    const kbId = document.getElementById('archiveRecSearchId')?.value || '';
    const product = document.getElementById('archiveRecSearchProduct')?.value || '';
    const question = document.getElementById('archiveRecSearchQuestion')?.value || '';
    const sourceModule = document.getElementById('archiveRecSourceSelect')?.value || '';
    const startTime = document.getElementById('archiveRecStartTime')?.value || '';
    const endTime = document.getElementById('archiveRecEndTime')?.value || '';
    return { kb_id: kbId, product, question, source_module: sourceModule, start_time: startTime, end_time: endTime };
}

async function loadArchiveRecords(page = 1) {
    if (!archiveCurrentBatchId) return;
    const tbody = document.getElementById('archiveRecTableBody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="15" class="empty-message">加载中...</td></tr>';
    const base = _buildArchiveRecFilterParams();
    const params = new URLSearchParams({
        page: page,
        pageSize: archiveRecPageSize,
        kb_id: base.kb_id,
        product: base.product,
        question: base.question,
        source_module: base.source_module,
        start_time: base.start_time,
        end_time: base.end_time
    });
    try {
        const res = await api(`/archives/${archiveCurrentBatchId}/records?${params.toString()}`);
        if (res && res.success) {
            currentArchiveRecords = res.data || [];
            archiveRecTotal = res.total || 0;
            archiveRecCurrentPage = page;
            renderArchiveRecTable();
            updateArchiveRecPagination();
        } else {
            if (tbody) tbody.innerHTML = '<tr><td colspan="15" class="error-message">加载失败</td></tr>';
        }
    } catch (e) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="15" class="error-message">加载失败: ${_escapeHtml(e.message)}</td></tr>`;
    }
}
window.loadArchiveRecords = loadArchiveRecords;

function renderArchiveRecTable() {
    const tbody = document.getElementById('archiveRecTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (!currentArchiveRecords || currentArchiveRecords.length === 0) {
        tbody.innerHTML = '<tr><td colspan="19" class="empty-message">暂无数据</td></tr>';
        return;
    }
    currentArchiveRecords.forEach((item, idx) => {
        const tr = document.createElement('tr');

        const changeType = item.change_type || item.opera || item.operation || item.modification_type || 'edit';
        const opLabel = changeType === 'create' ? '增加' : (changeType === 'delete' ? '删除' : '修改');
        let badgeClass = 'badge-warning';
        if (changeType === 'create') badgeClass = 'badge-success';
        else if (changeType === 'delete') badgeClass = 'badge-danger';

        const tdOp = document.createElement('td');
        tdOp.innerHTML = `<span class="badge ${badgeClass}">${opLabel}</span>`;
        tr.appendChild(tdOp);

        const tdWikiId = document.createElement('td');
        tdWikiId.textContent = item.question_wiki_id || item.kb_id || '-';
        tr.appendChild(tdWikiId);

        const tdQuestion = document.createElement('td');
        const qText = getModLatestField(item, 'question') || '';
        if (isModFieldChanged(item, 'question')) tdQuestion.classList.add('mod-cell-changed');
        tdQuestion.innerHTML = tdRenderExpandableText(`archive:${item.kb_id || item.question_wiki_id || idx}:question`, qText, {
            textareaClass: isModFieldChanged(item, 'question') ? 'mod-value-changed' : ''
        });
        tr.appendChild(tdQuestion);

        const tdQType = document.createElement('td');
        const qType = getModLatestField(item, 'question_type');
        if (isModFieldChanged(item, 'question_type')) tdQType.classList.add('mod-cell-changed');
        tdQType.innerHTML = `<div class="${isModFieldChanged(item, 'question_type') ? 'mod-value-changed' : ''}">${_escapeHtml(qType ?? '-')}</div>`;
        tr.appendChild(tdQType);

        const tdAnswer = document.createElement('td');
        const aText = getModLatestField(item, 'answer') || '';
        if (isModFieldChanged(item, 'answer')) tdAnswer.classList.add('mod-cell-changed');
        tdAnswer.innerHTML = tdRenderExpandableText(`archive:${item.kb_id || item.question_wiki_id || idx}:answer`, aText, {
            textareaClass: isModFieldChanged(item, 'answer') ? 'mod-value-changed' : ''
        });
        tr.appendChild(tdAnswer);

        const tdAType = document.createElement('td');
        const aType = getModLatestField(item, 'answer_type');
        if (isModFieldChanged(item, 'answer_type')) tdAType.classList.add('mod-cell-changed');
        tdAType.innerHTML = `<div class="${isModFieldChanged(item, 'answer_type') ? 'mod-value-changed' : ''}">${_escapeHtml(aType ?? '-')}</div>`;
        tr.appendChild(tdAType);

        const tdError = document.createElement('td');
        const errVal = getModLatestField(item, 'error_list');
        if (isModFieldChanged(item, 'error_list')) tdError.classList.add('mod-cell-changed');
        tdError.innerHTML = `<div class="${isModFieldChanged(item, 'error_list') ? 'mod-value-changed' : ''}">${formatJsonCell(errVal)}</div>`;
        tr.appendChild(tdError);

        const tdKeyword = document.createElement('td');
        const kwVal = getModLatestField(item, 'keyword_list');
        if (isModFieldChanged(item, 'keyword_list')) tdKeyword.classList.add('mod-cell-changed');
        tdKeyword.innerHTML = `<div class="${isModFieldChanged(item, 'keyword_list') ? 'mod-value-changed' : ''}">${formatJsonCell(kwVal)}</div>`;
        tr.appendChild(tdKeyword);

        const tdSimilar = document.createElement('td');
        const simVal = getModLatestField(item, 'similar_questions');
        if (isModFieldChanged(item, 'similar_questions')) tdSimilar.classList.add('mod-cell-changed');
        const simText = parseSmartListValue(simVal, { splitOnAsciiComma: true }).join(',');
        tdSimilar.innerHTML = tdRenderExpandableText(`archive:${item.kb_id || item.question_wiki_id || idx}:similar_questions`, simText, {
            textareaClass: isModFieldChanged(item, 'similar_questions') ? 'mod-value-changed' : ''
        });
        tr.appendChild(tdSimilar);

        const tdBm25 = document.createElement('td');
        const bm25Val = getModLatestField(item, 'if_bm25');
        if (isModFieldChanged(item, 'if_bm25')) tdBm25.classList.add('mod-cell-changed');
        const bm25Text = (bm25Val === true) ? '是' : (bm25Val === false ? '否' : (bm25Val ?? '-'));
        tdBm25.innerHTML = `<div class="${isModFieldChanged(item, 'if_bm25') ? 'mod-value-changed' : ''}">${_escapeHtml(bm25Text)}</div>`;
        tr.appendChild(tdBm25);

        const tdProducts = document.createElement('td');
        const productsText = getModLatestField(item, 'products') ?? getModLatestField(item, 'product_name') ?? '-';
        if (isModFieldChanged(item, 'products')) tdProducts.classList.add('mod-cell-changed');
        tdProducts.innerHTML = tdRenderExpandableText(`archive:${item.kb_id || item.question_wiki_id || idx}:products`, normalizeProductsListText(productsText), {
            textareaClass: isModFieldChanged(item, 'products') ? 'mod-value-changed' : ''
        });
        tr.appendChild(tdProducts);

        const urlOpts = { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true };
        const tdImage = document.createElement('td');
        const imgVal = getModLatestField(item, 'image_urls');
        const imgText = parseSmartListValue(imgVal, urlOpts).join(',');
        if (isModFieldChanged(item, 'image_urls')) tdImage.classList.add('mod-cell-changed');
        tdImage.innerHTML = tdRenderExpandableText(`archive:${item.kb_id || item.question_wiki_id || idx}:image_urls`, imgText, {
            textareaClass: isModFieldChanged(item, 'image_urls') ? 'mod-value-changed' : ''
        });
        tr.appendChild(tdImage);

        const tdVideo = document.createElement('td');
        const videoVal = getModLatestField(item, 'video_urls');
        const videoText = parseSmartListValue(videoVal, urlOpts).join(',');
        if (isModFieldChanged(item, 'video_urls')) tdVideo.classList.add('mod-cell-changed');
        tdVideo.innerHTML = tdRenderExpandableText(`archive:${item.kb_id || item.question_wiki_id || idx}:video_urls`, videoText, {
            textareaClass: isModFieldChanged(item, 'video_urls') ? 'mod-value-changed' : ''
        });
        tr.appendChild(tdVideo);

        const tdFile = document.createElement('td');
        const fileVal = getModLatestField(item, 'file_urls');
        const fileText = parseSmartListValue(fileVal, urlOpts).join(',');
        if (isModFieldChanged(item, 'file_urls')) tdFile.classList.add('mod-cell-changed');
        tdFile.innerHTML = tdRenderExpandableText(`archive:${item.kb_id || item.question_wiki_id || idx}:file_urls`, fileText, {
            textareaClass: isModFieldChanged(item, 'file_urls') ? 'mod-value-changed' : ''
        });
        tr.appendChild(tdFile);

        const tdLinkType = document.createElement('td');
        const linkTypeText = String(getModLatestField(item, 'link_type') ?? '').trim() || '-';
        if (isModFieldChanged(item, 'link_type')) tdLinkType.classList.add('mod-cell-changed');
        tdLinkType.innerHTML = `<div class="${isModFieldChanged(item, 'link_type') ? 'mod-value-changed' : ''}">${_escapeHtml(linkTypeText)}</div>`;
        tr.appendChild(tdLinkType);

        const tdLinkUrl = document.createElement('td');
        const linkUrlVal = getModLatestField(item, 'link_url');
        const linkUrlText = parseSmartListValue(linkUrlVal, urlOpts).join(',');
        if (isModFieldChanged(item, 'link_url')) tdLinkUrl.classList.add('mod-cell-changed');
        tdLinkUrl.innerHTML = tdRenderExpandableText(`archive:${item.kb_id || item.question_wiki_id || idx}:link_url`, linkUrlText, {
            textareaClass: isModFieldChanged(item, 'link_url') ? 'mod-value-changed' : ''
        });
        tr.appendChild(tdLinkUrl);

        const tdSource = document.createElement('td');
        tdSource.textContent = item.source_module || item.source || '-';
        tr.appendChild(tdSource);

        const tdTime = document.createElement('td');
        const t = item.modify_time || item.modification_time;
        tdTime.textContent = t ? new Date(t).toLocaleString() : '-';
        tr.appendChild(tdTime);

        const tdActions = document.createElement('td');
        tdActions.innerHTML = `
            <div style="display:flex; gap:6px; justify-content:center;">
                <button class="action-btn btn-sm" onclick="openArchiveRecDetails(${idx})">详情</button>
                <button class="action-btn btn-sm" onclick="copyArchiveRecRow(${idx})">复制</button>
            </div>
        `;
        tr.appendChild(tdActions);

        tbody.appendChild(tr);
    });
    makeTableResizable('archiveRecTable');
    tdRefreshCellOverflow(document.getElementById('archiveRecTable') || document);
}

function updateArchiveRecPagination() {
    const info = document.getElementById('archiveRecPageInfo');
    const prev = document.getElementById('prevArchiveRecPageBtn');
    const next = document.getElementById('nextArchiveRecPageBtn');
    if (info) info.innerText = `共 ${archiveRecTotal} 条`;
    if (prev) prev.disabled = archiveRecCurrentPage <= 1;
    if (next) next.disabled = archiveRecCurrentPage * archiveRecPageSize >= archiveRecTotal;
}

function changeArchiveRecPage(offset) {
    loadArchiveRecords(archiveRecCurrentPage + offset);
}
window.changeArchiveRecPage = changeArchiveRecPage;

function changeArchiveRecPageSize() {
    archiveRecPageSize = parseInt(document.getElementById('archiveRecPageSizeSelect').value);
    loadArchiveRecords(1);
}
window.changeArchiveRecPageSize = changeArchiveRecPageSize;

function resetArchiveRecordsFilter() {
    const ids = ['archiveRecSearchId', 'archiveRecSearchProduct', 'archiveRecSearchQuestion', 'archiveRecStartTime', 'archiveRecEndTime'];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    const s = document.getElementById('archiveRecSourceSelect');
    if (s) s.value = '';
    loadArchiveRecords(1);
}
window.resetArchiveRecordsFilter = resetArchiveRecordsFilter;

function exportArchiveRecords() {
    if (!archiveCurrentBatchId) return;
    const base = _buildArchiveRecFilterParams();
    const params = new URLSearchParams(base);
    window.location = `${API_BASE}/archives/${archiveCurrentBatchId}/export?${params.toString()}`;
}
window.exportArchiveRecords = exportArchiveRecords;

function openArchiveRecDetails(index) {
    const item = currentArchiveRecords[index];
    _openModDetailsByItem(item);
}
window.openArchiveRecDetails = openArchiveRecDetails;

async function copyArchiveRecRow(index) {
    const item = currentArchiveRecords[index];
    if (!item) return;
    currentModifications = currentArchiveRecords;
    await copyModRow(index);
}
window.copyArchiveRecRow = copyArchiveRecRow;

function updateGovPagination() {
    // Only updates info text as pagination is client-side for now
    // But buttons are handled by changeGovPage
    const prev = document.getElementById('prevGovPageBtn');
    const next = document.getElementById('nextGovPageBtn');
    if (prev) prev.disabled = govCurrentPage <= 1;
    // Calculate total pages
    const totalPages = Math.ceil(govData.length / govPageSize);
    if (next) next.disabled = govCurrentPage >= totalPages;
}

// ==========================================
// KB View Logic
// ==========================================
function formatJsonCell(data) {
    if (data === null || data === undefined || data === '') return '';
    const coerceArrayText = (arr) => {
        const parts = (arr || [])
            .map(x => (x === null || x === undefined) ? '' : String(x).trim())
            .filter(Boolean);
        return parts.join('，');
    };
    const toText = (val) => {
        if (val === null || val === undefined) return '';
        if (Array.isArray(val)) return coerceArrayText(val);
        if (typeof val === 'string') {
            const s = val.trim();
            if (!s || s === '[]' || s === '{}' || s.toLowerCase() === 'null') return '';
            if ((s.startsWith('[') && s.endsWith(']')) || (s.startsWith('{') && s.endsWith('}'))) {
                try {
                    const parsed = JSON.parse(s);
                    if (Array.isArray(parsed)) return coerceArrayText(parsed);
                    if (parsed && typeof parsed === 'object') return JSON.stringify(parsed);
                } catch { }
            }
            return s;
        }
        if (typeof val === 'boolean') return val ? '是' : '否';
        if (typeof val === 'object') {
            try { return JSON.stringify(val); } catch { return String(val); }
        }
        return String(val);
    };
    const text = toText(data);
    if (!text) return '';
    return `<div class="text-truncate" title="${_escapeAttr(text)}">${_escapeHtml(text)}</div>`;
}

function parseSmartListValue(value, options = {}) {
    const splitOnAsciiComma = options.splitOnAsciiComma !== undefined ? !!options.splitOnAsciiComma : true;
    const splitOnChineseCommaWhenUrlList = !!options.splitOnChineseCommaWhenUrlList;
    const isUrlList = !!options.isUrlList;
    
    const toStr = (v) => (v === null || v === undefined) ? '' : String(v);
    
    if (Array.isArray(value)) {
        return value.map(v => toStr(v).trim()).filter(Boolean);
    }
    
    if (typeof value === 'string') {
        const raw = value.trim();
        if (!raw || raw === '[]' || raw === '{}' || raw.toLowerCase() === 'null') return [];
        
        if ((raw.startsWith('[') && raw.endsWith(']')) || (raw.startsWith('{') && raw.endsWith('}'))) {
            try {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed)) return parsed.map(v => toStr(v).trim()).filter(Boolean);
            } catch { }
        }
        
        const hasNewline = /\r?\n/.test(raw);
        if (hasNewline) {
            return raw.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
        }
        
        if (splitOnAsciiComma && raw.includes(',')) {
            return raw.split(',').map(s => s.trim()).filter(Boolean);
        }
        
        if (splitOnChineseCommaWhenUrlList && isUrlList && raw.includes('，')) {
            const roughTokens = raw.split('，').map(s => s.trim()).filter(Boolean);
            const urlLikeCount = roughTokens.filter(t => /^https?:\/\//i.test(t) || /^www\./i.test(t)).length;
            if (urlLikeCount >= 2) return roughTokens;
        }
        
        return [raw];
    }
    
    return [];
}

async function loadKBTable(page = 1) {
    const tableInputs = document.querySelectorAll('input[name="kbTable"]');
    let table = 'knowledge_base_v1';
    tableInputs.forEach(input => { if (input.checked) table = input.value; });

    const id = document.getElementById('idSearch').value.trim();
    const product = document.getElementById('productNameSearch').value.trim();
    const question = document.getElementById('questionSearch').value.trim();
    const similarQuestion = document.getElementById('similarQuestionSearch') ? document.getElementById('similarQuestionSearch').value.trim() : '';
    const answer = document.getElementById('answerSearch').value.trim();
    const url = document.getElementById('urlSearch') ? document.getElementById('urlSearch').value.trim() : '';
    const localDraftFilter = document.getElementById('kbDraftStatusFilter') ? document.getElementById('kbDraftStatusFilter').value : '';
    const selectedTagNames = Array.from(kbSelectedTags).map(t => String(t ?? '').trim()).filter(Boolean);
    const tagMode = document.querySelector('input[name="kbTagFilterMode"]:checked')?.value || 'OR';
    
    const statusChips = document.querySelectorAll('#reviewStatusChips .tag-chip.active');
    const statuses = Array.from(statusChips).map(chip => chip.dataset.value);
    
    const sizeSelect = document.getElementById('kbPageSizeSelect');
    if (sizeSelect) kbPageSize = parseInt(sizeSelect.value);

    const params = new URLSearchParams({
        table: table,
        page: page,
        pageSize: kbPageSize
    });
    if (kbSortBy && kbSortDir) {
        params.append('sortBy', kbSortBy);
        params.append('sortDir', kbSortDir);
    }
    
    if (kbShowSelectedOnly) {
        params.append('ids', Array.from(selectedKBRows).join(','));
    } else {
        params.append('id', id);
        params.append('product', product);
        params.append('question', question);
        params.append('similar_question', similarQuestion);
        params.append('answer', answer);
        params.append('url', url);
    }

    if (selectedTagNames.length) {
        params.append('tagNames', selectedTagNames.join(','));
        params.append('tagMode', tagMode);
    }
    
    if (!kbShowSelectedOnly) {
        if (statuses.length > 0) {
            params.append('review_status', statuses.join(','));
        }
        
        if (kbSelectedProductCategories.size > 0) {
            params.append('product_categories', Array.from(kbSelectedProductCategories).join(','));
        }
    }

    const tbody = document.getElementById('kbTableBody');
    if (!tbody) return;
    
    // 尝试从缓存获取数据
    const cacheKey = getCacheKey(page, params);
    const cachedData = getFromCache(cacheKey);
    
    if (cachedData) {
        console.log(`✓ 使用缓存数据（第 ${page} 页）`);
        // 使用缓存数据，跳过网络请求
        let data = [];
        let debugSimilar = null;
        
        if (cachedData.success && cachedData.data) {
            data = cachedData.data;
            kbTotal = cachedData.total || 0;
            debugSimilar = cachedData.debug_similar || null;
        } else if (Array.isArray(cachedData)) {
            data = cachedData;
            kbTotal = cachedData.length;
        }
        
        // Local-only filter
        if (localDraftFilter) {
            data = data.filter(item => __kbEditMatchLocalDraftFilter(item, localDraftFilter));
            kbTotal = data.length;
        }
        
        currentKBData = data;
        kbCurrentPage = page;
        
        renderKBTable();
        updateKBPagination();
        updateKBPreviewSelectedButton();
        
        // 预加载下一页
        prefetchKBNextPage(page, params);
        
        return;
    }
    
    tbody.innerHTML = '<tr><td colspan="100" class="empty-message">加载中...</td></tr>';

    try {
        const res = await api(`/kb/data?${params.toString()}`);
        
        if (res.error) {
             tbody.innerHTML = `<tr><td colspan="100" class="error-message">加载失败: ${res.error}</td></tr>`;
             return;
        }
        
        let data = [];
        let debugSimilar = null;
        if (res.success && res.data) {
            data = res.data;
            kbTotal = res.total || 0;
            debugSimilar = res.debug_similar || null;
        } else if (Array.isArray(res)) {
            data = res;
            kbTotal = res.length;
        } else {
             data = [];
             kbTotal = 0;
        }

        // Local-only filter: draft status is stored in browser localStorage.
        if (localDraftFilter) {
            data = data.filter(item => __kbEditMatchLocalDraftFilter(item, localDraftFilter));
            kbTotal = data.length;
        }

        // If similar-question search returns empty, do not show debug alerts in production
        /* 
        try {
            if (similarQuestion && (!data || data.length === 0)) {
                const dbg = debugSimilar;
                if (dbg && (dbg.pre_count !== undefined || dbg.post_count !== undefined || dbg.sample_rows)) {
                    const msg =
                        `相似问搜索无结果（调试信息）\n` +
                        `raw: ${dbg.raw ?? ''}\n` +
                        `norm: ${dbg.norm ?? ''}\n` +
                        `tokens: ${(dbg.tokens || []).join(',')}\n` +
                        `pre_count: ${dbg.pre_count ?? ''}\n` +
                        `post_count: ${dbg.post_count ?? ''}\n` +
                        `sample_rows: ${JSON.stringify(dbg.sample_rows || [], null, 2)}`;
                    alert(msg);
                } else {
                    const meta = (res && typeof res === 'object' && res.__meta) ? res.__meta : null;
                    const status = meta ? meta.status : '';
                    const url = meta ? meta.url : '';
                    const msg = (res && typeof res === 'object' && (res.message || res.error)) ? (res.message || res.error) : '';
                    const kind = Array.isArray(res) ? `array(len=${res.length})` : (res && typeof res === 'object' ? 'object' : typeof res);
                    alert(
                        '相似问搜索无结果：后端未返回 debug_similar。\n' +
                        `response_type: ${kind}\n` +
                        (status ? `HTTP: ${status}\n` : '') +
                        (url ? `URL: ${url}\n` : '') +
                        (msg ? `message: ${msg}\n` : '') +
                        '（若 HTTP=401 请重新登录；若仍是 200 则说明后端未走 similar_question 分支）'
                    );
                }
            }
        } catch (e) {
            // ignore UI debug failures
        }
        */
        
        currentKBData = data;
        kbCurrentPage = page;
        
        renderKBTable();
        updateKBPagination();
        updateKBPreviewSelectedButton();
        
        // 保存到缓存
        saveToCache(cacheKey, res);
        
        // 预加载下一页
        prefetchKBNextPage(page, params);
        
    } catch (e) {
        console.error("Load KB failed", e);
        tbody.innerHTML = `<tr><td colspan="100" class="error-message">请求失败: ${e.message}</td></tr>`;
    }
}

function renderKBTableHeader(force = false) {
    const thead = document.querySelector('#kbTable thead tr');
    if (!thead) return;

    const signature = JSON.stringify(
        kbColumns
            .filter(col => col.visible !== false)
            .map(col => ({
                key: col.key,
                width: col.width || '',
                sortable: Boolean(col.sortable),
                sortActive: kbSortBy === col.field ? (kbSortDir || '') : ''
            }))
    );

    if (!force && signature === kbHeaderSignature) return;
    kbHeaderSignature = signature;
    kbResizersBound = false;
    thead.innerHTML = '';
    
    kbColumns.forEach((col, index) => {
        if (col.visible === false) return;
        const th = document.createElement('th');
        th.innerText = col.title;
        if (col.width) th.style.width = col.width;
        
        // Sticky Columns Logic (Removed)
        // if (col.fixed === 'left') { ... }

        if (col.key === 'checkbox') {
             th.innerHTML = '<input type="checkbox" id="kbSelectAll" onclick="toggleKBSelectAll()" title="全选/取消全选">';
             th.classList.add('col-checkbox');
        } else {
             if (col.sortable) {
                 th.title = '点击排序';
                 th.onclick = () => handleKBSort(col.field);
                 th.style.cursor = 'pointer';

                 const wrap = document.createElement('div');
                 wrap.className = 'kb-sort-header';
                 const label = document.createElement('span');
                 label.textContent = col.title;
                 const icon = document.createElement('i');
                 const isActive = kbSortBy === col.field && (kbSortDir === 'asc' || kbSortDir === 'desc');
                 if (isActive) {
                     icon.className = kbSortDir === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down';
                     icon.style.opacity = '0.95';
                 } else {
                     icon.className = 'fas fa-sort';
                     icon.style.opacity = '0.35';
                 }
                 wrap.appendChild(label);
                 wrap.appendChild(icon);
                 th.innerHTML = '';
                 th.appendChild(wrap);
             }
        }
        thead.appendChild(th);
    });
}

function renderKBTable() {
    renderKBTableHeader();

    const tbody = document.getElementById('kbTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    if (!currentKBData || currentKBData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="100" class="empty-message">暂无数据</td></tr>';
        return;
    }

    const visibleColumns = kbColumns.filter(col => col.visible !== false);
    const fragment = document.createDocumentFragment();
    
    currentKBData.forEach((item, rowIndex) => {
        const tr = document.createElement('tr');
        const id = item.question_wiki_id || item.id;
        
        visibleColumns.forEach((col, index) => {
            const td = document.createElement('td');
            
            // Sticky Columns Logic (Removed)
            // if (col.fixed === 'left') { ... }
            
            if (col.key === 'checkbox') {
                const isSelected = selectedKBRows.has(id);
                td.style.textAlign = "center";
                td.innerHTML = `<input type="checkbox" class="kb-row-check" value="${id}" ${isSelected ? 'checked' : ''} onchange="toggleKBRow('${id}')">`;
            } else if (col.key === 'status') {
                const status = item.review_status || 'unadjusted';
                let statusBadge = '';
                let statusText = '未调整';
                if (status === 'creating') statusBadge = '<span class="badge badge-info">新增中</span>';
                else if (status === 'modifying') statusBadge = '<span class="badge badge-warning">修改中</span>';
                else if (status === 'deleting') statusBadge = '<span class="badge badge-danger">删除中</span>';
                else statusBadge = '<span class="badge badge-success">未调整</span>';
                if (status === 'creating') statusText = '新增中';
                else if (status === 'modifying') statusText = '修改中';
                else if (status === 'deleting') statusText = '删除中';
                td.innerHTML = statusBadge;
                kbPrepareCompactCell(td, col, statusText);
            } else if (col.key === 'id') {
                 const rawId = item.question_wiki_id || item.id || '';
                 const ids = rawId.split(/[,，]/).map(s => s.trim()).filter(s => s);
                 
                const idHtml = ids.map(oneId => 
                    `<div class="clickable-id-row"><span class="clickable-id" onclick="searchKBById('${oneId}')" title="点击搜索此ID">${oneId}</span></div>`
                 ).join('');

                 td.innerHTML = `
                    <div class="kb-id-cell-wrap">
                        <div class="kb-id-cell-list">${idHtml}</div>
                        <div class="kb-cell-actions-inline">
                            <button type="button" class="kb-mini-action-btn kb-mini-action-btn-icon" onclick="copyToClipboard('${rawId}')" title="复制ID"><i class="fas fa-copy"></i></button>
                            <button type="button" class="kb-mini-action-btn kb-mini-action-btn-edit kb-mini-action-btn-icon" onclick="openKBEditModal('${rawId}')" title="编辑"><i class="fas fa-edit"></i></button>
                        </div>
                    </div>
                 `;
            } else if (col.key === 'image_urls' || col.key === 'video_urls' || col.key === 'file_urls') {
                let val = item[col.field];
                let urls = [];
                try {
                    urls = typeof val === 'string' ? JSON.parse(val) : val;
                } catch {}
                if (!Array.isArray(urls)) {
                    urls = parseSmartListValue(val, { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true });
                }
                const html = urls.map(u => {
                    if (!u) return '';
                    const cleanUrl = String(u).replace(/[\[\]"']/g, '').trim();
                    if (!cleanUrl) return '';
                    let href = cleanUrl;
                    if (!href.match(/^https?:\/\//i)) href = 'http://' + href;
                    return `
                    <div class="kb-url-row">
                        <button type="button" class="kb-mini-action-btn kb-mini-action-btn-icon" onclick="copyToClipboard('${cleanUrl}')" title="复制链接"><i class="fas fa-copy"></i></button>
                        <a href="javascript:void(0)" onclick="searchKBByUrl('${cleanUrl}')" title="点击搜索: ${cleanUrl}" class="kb-url-link">${cleanUrl}</a>
                        <a href="${href}" target="_blank" title="在新标签页打开" class="kb-url-open-btn kb-mini-action-btn-icon"><i class="fas fa-external-link-alt"></i></a>
                    </div>`;
                }).join('');
                td.innerHTML = html || '<span class="cell-empty">-</span>';
                kbPrepareCompactCell(td, col, urls.join('\n'), { modalAllowed: false });
            } else if (col.key === 'link_url') {
                const val = String(item[col.field] ?? '').trim();
                if (!val) {
                    td.innerHTML = '<span class="cell-empty">-</span>';
                    kbPrepareCompactCell(td, col, '-', { modalAllowed: false });
                } else {
                    const links = parseSmartListValue(val, { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true });
                    const html = links.map(u => {
                        if (!u) return '';
                        const cleanUrl = String(u).replace(/[\[\]"']/g, '').trim();
                        if (!cleanUrl) return '';
                        let href = cleanUrl;
                        if (!href.match(/^https?:\/\//i)) href = 'http://' + href;
                        return `
                        <div class="kb-url-row">
                            <button type="button" class="kb-mini-action-btn kb-mini-action-btn-icon" onclick="copyToClipboard('${cleanUrl}')" title="复制链接"><i class="fas fa-copy"></i></button>
                            <a href="javascript:void(0)" onclick="searchKBByUrl('${cleanUrl}')" title="点击搜索: ${cleanUrl}" class="kb-url-link">${cleanUrl}</a>
                            <a href="${href}" target="_blank" title="在新标签页打开" class="kb-url-open-btn kb-mini-action-btn-icon"><i class="fas fa-external-link-alt"></i></a>
                        </div>`;
                    }).join('');
                    td.innerHTML = html || '<span class="cell-empty">-</span>';
                    kbPrepareCompactCell(td, col, links.join('\n'), { modalAllowed: false });
                }
            } else if (col.key === 'bm25') {
                let val = item[col.field];
                let display = '否';
                if (val === true || val === 'true' || val === '1' || val === 1 || String(val).toLowerCase() === 'true') {
                    display = '是';
                }
                td.innerHTML = kbRenderCompactText(display);
                kbPrepareCompactCell(td, col, display);
            } else if (col.key === 'question' || col.key === 'answer' || col.key === 'question_type') {
                const val = item[col.field] ?? '';
                const display = val || '-';
                td.innerHTML = kbRenderCompactText(display);
                kbPrepareCompactCell(td, col, display);
            } else if (col.key === 'product_name' || col.key === 'product_category') {
                const rawVal = item[col.field] ?? '';
                let display = '';
                if (Array.isArray(rawVal)) {
                    display = rawVal.map(v => String(v ?? '').trim()).filter(Boolean).join('\n');
                } else {
                    const s = String(rawVal ?? '').trim();
                    if (s) {
                        const parts = s.split(/[,，、]\s*/).map(x => x.trim()).filter(Boolean);
                        display = parts.length > 1 ? parts.join('\n') : s;
                    }
                }
                if (!display) display = '-';
                td.innerHTML = kbRenderCompactText(display);
                kbPrepareCompactCell(td, col, display);
            } else if (col.key === 'similar_questions' || col.key === 'keyword_list') {
                const val = item[col.field];
                const items = (col.key === 'similar_questions')
                    ? parseSmartListValue(val, { splitOnAsciiComma: true })
                    : parseSmartListValue(val, { splitOnAsciiComma: true });
                const display = items.length ? items.join('\n') : '-';
                td.innerHTML = kbRenderCompactText(display);
                kbPrepareCompactCell(td, col, display);
            } else if (col.key === 'kb_tags') {
                // Tag values may be delivered as an array or a stringified list (e.g. "['a','b']" / "[]"/"a,b")
                const rawVal = item[col.field];
                let tags = [];
                if (Array.isArray(rawVal)) {
                    tags = rawVal;
                } else if (typeof rawVal === 'string') {
                    tags = parseSmartListValue(rawVal, { splitOnAsciiComma: true });
                }
                tags = (tags || [])
                    .map(t => String(t ?? '').trim())
                    .filter(Boolean);

                if (!tags.length) {
                    td.innerHTML = '<span class="cell-empty">-</span>';
                    kbPrepareCompactCell(td, col, '-');
                } else {
                    const maxShow = 4;
                    const shown = tags.slice(0, maxShow);
                    const rest = tags.length - shown.length;
                    const shownHtml = shown.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');
                    const restHtml = rest > 0 ? `<span class="tag" title="更多标签">+${rest}</span>` : '';
                    td.innerHTML = `<div class="tags-cell">${shownHtml}${restHtml}</div>`;
                    kbPrepareCompactCell(td, col, tags.join('\n'));
                }
            } else {
                let val = item[col.field];
                // Check for null, undefined, or empty string (but allow 0)
                if (val === null || val === undefined || val === '') {
                     td.innerHTML = '<span class="cell-empty">-</span>';
                     kbPrepareCompactCell(td, col, '-');
                } else {
                    if (col.type === 'json') {
                        td.innerHTML = formatJsonCell(val);
                        kbPrepareCompactCell(td, col, typeof val === 'string' ? val : JSON.stringify(val, null, 2));
                    } else if (col.key === 'update_time') {
                        const display = val ? new Date(val).toLocaleString() : '-';
                        td.innerHTML = kbRenderCompactText(display);
                        kbPrepareCompactCell(td, col, display);
                    } else {
                        td.innerHTML = kbRenderCompactText(val);
                        if (col.className) td.className = col.className;
                        kbPrepareCompactCell(td, col, val);
                    }
                }
            }
            if (col.className) {
                String(col.className || '').split(/\s+/).filter(Boolean).forEach(cn => td.classList.add(cn));
            }
            tr.appendChild(td);
        });
        
        fragment.appendChild(tr);
    });
    
    tbody.appendChild(fragment);
    kbApplyStableTableWidth();
    kbBindCompactTableInteractions();
    kbRefreshCompactOverflow(document.getElementById('kbTable') || document);
    if (!kbResizersBound) {
        makeTableResizable('kbTable');
        kbResizersBound = true;
    }
    // updateStickyColumns();
}

function updateKBPagination() {
    const info = document.getElementById('kbPageInfo');
    const prev = document.getElementById('prevKBPageBtn');
    const next = document.getElementById('nextKBPageBtn');
    
    if (info) info.innerText = `共 ${kbTotal} 条`;
    if (prev) prev.disabled = kbCurrentPage <= 1;
    if (next) next.disabled = kbCurrentPage * kbPageSize >= kbTotal;
}

function changeKBPage(offset) {
    loadKBTable(kbCurrentPage + offset);
}

function handleKBSort(field) {
    if (kbSortBy === field) {
        if (kbSortDir === 'asc') {
            kbSortDir = 'desc';
        } else if (kbSortDir === 'desc') {
            kbSortBy = null;
            kbSortDir = null;
        } else {
            kbSortDir = 'asc';
        }
    } else {
        kbSortBy = field;
        kbSortDir = 'asc';
    }
    kbHeaderSignature = '';
    clearKBCache(); // 排序改变时清除缓存
    loadKBTable(1);
}

function toggleKBRow(id) {
    if (selectedKBRows.has(id)) {
        selectedKBRows.delete(id);
    } else {
        selectedKBRows.add(id);
    }
    updateKBPreviewSelectedButton();
    if (kbShowSelectedOnly) {
        if (selectedKBRows.size === 0) kbShowSelectedOnly = false;
        loadKBTable(1);
    }
}

function toggleKBSelectAll() {
    const selectAll = document.getElementById('kbSelectAll');
    const checked = selectAll.checked;
    const checkboxes = document.querySelectorAll('.kb-row-check');
    
    checkboxes.forEach(cb => {
        cb.checked = checked;
        if (checked) selectedKBRows.add(cb.value);
        else selectedKBRows.delete(cb.value);
    });
    updateKBPreviewSelectedButton();
    if (kbShowSelectedOnly) {
        if (selectedKBRows.size === 0) kbShowSelectedOnly = false;
        loadKBTable(1);
    }
}

// 创建防抖版本的搜索函数
const debouncedLoadKBTable = debounce((page = 1) => {
    loadKBTable(page);
}, 500); // 500ms延迟

function searchKB() {
    clearKBCache(); // 搜索时清除缓存
    loadKBTable(1);
}

// 用于输入框实时搜索的防抖版本
function searchKBDebounced() {
    debouncedLoadKBTable(1);
}

function __kbEditGetLocalDraftStatusForItem(item) {
    try {
        const id = String(item?.question_wiki_id || item?.id || '').trim();
        if (!id) return 'no_draft';
        const raw = localStorage.getItem(__kbEditDraftKey(id));
        if (!raw) return 'no_draft';
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object') return 'no_draft';
        if (parsed.status === 'pending_sync') return 'pending_sync';
        if (parsed.digest && typeof parsed.digest === 'object') return 'has_draft';
        return 'no_draft';
    } catch {
        return 'no_draft';
    }
}

function __kbEditMatchLocalDraftFilter(item, filter) {
    const st = __kbEditGetLocalDraftStatusForItem(item);
    if (filter === 'has_draft') return st === 'has_draft' || st === 'pending_sync';
    if (filter === 'pending_sync') return st === 'pending_sync';
    if (filter === 'no_draft') return st === 'no_draft';
    return true;
}

async function loadKBProductCategoryChips() {
    const container = document.getElementById('kbProductCategoryChips');
    if (!container) return;
    try {
        const res = await api('/kb/product_catalog');
        let catalog = res || {};
        if (res && typeof res === 'object' && res.data) catalog = res.data;
        if (!catalog || typeof catalog !== 'object' || Array.isArray(catalog)) catalog = {};
        const categories = Object.keys(catalog).map(x => String(x || '').trim()).filter(Boolean).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'));
        renderKBProductCategoryChips(categories);
    } catch (e) {
        renderKBProductCategoryChips([]);
    }
}

function renderKBProductCategoryChips(categories) {
    const container = document.getElementById('kbProductCategoryChips');
    if (!container) return;
    container.innerHTML = '';
    const values = Array.isArray(categories) ? categories : [];
    const makeChip = (label, value) => {
        const chip = document.createElement('div');
        chip.className = 'tag-chip';
        chip.dataset.value = value;
        chip.innerText = label;
        chip.onclick = () => toggleKBProductCategoryChip(value);
        return chip;
    };
    container.appendChild(makeChip('全部', ''));
    values.forEach(v => container.appendChild(makeChip(v, v)));
    syncKBProductCategoryChipActive();
}

function toggleKBProductCategoryChip(value) {
    const v = String(value || '').trim();
    if (!v) {
        kbSelectedProductCategories.clear();
    } else {
        if (kbSelectedProductCategories.has(v)) kbSelectedProductCategories.delete(v);
        else kbSelectedProductCategories.add(v);
    }
    syncKBProductCategoryChipActive();
    loadKBTable(1);
}

function syncKBProductCategoryChipActive() {
    const container = document.getElementById('kbProductCategoryChips');
    if (!container) return;
    const empty = kbSelectedProductCategories.size === 0;
    container.querySelectorAll('.tag-chip').forEach(chip => {
        const v = String(chip.dataset.value || '');
        if (!v) chip.classList.toggle('active', empty);
        else chip.classList.toggle('active', kbSelectedProductCategories.has(v));
    });
}

function resetKBSearch() {
    document.getElementById('idSearch').value = '';
    document.getElementById('productNameSearch').value = '';
    document.getElementById('questionSearch').value = '';
    if (document.getElementById('similarQuestionSearch')) document.getElementById('similarQuestionSearch').value = '';
    document.getElementById('answerSearch').value = '';
    if(document.getElementById('urlSearch')) document.getElementById('urlSearch').value = '';
    if (document.getElementById('kbDraftStatusFilter')) document.getElementById('kbDraftStatusFilter').value = '';
    syncKBDraftStatusChips();
    kbSelectedTags.clear();
    updateKbTagFilterButton();
    // Default tag filter mode OR
    const orCb = document.querySelector('input[name="kbTagFilterMode"][value="OR"]');
    if (orCb) orCb.checked = true;
    document.querySelectorAll('#reviewStatusChips .tag-chip').forEach(c => c.classList.remove('active'));
    kbShowSelectedOnly = false;
    selectedKBRows.clear();
    const selectAll = document.getElementById('kbSelectAll');
    if (selectAll) {
        selectAll.checked = false;
        selectAll.indeterminate = false;
    }
    document.querySelectorAll('.kb-row-check').forEach(cb => { cb.checked = false; });
    kbSelectedProductCategories.clear();
    syncKBProductCategoryChipActive();
    updateKBPreviewSelectedButton();
    clearKBCache(); // 重置搜索时清除缓存
    loadKBTable(1);
}

function toggleStatusFilter(chip) {
    chip.classList.toggle('active');
    clearKBCache(); // 状态筛选改变时清除缓存
    loadKBTable(1);
}

// Make toggleStatusFilter global
window.toggleStatusFilter = toggleStatusFilter;

function setKBDraftStatusFilter(chip) {
    const input = document.getElementById('kbDraftStatusFilter');
    if (!input || !chip) return;
    input.value = String(chip.dataset.value || '');
    syncKBDraftStatusChips();
    clearKBCache();
    loadKBTable(1);
}

function syncKBDraftStatusChips() {
    const input = document.getElementById('kbDraftStatusFilter');
    const current = input ? String(input.value || '') : '';
    document.querySelectorAll('#kbDraftStatusChips .tag-chip').forEach(chip => {
        chip.classList.toggle('active', String(chip.dataset.value || '') === current);
    });
}

window.setKBDraftStatusFilter = setKBDraftStatusFilter;

function changeKBPageSize() {
    clearKBCache(); // 页面大小改变时清除缓存
    loadKBTable(1);
}

// KB Import/Export/Sync
async function importKB() {
  const fileInput = document.getElementById('importFileKB');
  const btn = document.getElementById('importBtn');
  const status = document.getElementById('importStatus');
  const mode = document.querySelector('input[name="importMode"]:checked')?.value || 'upsert';
  const deleteMissing = mode !== 'overwrite' && Boolean(document.getElementById('deleteMissingIds')?.checked);
  
  if (!fileInput.files[0]) {
    alert('请选择文件');
    return;
  }

  let overwritePreview = null;
  let deleteMissingPreview = null;
  if (mode === 'overwrite') {
    try {
      if (status) status.textContent = '正在生成全量覆盖预览...';
      const previewForm = new FormData();
      previewForm.append('file', fileInput.files[0]);
      const previewRes = await fetch(API_BASE + '/kb/import/preview', {
        method: 'POST',
        body: previewForm,
        credentials: 'same-origin'
      });
      const previewData = await previewRes.json();
      if (!previewData || !previewData.success) {
        throw new Error(previewData?.message || '生成导入预览失败');
      }
      overwritePreview = previewData.preview || {};
      if ((overwritePreview.invalid_model_count || 0) > 0) {
        const first = (overwritePreview.invalid_rows || []).slice(0, 5).map(r => `第 ${r.row} 行: ${(r.invalid_models || []).join(', ')}`).join('\n');
        alert(`导入文件存在未知型号 ${overwritePreview.invalid_model_count} 行，请修正后再覆盖。\n${first}`);
        if (status) status.textContent = '预览失败：存在未知型号';
        return;
      }
    } catch (e) {
      if (status) status.textContent = '预览失败: ' + e.message;
      alert('导入预览失败: ' + e.message);
      return;
    }

    const ok = await showDangerConfirmModal(
      '全量覆盖确认',
      `你选择了全量覆盖：将导入 ${overwritePreview.incoming_count || 0} 条记录，当前 V1 有 ${overwritePreview.current_v1_count || 0} 条，评分缓存有 ${overwritePreview.score_count || 0} 条。\n系统会先同步 V1 到 V1T-1，并备份评分缓存；若导入失败会尝试自动恢复。确认继续？`,
      '确认全量覆盖'
    );
    if (!ok) return;
  }

  if (deleteMissing) {
    try {
      if (status) status.textContent = '正在生成缺失 ID 删除预览...';
      const previewForm = new FormData();
      previewForm.append('file', fileInput.files[0]);
      previewForm.append('delete_missing', 'true');
      const previewRes = await fetch(API_BASE + '/kb/import/preview', {
        method: 'POST',
        body: previewForm,
        credentials: 'same-origin'
      });
      const previewData = await previewRes.json();
      if (!previewData || !previewData.success) {
        throw new Error(previewData?.message || '生成缺失 ID 删除预览失败');
      }
      deleteMissingPreview = previewData.preview || {};
      if (deleteMissingPreview.delete_missing_blocked) {
        alert('启用“同步删除缺失 ID”时，导入文件必须包含至少一个有效 ID。');
        if (status) status.textContent = '预览失败：文件缺少有效 ID';
        return;
      }
      if ((deleteMissingPreview.invalid_model_count || 0) > 0) {
        const first = (deleteMissingPreview.invalid_rows || []).slice(0, 5).map(r => `第 ${r.row} 行: ${(r.invalid_models || []).join(', ')}`).join('\n');
        alert(`导入文件存在未知型号 ${deleteMissingPreview.invalid_model_count} 行，请修正后再导入。\n${first}`);
        if (status) status.textContent = '预览失败：存在未知型号';
        return;
      }
    } catch (e) {
      if (status) status.textContent = '预览失败: ' + e.message;
      alert('缺失 ID 删除预览失败: ' + e.message);
      return;
    }

    const deleteCount = deleteMissingPreview.delete_missing_count || 0;
    if (deleteCount > 0) {
      const sample = (deleteMissingPreview.delete_missing_sample_ids || []).slice(0, 10).join(', ');
      const sampleText = sample ? `\n示例 ID：${sample}` : '';
      const ok = await showDangerConfirmModal(
        '同步删除缺失 ID 确认',
        `当前 V1 中有 ${deleteCount} 条记录未出现在导入文件 ID 列中。导入成功后，这些记录会从 V1 直接物理删除。${sampleText}\n确认继续？`,
        '确认物理删除'
      );
      if (!ok) return;
    }
  }
  
  btn.disabled = true;
  status.textContent = '正在上传并导入...';
  
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('mode', mode);
  if (deleteMissing) {
    formData.append('delete_missing', 'true');
    formData.append('confirm_delete_missing', 'true');
    if (deleteMissingPreview && deleteMissingPreview.delete_missing_count !== undefined) {
      formData.append('expected_delete_missing_count', String(deleteMissingPreview.delete_missing_count));
    }
  }
  if (mode === 'overwrite') {
    formData.append('confirm_overwrite', 'true');
    if (overwritePreview && overwritePreview.incoming_count !== undefined) {
      formData.append('expected_incoming_count', String(overwritePreview.incoming_count));
    }
  }
  
  try {
    const res = await fetch(API_BASE + '/kb/import', {
      method: 'POST',
      body: formData
    });
    
    if (res.status === 401) {
       showLogin(true);
       throw new Error('Unauthorized');
    }
    
    const data = await res.json();
    if (data.success) {
      status.textContent = `✅ 成功导入 ${data.count} 条数据`;
      let msg = `导入成功！共插入 ${data.count} 条记录。`;
      if (data.pre_sync_v1_to_t1) {
        msg += `\n\n（全量覆盖前置备份）${data.pre_sync_v1_to_t1}`;
      }
      if (data.delete_missing) {
        msg += `\n\n同步删除缺失 ID：已从 V1 物理删除 ${data.delete_missing.count || 0} 条。`;
        const cleanupWarnings = Array.isArray(data.delete_missing.warnings) ? data.delete_missing.warnings.filter(Boolean) : [];
        if (cleanupWarnings.length > 0) {
          msg += `\n关联清理提醒：${cleanupWarnings.slice(0, 3).join('；')}`;
        }
      }
      alert(msg);
      loadKBTable(1);
    } else {
      throw new Error(data.message || 'Unknown error');
    }
  } catch (e) {
    status.textContent = '❌ 失败: ' + e.message;
    alert('导入失败: ' + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function syncKB() {
  if (!await showDangerConfirmModal('同步确认', '此操作将清空 V1T-1 并用 V1 全量覆盖。确认继续？', '确认同步')) return;
  
  const btn = document.getElementById('syncBtn');
  const status = document.getElementById('syncStatus');
  
  if (btn) btn.disabled = true;
  if (status) status.textContent = '正在同步...';
  
  try {
    const data = await api('/kb/sync', 'POST');
    if (data.success) {
      if (status) status.textContent = '✅ 同步完成';
      alert('同步操作成功完成！');
      loadKBTable(1);
    } else {
      throw new Error(data.message);
    }
  } catch (e) {
    if (status) status.textContent = '❌ 同步失败';
    alert('同步失败: ' + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/**
 * 将当前 V1 一键同步到：机型矩阵(merge)、多媒体 link_previews、评分 kb_scores。
 * 治理月度召回仍须在治理 Tab 导入；评分同步后治理页可关联最新快照。
 */
async function syncDownstreamFromV1() {
  if (!await showDangerConfirmModal(
    '一键同步下游确认',
    '将顺序执行机型矩阵、多媒体链接与评分表同步；治理月度召回仍需在治理页导入。确认继续？',
    '确认一键同步'
  )) return;

  const btn = document.getElementById('syncDownstreamBtn');
  const st = document.getElementById('syncDownstreamStatus');
  if (btn) btn.disabled = true;
  if (st) st.textContent = '同步中（可能较久，请稍候）…';

  try {
    const res = await api('/kb/sync_downstream', 'POST');
    if (res.success) {
      const s = res.steps || {};
      const m = s.matrix || {};
      const l = s.links || {};
      const sc = s.scoring || {};
      const gov = (s.governance && s.governance.note) ? `\n\n治理：${s.governance.note}` : '';
      alert(
        `一键同步完成。\n\n矩阵：新增 ${m.added ?? 0}，更新 ${m.updated ?? 0}，删除 ${m.deleted ?? 0}\n` +
        `多媒体：新增 ${l.count ?? 0}，更新 ${l.updated ?? 0}，解除关联 ${l.unlinked ?? 0}，扫描到链接 ${l.total_found ?? 0}\n` +
        `评分：${sc.message || (JSON.stringify(sc))}` +
        gov
      );
      if (st) st.textContent = '✅ 已完成';
    } else {
      throw new Error(res.message || '失败');
    }
  } catch (e) {
    if (st) st.textContent = '❌ ' + (e.message || e);
    alert('一键同步失败: ' + (e.message || e));
  } finally {
    if (btn) btn.disabled = false;
  }
}
window.syncDownstreamFromV1 = syncDownstreamFromV1;

async function previewCheckDuplicates() {
    const fileInput = document.getElementById('importFileKB');
    if (!fileInput || !fileInput.files[0]) {
        alert('请先选择一个 Excel 文件');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    const mode = document.querySelector('input[name="importMode"]:checked')?.value || 'upsert';
    const deleteMissing = mode !== 'overwrite' && Boolean(document.getElementById('deleteMissingIds')?.checked);
    if (deleteMissing) formData.append('delete_missing', 'true');
    
    // Add button loading state
    const btn = document.querySelector('button[onclick="previewCheckDuplicates()"]');
    const originalText = btn ? btn.innerText : '🔍 查重预览';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '正在查重...';
    }
    
    try {
        const res = await fetch(API_BASE + '/kb/check_duplicates', {
             method: 'POST',
             body: formData
        });
        const data = await res.json();
        
        if (data.success) {
            const errorCount = data.error_count || 0;
            const errorMsg = errorCount > 0 ? `\n异常记录: ${errorCount} (包含未知型号)` : '';
            const deleteMissingCount = data.delete_missing_count || 0;
            const deleteMissingMsg = deleteMissing ? `\n将物理删除: ${deleteMissingCount}` : '';
            alert(`查重完成。\n重复记录: ${data.duplicates_count || 0}\n新增记录: ${data.new_count || 0}${errorMsg}${deleteMissingMsg}`);
            
            const checkResultDiv = document.getElementById('checkResult');
            if (checkResultDiv && data.report) {
                const errors = data.report.filter(item => item.status === '异常');
                const sections = [];
                if (errors.length > 0) {
                    let html = `<div style="color: #dc3545; margin-bottom: 5px;"><b>发现 ${errors.length} 条异常记录 (未计入新增):</b></div>`;
                    html += '<ul style="padding-left: 20px; margin: 0; color: #666;">';
                    errors.slice(0, 50).forEach(err => {
                        html += `<li><b>${escapeHtml(err.id)}</b>: ${escapeHtml(err.details)}</li>`;
                    });
                    if (errors.length > 50) {
                        html += `<li>...以及其他 ${errors.length - 50} 条记录</li>`;
                    }
                    html += '</ul>';
                    sections.push(html);
                }
                if (deleteMissing && data.delete_missing_blocked) {
                    sections.push('<div style="color: #dc3545;"><b>同步删除缺失 ID 不可执行：</b>未提取到有效 ID。</div>');
                } else if (deleteMissing && deleteMissingCount > 0) {
                    const sampleIds = data.delete_missing_sample_ids || [];
                    let html = `<div style="color: #b45309; margin-bottom: 5px;"><b>将从 V1 物理删除 ${deleteMissingCount} 条缺失 ID:</b></div>`;
                    html += '<ul style="padding-left: 20px; margin: 0; color: #666;">';
                    sampleIds.forEach(id => {
                        html += `<li><b>${escapeHtml(id)}</b></li>`;
                    });
                    if (deleteMissingCount > sampleIds.length) {
                        html += `<li>...以及其他 ${deleteMissingCount - sampleIds.length} 条记录</li>`;
                    }
                    html += '</ul>';
                    sections.push(html);
                }
                if (sections.length > 0) {
                    checkResultDiv.classList.remove('d-none');
                    checkResultDiv.innerHTML = sections.join('<hr style="border: none; border-top: 1px solid #e5e7eb; margin: 10px 0;">');
                } else {
                    checkResultDiv.classList.add('d-none');
                    checkResultDiv.innerHTML = '';
                }
            }
        } else {
            alert('查重失败: ' + data.message);
        }
    } catch (e) {
        alert('查重请求异常: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = originalText;
        }
    }
}

function downloadTemplate() {
    // Use a hidden link to trigger download, which is more robust than window.location.href
    // and handles browser behavior better
    const link = document.createElement('a');
    link.href = API_BASE + '/kb/template';
    link.setAttribute('download', 'knowledge_base_template.xlsx');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function showRevisionModal() {
    const modal = document.getElementById('revisionConfirmModal');
    if (modal) modal.style.display = 'block';
}

function closeRevisionModal() {
    const modal = document.getElementById('revisionConfirmModal');
    if (modal) modal.style.display = 'none';
}

async function executeRevisionCompletion() {
    closeRevisionModal();
    
    try {
        const res = await api('/kb/complete_revision', 'POST');
        if (res.success) {
            alert('修订已完成！状态已重置。');
            loadKBTable(1);
        } else {
            alert('操作失败: ' + res.message);
        }
    } catch (e) {
        alert('请求失败: ' + e.message);
    }
}

// Make functions global
window.showRevisionModal = showRevisionModal;
window.closeRevisionModal = closeRevisionModal;
window.executeRevisionCompletion = executeRevisionCompletion;
window.closeDangerConfirmModal = closeDangerConfirmModal;

// Deprecated old function
async function completeRevision(event) {
    console.warn('completeRevision is deprecated. Use showRevisionModal instead.');
    showRevisionModal();
}
window.completeRevision = completeRevision;

async function deleteSelectedKBItems() {
    if (selectedKBRows.size === 0) {
        alert('请先选择要删除的条目');
        return;
    }
    if (!await showDangerConfirmModal(
        '批量删除确认',
        `将把选中的 ${selectedKBRows.size} 条记录标记为“删除中”。确认继续？`,
        '确认删除'
    )) return;
    
    try {
        const res = await api('/kb/delete', 'POST', { ids: Array.from(selectedKBRows) });
        if (res.success) {
            alert('删除操作成功');
            selectedKBRows.clear();
            // 删除后强制清缓存并刷新，避免继续显示旧状态。
            clearKBCache();
            await loadKBTable(kbCurrentPage || 1);
        } else {
            alert('删除失败: ' + res.message);
        }
    } catch (e) {
        alert('删除请求异常: ' + e.message);
    }
}

// Make deleteSelectedKBItems global
window.deleteSelectedKBItems = deleteSelectedKBItems;

let __manualHtmlCache = '';
let __manualLoadPromise = null;

function renderManualInline(text) {
    let html = escapeHtml(text || '');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    return html;
}

function isManualTableSeparator(line) {
    return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(String(line || '').trim());
}

function splitManualTableRow(line) {
    return String(line || '')
        .trim()
        .replace(/^\|/, '')
        .replace(/\|$/, '')
        .split('|')
        .map(cell => cell.trim());
}

function renderManualTable(rows) {
    if (!rows || rows.length < 2) return '';
    const header = splitManualTableRow(rows[0]);
    const bodyRows = rows.slice(2).map(splitManualTableRow);
    return `
        <div class="manual-table-wrap">
            <table class="manual-table">
                <thead><tr>${header.map(cell => `<th>${renderManualInline(cell)}</th>`).join('')}</tr></thead>
                <tbody>
                    ${bodyRows.map(row => `<tr>${row.map(cell => `<td>${renderManualInline(cell)}</td>`).join('')}</tr>`).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function renderProductManualMarkdown(markdownText) {
    const lines = String(markdownText || '').replace(/\r\n/g, '\n').split('\n');
    const out = [];
    let listType = '';
    let inCodeBlock = false;
    let codeLines = [];

    const closeList = () => {
        if (listType) {
            out.push(`</${listType}>`);
            listType = '';
        }
    };

    const openList = (type) => {
        if (listType !== type) {
            closeList();
            out.push(`<${type}>`);
            listType = type;
        }
    };

    for (let i = 0; i < lines.length; i++) {
        const rawLine = lines[i];
        const line = rawLine.trim();

        if (line.startsWith('```')) {
            if (inCodeBlock) {
                out.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
                codeLines = [];
                inCodeBlock = false;
            } else {
                closeList();
                inCodeBlock = true;
            }
            continue;
        }

        if (inCodeBlock) {
            codeLines.push(rawLine);
            continue;
        }

        if (!line) {
            closeList();
            continue;
        }

        if (line.includes('|') && i + 1 < lines.length && isManualTableSeparator(lines[i + 1])) {
            closeList();
            const tableRows = [rawLine, lines[i + 1]];
            i += 2;
            while (i < lines.length && String(lines[i] || '').trim().includes('|') && String(lines[i] || '').trim()) {
                tableRows.push(lines[i]);
                i += 1;
            }
            i -= 1;
            out.push(renderManualTable(tableRows));
            continue;
        }

        const heading = line.match(/^(#{1,4})\s+(.+)$/);
        if (heading) {
            closeList();
            const level = Math.min(heading[1].length, 4);
            out.push(`<h${level}>${renderManualInline(heading[2])}</h${level}>`);
            continue;
        }

        const ordered = line.match(/^\d+\.\s+(.+)$/);
        if (ordered) {
            openList('ol');
            out.push(`<li>${renderManualInline(ordered[1])}</li>`);
            continue;
        }

        const unordered = line.match(/^[-*]\s+(.+)$/);
        if (unordered) {
            openList('ul');
            out.push(`<li>${renderManualInline(unordered[1])}</li>`);
            continue;
        }

        closeList();
        out.push(`<p>${renderManualInline(line)}</p>`);
    }

    closeList();
    if (inCodeBlock && codeLines.length) {
        out.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
    }

    return `<article class="manual-md">${out.join('\n')}</article>`;
}

async function loadProductManualIntoModal(force = false) {
    const body = document.querySelector('#manualModal .manual-modal-body');
    if (!body) return;
    if (__manualHtmlCache && !force) {
        body.innerHTML = __manualHtmlCache;
        return;
    }
    if (__manualLoadPromise && !force) {
        await __manualLoadPromise;
        if (__manualHtmlCache) body.innerHTML = __manualHtmlCache;
        return;
    }

    body.innerHTML = '<div class="manual-loading">正在加载完整产品说明书...</div>';
    __manualLoadPromise = fetch('/api/product_manual', { credentials: 'same-origin' })
        .then(async res => {
            const text = await res.text();
            if (res.status === 401) {
                try { showLogin(true); } catch {}
                throw new Error('登录已失效，请重新登录');
            }
            if (!res.ok) {
                let msg = text;
                try {
                    const json = JSON.parse(text);
                    msg = json.message || msg;
                } catch {}
                throw new Error(msg || `HTTP ${res.status}`);
            }
            __manualHtmlCache = renderProductManualMarkdown(text);
            body.innerHTML = __manualHtmlCache;
        })
        .catch(err => {
            const msg = err && err.message ? err.message : String(err);
            body.innerHTML = `<div class="manual-error">产品说明书加载失败：${escapeHtml(msg)}</div>`;
        })
        .finally(() => {
            __manualLoadPromise = null;
        });

    await __manualLoadPromise;
}

function openManual() {
    const modal = document.getElementById('manualModal');
    if (modal) {
        modal.style.display = 'block';
        loadProductManualIntoModal();
    }
}

function closeManual() {
    const modal = document.getElementById('manualModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// KB Edit Modal Logic
let __kbEditInitialDigest = null;
let __kbEditIsCreateMode = true;
let __kbEditOpenSeq = 0;
let __kbEditTouched = false;
let __kbEditDraftTimer = null;
let __kbEditDraftContextId = '';
let __kbEditSyncOnlineBound = false;
let __kbEditSyncingPending = false;
let __kbEditSaving = false;
let __kbEditCurrentPreviewItem = null;
let __kbEditTemplateRefId = '';
let __kbEditTemplatePickerBound = false;
let __kbEditQualityContext = null;
const KB_EDIT_DRAFT_KEY_PREFIX = 'kb_edit_draft_v1:';
const KB_EDIT_PENDING_SYNC_KEY = 'kb_edit_pending_sync_v1';

function __kbEditNormalizeText(v) {
    return String(v ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim();
}

function __kbEditCollectDigest() {
    const form = document.getElementById('kbEditForm');
    if (!form) return {};
    const get = (k) => __kbEditNormalizeText(form.elements?.[k]?.value);
    const opts = { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true };

    const checkedProducts = Array.from(document.querySelectorAll('#productCheckboxes input.product-item-check:checked'))
        .map(cb => __kbEditNormalizeText(cb.value))
        .filter(Boolean)
        .sort();
    const productName = checkedProducts.length ? checkedProducts.join(',') : get('product_name');
    const productCategory = __kbEditNormalizeText(document.getElementById('productCategorySelectInput')?.getAttribute('data-value') || get('product_category_name'));

    return {
        question_wiki_id: get('question_wiki_id'),
        product_category_name: productCategory,
        question_type: get('question_type'),
        if_bm25: get('if_bm25') || 'false',
        question: get('question'),
        answer: get('answer'),
        answer_type: get('answer_type'),
        product_name: productName,
        similar_questions: parseSmartListValue(get('similar_questions'), { splitOnAsciiComma: true }).join('\n'),
        keyword_list: parseSmartListValue(get('keyword_list'), { splitOnAsciiComma: true }).join('\n'),
        image_urls: parseSmartListValue(get('image_urls'), opts).join('\n'),
        video_urls: parseSmartListValue(get('video_urls'), opts).join('\n'),
        file_urls: parseSmartListValue(get('file_urls'), opts).join('\n'),
        link_type: get('link_type'),
        link_url: parseSmartListValue(get('link_url'), opts).join('\n'),
        // Include tags into dirty check so the save button enables when only tags change.
        kb_tags_input: get('kb_tags_input'),
        // Template source is a draft/preview hint only; it is never submitted to backend.
        template_ref_id: __kbEditNormalizeText(__kbEditTemplateRefId),
    };
}

function __kbEditStatusText(status, isCreateMode = false) {
    if (isCreateMode) return '新增中';
    const value = String(status || 'unadjusted').trim();
    if (value === 'creating') return '新增中';
    if (value === 'modifying') return '修改中';
    if (value === 'deleting') return '删除中';
    return '未调整';
}

function __kbEditFormatPreviewTime(value) {
    const raw = String(value || '').trim();
    if (!raw) return '-';
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return raw;
    return d.toLocaleString('zh-CN', { hour12: false });
}

function __kbEditSplitPreviewList(value, opts = {}) {
    let items = parseSmartListValue(value, {
        splitOnAsciiComma: true,
        splitOnChineseCommaWhenUrlList: !!opts.isUrlList,
        isUrlList: !!opts.isUrlList
    });
    if (!opts.isUrlList) {
        items = items.flatMap(v => String(v || '').split(/[,\n，]+/));
    }
    const seen = new Set();
    return items
        .map(v => String(v ?? '').trim())
        .filter(Boolean)
        .filter(v => {
            const key = v.toLowerCase();
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
}

function __kbEditWriteText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function __kbEditRenderPreviewChips(id, items, emptyText = '未填写') {
    const el = document.getElementById(id);
    if (!el) return;
    const list = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!list.length) {
        el.innerHTML = `<span class="kb-preview-empty">${_escapeHtml(emptyText)}</span>`;
        return;
    }
    const shown = list.slice(0, 18);
    const more = list.length > shown.length ? `<span class="kb-preview-chip">+${list.length - shown.length}</span>` : '';
    el.innerHTML = shown.map(item => `<span class="kb-preview-chip" title="${_escapeHtml(item)}">${_escapeHtml(item)}</span>`).join('') + more;
}

function __kbEditRenderPreviewText(id, value, emptyText) {
    const el = document.getElementById(id);
    if (!el) return;
    const text = String(value || '').trim();
    el.textContent = text || emptyText;
    el.classList.toggle('kb-preview-empty', !text);
}

function __kbEditIsPreviewChanged(key) {
    if (!__kbEditInitialDigest) return false;
    const current = __kbEditCollectDigest();
    if (key === 'resources') {
        return ['image_urls', 'video_urls', 'file_urls', 'link_type', 'link_url'].some(k => String(current[k] ?? '') !== String(__kbEditInitialDigest[k] ?? ''));
    }
    if (key === 'basic_meta') {
        return ['question_type', 'answer_type', 'if_bm25'].some(k => String(current[k] ?? '') !== String(__kbEditInitialDigest[k] ?? ''));
    }
    return String(current[key] ?? '') !== String(__kbEditInitialDigest[key] ?? '');
}

function __kbEditRenderPreviewResources(digest) {
    const el = document.getElementById('kbEditPreviewResources');
    if (!el) return;
    const groups = [
        ['图片', __kbEditSplitPreviewList(digest.image_urls, { isUrlList: true })],
        ['视频', __kbEditSplitPreviewList(digest.video_urls, { isUrlList: true })],
        ['文件', __kbEditSplitPreviewList(digest.file_urls, { isUrlList: true })],
        [digest.link_type || '外链', __kbEditSplitPreviewList(digest.link_url, { isUrlList: true })]
    ];
    const rows = [];
    groups.forEach(([kind, urls]) => {
        urls.forEach(url => {
            const href = /^https?:\/\//i.test(url) ? url : `http://${url}`;
            rows.push(`
                <div class="kb-preview-resource-row">
                    <span class="kb-preview-resource-kind">${_escapeHtml(kind)}</span>
                    <a href="${_escapeHtml(href)}" target="_blank" rel="noopener noreferrer" title="${_escapeHtml(url)}">${_escapeHtml(url)}</a>
                </div>
            `);
        });
    });
    el.innerHTML = rows.join('') || '<span class="kb-preview-empty">暂无资源链接</span>';
}

function __kbEditSyncPreviewChangedState() {
    document.querySelectorAll('#kbEditModal .kb-preview-field[data-preview-key]').forEach(field => {
        const key = field.getAttribute('data-preview-key');
        field.classList.toggle('is-changed', __kbEditIsPreviewChanged(key));
    });
}

function __kbEditRenderPreview() {
    const modal = document.getElementById('kbEditModal');
    if (!modal || modal.style.display === 'none') return;
    const digest = __kbEditCollectDigest();
    const item = __kbEditCurrentPreviewItem || {};
    const idText = digest.question_wiki_id || '保存后自动生成';
    const templateRefText = __kbEditIsCreateMode ? (__kbEditTemplateRefId || '未选择') : '-';
    const statusText = __kbEditStatusText(item.review_status, __kbEditIsCreateMode);
    const updatedText = __kbEditFormatPreviewTime(item.update_time);

    __kbEditWriteText('kbEditHeaderId', idText);
    __kbEditWriteText('kbEditHeaderTemplateRef', templateRefText);
    __kbEditWriteText('kbEditHeaderStatus', statusText);
    __kbEditWriteText('kbEditHeaderUpdated', updatedText);
    __kbEditWriteText('kbEditPreviewMode', __kbEditIsCreateMode ? '新增知识库条目' : '编辑知识库条目');
    __kbEditWriteText('kbEditPreviewId', idText);
    __kbEditWriteText('kbEditPreviewTemplateRef', templateRefText);
    __kbEditWriteText('kbEditPreviewStatus', statusText);
    const headerTemplateWrap = document.getElementById('kbEditHeaderTemplateRefWrap');
    if (headerTemplateWrap) headerTemplateWrap.style.display = __kbEditIsCreateMode ? '' : 'none';
    const previewTemplateWrap = document.getElementById('kbEditPreviewTemplateRefWrap');
    if (previewTemplateWrap) previewTemplateWrap.style.display = __kbEditIsCreateMode ? '' : 'none';

    __kbEditRenderPreviewChips('kbEditPreviewCategory', __kbEditSplitPreviewList(digest.product_category_name), '未选择分类');
    __kbEditRenderPreviewChips('kbEditPreviewProducts', __kbEditSplitPreviewList(digest.product_name), '未选择型号');
    __kbEditRenderPreviewChips('kbEditPreviewTags', __kbEditSplitPreviewList(digest.kb_tags_input), '未设置标签');
    __kbEditRenderPreviewChips('kbEditPreviewAttrs', [
        digest.question_type ? `问题类型：${digest.question_type}` : '',
        digest.answer_type ? `答案类型：${digest.answer_type}` : '',
        `BM25：${String(digest.if_bm25).toLowerCase() === 'true' ? '是' : '否'}`
    ].filter(Boolean), '未设置属性');

    __kbEditRenderPreviewText('kbEditPreviewQuestion', digest.question, '暂无问题内容');
    __kbEditRenderPreviewChips('kbEditPreviewSimilarQuestions', __kbEditSplitPreviewList(digest.similar_questions), '未设置相似问');
    __kbEditRenderPreviewText('kbEditPreviewAnswer', digest.answer, '暂无答案内容');
    __kbEditRenderPreviewResources(digest);
    __kbEditSyncPreviewChangedState();
}

function __kbEditFormatTime(ts) {
    const d = new Date(Number(ts));
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleString('zh-CN', { hour12: false });
}

function __kbEditUpdateAutosaveHint(text, color = '#666') {
    const el = document.getElementById('kbEditAutosaveHint');
    if (!el) return;
    el.textContent = text;
    el.style.color = color;
}

function __kbEditSetDraftStatus(status, savedAt = null) {
    const ts = savedAt ? __kbEditFormatTime(savedAt) : '';
    if (status === 'clean') {
        __kbEditUpdateAutosaveHint('草稿状态：未修改');
        return;
    }
    if (status === 'dirty') {
        __kbEditUpdateAutosaveHint('草稿状态：待保存', '#d48806');
        return;
    }
    if (status === 'saved') {
        __kbEditUpdateAutosaveHint(`草稿状态：已保存${ts ? `（${ts}）` : ''}`, '#389e0d');
        return;
    }
    if (status === 'pending_sync') {
        __kbEditUpdateAutosaveHint('草稿状态：待同步（离线）', '#d46b08');
        return;
    }
    if (status === 'error') {
        __kbEditUpdateAutosaveHint('草稿状态：保存失败', '#cf1322');
        return;
    }
    __kbEditUpdateAutosaveHint('草稿状态：未知');
}

function __kbEditDraftKey(id) {
    return `${KB_EDIT_DRAFT_KEY_PREFIX}${String(id || '__new__')}`;
}

function __kbEditGetCurrentDraftKey() {
    return __kbEditDraftKey(__kbEditDraftContextId);
}

function __kbEditSaveDraftNow() {
    const form = document.getElementById('kbEditForm');
    const modal = document.getElementById('kbEditModal');
    if (!form || !modal || modal.style.display === 'none') return;
    const digest = __kbEditCollectDigest();
    const current = JSON.stringify(digest);
    const initial = JSON.stringify(__kbEditInitialDigest || {});
    if (!__kbEditIsCreateMode && current === initial) {
        __kbEditSetDraftStatus('clean');
        return;
    }
    const payload = {
        v: 1,
        id: __kbEditDraftContextId || '__new__',
        isCreateMode: !!__kbEditIsCreateMode,
        status: 'saved',
        digest,
        savedAt: Date.now()
    };
    try {
        localStorage.setItem(__kbEditGetCurrentDraftKey(), JSON.stringify(payload));
        __kbEditSetDraftStatus('saved', payload.savedAt);
    } catch {
        __kbEditSetDraftStatus('error');
    }
}

function __kbEditScheduleDraftSave() {
    if (__kbEditDraftTimer) clearTimeout(__kbEditDraftTimer);
    __kbEditDraftTimer = setTimeout(() => {
        __kbEditDraftTimer = null;
        __kbEditSaveDraftNow();
    }, 1800);
}

function __kbEditClearDraft(id = __kbEditDraftContextId) {
    try { localStorage.removeItem(__kbEditDraftKey(id)); } catch {}
    __kbEditSetDraftStatus('clean');
}

function __kbEditReadDraft(id = __kbEditDraftContextId) {
    try {
        const raw = localStorage.getItem(__kbEditDraftKey(id));
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object' || !parsed.digest) return null;
        return parsed;
    } catch {
        return null;
    }
}

function __kbEditRestoreDraftDigest(digest) {
    const form = document.getElementById('kbEditForm');
    if (!form || !digest || typeof digest !== 'object') return;
    const setVal = (name, value) => {
        const el = form.elements?.[name];
        if (el) el.value = String(value ?? '');
    };
    [
        'question_wiki_id', 'question_type', 'if_bm25', 'question', 'answer', 'answer_type',
        'similar_questions', 'keyword_list', 'image_urls', 'video_urls', 'file_urls', 'link_type', 'link_url'
    ].forEach(k => setVal(k, digest[k]));
    try { __kbAnswerSetMarkdown(String(digest.answer ?? ''), { from: 'restoreDraft' }); } catch {}
    const tagsEl = document.getElementById('kbEditTagsInput');
    if (tagsEl) tagsEl.value = String(digest.kb_tags_input || '');
    __kbEditTemplateRefId = String(digest.template_ref_id || '').trim();
    __kbEditSyncTemplateReferenceUi();
    const pcInput = document.getElementById('productCategorySelectInput');
    if (pcInput) {
        const raw = String(digest.product_category_name || '');
        pcInput.setAttribute('data-value', raw);
        pcInput.value = raw.split(/[,\n，]+/).map(s => s.trim()).filter(Boolean).join('，');
    }
    const productSet = new Set(String(digest.product_name || '').split(/[,\n，]+/).map(s => s.trim()).filter(Boolean));
    document.querySelectorAll('#productCheckboxes input.product-item-check').forEach(cb => {
        cb.checked = productSet.has(String(cb.value || '').trim());
    });
    if (window.updateSelectAllStates) window.updateSelectAllStates();
    __kbEditRenderPreview();
}

function __kbEditHasUnsavedChanges() {
    if (__kbEditSaving) return false;
    if (!__kbEditTouched) return false;
    const current = JSON.stringify(__kbEditCollectDigest());
    const initial = JSON.stringify(__kbEditInitialDigest || {});
    return current !== initial;
}

function __kbEditBuildSubmitPayload() {
    const form = document.getElementById('kbEditForm');
    try { __kbAnswerSyncToTextarea({ emit: false }); } catch {}
    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());
    const tagsInputEl = document.getElementById('kbEditTagsInput');
    const tagNames = __kbParseTagNames(tagsInputEl?.value);

    try {
        const pcEl = document.getElementById('productCategorySelectInput');
        if (pcEl) {
            const raw = pcEl.getAttribute('data-value') || pcEl.value || '';
            const parts = String(raw).split(/[,\n，]+/).map(s => s.trim()).filter(Boolean);
            data.product_category_name = parts.join(',');
        }
    } catch {}
    if (data.if_bm25 === '' || data.if_bm25 === null || data.if_bm25 === undefined) data.if_bm25 = 'false';
    const checkedProducts = Array.from(document.querySelectorAll('#productCheckboxes input.product-item-check:checked')).map(cb => cb.value);
    if (checkedProducts.length > 0) data.product_name = checkedProducts.join(',');
    if (data.similar_questions) {
        try { data.similar_questions = JSON.parse(data.similar_questions); }
        catch { data.similar_questions = parseSmartListValue(data.similar_questions, { splitOnAsciiComma: true }); }
    }
    if (data.keyword_list) {
        try { data.keyword_list = JSON.parse(data.keyword_list); }
        catch { data.keyword_list = parseSmartListValue(data.keyword_list, { splitOnAsciiComma: true }); }
    }
    const urlListOpts = { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true };
    ['image_urls', 'video_urls', 'file_urls'].forEach(k => {
        if (!data[k]) return;
        try { data[k] = JSON.parse(data[k]); }
        catch { data[k] = parseSmartListValue(data[k], urlListOpts); }
    });
    if (typeof data.link_url === 'string') data.link_url = data.link_url.trim();
    if (typeof data.link_type === 'string') data.link_type = data.link_type.trim();
    if (__kbEditQualityContext) {
        data.change_source = '管控中心';
        data.quality_task_id = __kbEditQualityContext.task_id;
        data.base_update_time = __kbEditQualityContext.base_update_time || '';
    }
    return { data, tagNames };
}

function __kbEditLoadPendingSyncQueue() {
    try {
        const raw = localStorage.getItem(KB_EDIT_PENDING_SYNC_KEY);
        const arr = raw ? JSON.parse(raw) : [];
        return Array.isArray(arr) ? arr : [];
    } catch {
        return [];
    }
}

function __kbEditSavePendingSyncQueue(queue) {
    try { localStorage.setItem(KB_EDIT_PENDING_SYNC_KEY, JSON.stringify(Array.isArray(queue) ? queue : [])); } catch {}
}

function __kbEditQueuePendingSync(payload) {
    const queue = __kbEditLoadPendingSyncQueue();
    queue.push({ ...payload, status: 'pending_sync', queuedAt: Date.now() });
    __kbEditSavePendingSyncQueue(queue);
}

async function __kbEditSyncPendingQueue() {
    if (__kbEditSyncingPending || !navigator.onLine) return;
    const queue = __kbEditLoadPendingSyncQueue();
    if (!queue.length) return;
    __kbEditSyncingPending = true;
    try {
        const remained = [];
        for (const item of queue) {
            try {
                const res = await api('/kb/update', 'POST', item.data || {});
                if (!res?.success) throw new Error(res?.message || res?.error || '未知错误');
                const savedWikiId = String(res.question_wiki_id || item?.data?.question_wiki_id || '').trim();
                if (savedWikiId) {
                    const tr = await api('/kb/item/tags', 'PUT', {
                        libraryType: 'current',
                        question_wiki_id: savedWikiId,
                        tagNames: Array.isArray(item.tagNames) ? item.tagNames : []
                    });
                    if (!tr?.success) throw new Error(tr?.message || '标签同步失败');
                }
            } catch {
                remained.push(item);
            }
        }
        __kbEditSavePendingSyncQueue(remained);
        if (!remained.length) showToast('离线期间保存的数据已自动同步');
    } finally {
        __kbEditSyncingPending = false;
    }
}

function __kbEditEnsureSyncBindings() {
    if (__kbEditSyncOnlineBound) return;
    __kbEditSyncOnlineBound = true;
    window.addEventListener('online', () => { __kbEditSyncPendingQueue(); });
    __kbEditSyncPendingQueue();
}

function __kbEditRefreshDirtyState() {
    const hint = document.getElementById('kbEditDirtyHint');
    const saveBtn = document.getElementById('saveKBItemBtn');
    if (!hint || !saveBtn) return;
    if (__kbEditIsCreateMode) {
        hint.textContent = '新增模式';
        hint.style.color = '#666';
        saveBtn.disabled = false;
        __kbEditRenderPreview();
        return;
    }
    const current = JSON.stringify(__kbEditCollectDigest());
    const initial = JSON.stringify(__kbEditInitialDigest || {});
    const dirty = current !== initial;
    hint.textContent = dirty ? '已修改（可保存）' : '未修改';
    hint.style.color = dirty ? '#d48806' : '#666';
    saveBtn.disabled = !dirty;
    __kbEditSetDraftStatus(dirty ? 'dirty' : 'clean');
    __kbEditRenderPreview();
}

function __kbEditCaptureInitialState(isCreateMode) {
    __kbEditIsCreateMode = !!isCreateMode;
    __kbEditTouched = false;
    __kbEditInitialDigest = __kbEditCollectDigest();
    __kbEditRefreshDirtyState();
}

function __kbEditBindDirtyChecker() {
    const form = document.getElementById('kbEditForm');
    if (!form || form.dataset.dirtyBound === '1') return;
    form.dataset.dirtyBound = '1';
    form.addEventListener('input', () => {
        __kbEditTouched = true;
        __kbEditRefreshDirtyState();
        __kbEditScheduleDraftSave();
    }, true);
    form.addEventListener('change', () => {
        __kbEditTouched = true;
        __kbEditRefreshDirtyState();
        __kbEditScheduleDraftSave();
    }, true);
}

function __kbEditFormatListTextarea(value, opts = {}) {
    if (value === null || value === undefined) return '';
    const items = parseSmartListValue(value, opts);
    return items.length ? items.join('\n') : '';
}

function __kbEditSetProductCategoryInput(value) {
    const pcEl = document.getElementById('productCategorySelectInput');
    if (!pcEl) return;
    const raw = String(value || '').trim();
    const parts = raw.split(/[,\n，]+/).map(s => s.trim()).filter(Boolean);
    pcEl.setAttribute('data-value', parts.join(','));
    pcEl.value = parts.join('，');
    try {
        pcEl.dispatchEvent(new Event('input', { bubbles: true }));
        pcEl.dispatchEvent(new Event('change', { bubbles: true }));
    } catch {}
}

function __kbEditApplyProductsToForm(productValue) {
    const prods = String(productValue || '').split(/[,\n，]+/).map(s => s.trim()).filter(Boolean);
    const productInput = document.getElementById('kbEditProductName');
    if (productInput) productInput.value = prods.join(',');

    let checkboxes = Array.from(document.querySelectorAll('#productCheckboxes input.product-item-check'));
    if (checkboxes.length) {
        const availableModels = checkboxes.map(cb => cb.value);
        const extraModels = prods.filter(p => !availableModels.includes(p));
        if (extraModels.length > 0 && window.renderExtraModels) {
            window.renderExtraModels(extraModels);
            checkboxes = Array.from(document.querySelectorAll('#productCheckboxes input.product-item-check'));
        }
        checkboxes.forEach(cb => {
            cb.checked = prods.includes(cb.value);
        });
        if (window.updateSelectAllStates) window.updateSelectAllStates();
    } else if (productInput) {
        try {
            productInput.dispatchEvent(new Event('input', { bubbles: true }));
            productInput.dispatchEvent(new Event('change', { bubbles: true }));
        } catch {}
    }
}

function __kbEditHasMeaningfulCreateInput(digest = null) {
    const d = digest || __kbEditCollectDigest();
    const keys = [
        'product_category_name', 'question_type', 'question', 'answer', 'answer_type',
        'product_name', 'similar_questions', 'keyword_list', 'image_urls', 'video_urls',
        'file_urls', 'link_type', 'link_url', 'kb_tags_input'
    ];
    return keys.some(k => String(d?.[k] ?? '').trim());
}

function __kbEditSyncTemplateReferenceUi(message = '') {
    const panel = document.getElementById('kbEditTemplatePanel');
    if (panel) panel.style.display = __kbEditIsCreateMode ? '' : 'none';

    const refText = __kbEditIsCreateMode ? (__kbEditTemplateRefId || '未选择') : '-';
    __kbEditWriteText('kbEditHeaderTemplateRef', refText);
    __kbEditWriteText('kbEditPreviewTemplateRef', refText);

    const clearBtn = document.getElementById('kbTemplateClearBtn');
    if (clearBtn) clearBtn.style.display = __kbEditTemplateRefId ? '' : 'none';

    const statusEl = document.getElementById('kbTemplateStatus');
    if (statusEl) {
        statusEl.className = 'kb-template-status' + (__kbEditTemplateRefId ? ' is-applied' : '');
        statusEl.textContent = message || (__kbEditTemplateRefId
            ? `已使用 ${__kbEditTemplateRefId} 作为参考，保存时仍会生成新条目 ID。`
            : '未选择模板，新增条目将从空白表单开始。');
    }

    const headerTemplateWrap = document.getElementById('kbEditHeaderTemplateRefWrap');
    if (headerTemplateWrap) headerTemplateWrap.style.display = __kbEditIsCreateMode ? '' : 'none';
    const previewTemplateWrap = document.getElementById('kbEditPreviewTemplateRefWrap');
    if (previewTemplateWrap) previewTemplateWrap.style.display = __kbEditIsCreateMode ? '' : 'none';
}

function __kbEditResetTemplatePicker() {
    __kbEditTemplateRefId = '';
    const input = document.getElementById('kbTemplateIdInput');
    if (input) input.value = '';
    const resultEl = document.getElementById('kbTemplateResult');
    if (resultEl) {
        resultEl.classList.add('d-none');
        resultEl.innerHTML = '';
    }
    __kbEditSyncTemplateReferenceUi();
}

function __kbEditBindTemplatePicker() {
    if (__kbEditTemplatePickerBound) return;
    const input = document.getElementById('kbTemplateIdInput');
    if (!input) return;
    __kbEditTemplatePickerBound = true;
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            kbSearchTemplateById();
        }
    });
}

function __kbEditResetWorkbenchScroll() {
    const modal = document.getElementById('kbEditModal');
    if (!modal) return;

    try {
        const active = document.activeElement;
        if (active && modal.contains(active) && typeof active.blur === 'function') {
            active.blur();
        }
    } catch {}

    const selectors = [
        '.kb-edit-modal-content',
        '.kb-edit-modal-body',
        '.kb-edit-preview-pane',
        '.kb-edit-main-pane',
        '.kb-edit-side-pane',
        '#answerTuiEditor .toastui-editor-md-container',
        '#answerTuiEditor .toastui-editor-md-container .toastui-editor',
        '#answerTuiEditor .toastui-editor-md-preview',
        '#answerTuiEditor .toastui-editor-ww-container',
        '#answerTuiEditor .toastui-editor-ww-container .toastui-editor-contents'
    ];

    try {
        modal.scrollTop = 0;
        modal.scrollLeft = 0;
        const content = modal.querySelector('.kb-edit-modal-content');
        if (content) {
            content.scrollTop = 0;
            content.scrollLeft = 0;
        }
    } catch {}

    selectors.forEach((selector) => {
        modal.querySelectorAll(selector).forEach((el) => {
            try {
                el.scrollTop = 0;
                el.scrollLeft = 0;
            } catch {}
        });
    });
}

function __kbEditScheduleTopReset() {
    __kbEditResetWorkbenchScroll();
    try { requestAnimationFrame(__kbEditResetWorkbenchScroll); } catch {}
    try { requestAnimationFrame(() => requestAnimationFrame(__kbEditResetWorkbenchScroll)); } catch {}
    setTimeout(__kbEditResetWorkbenchScroll, 80);
    setTimeout(__kbEditResetWorkbenchScroll, 180);
}

async function __kbEditFetchItemTags(wikiId) {
    const id = String(wikiId || '').trim();
    if (!id) return [];
    try {
        const tr = await api(`/kb/item/tags?libraryType=current&question_wiki_id=${encodeURIComponent(id)}`);
        if (tr && tr.success && Array.isArray(tr.tags)) return tr.tags;
    } catch (e) {
        console.error('Failed to load template tags:', e);
    }
    return [];
}

function __kbEditApplyTemplateItem(item, templateId, tags = []) {
    const form = document.getElementById('kbEditForm');
    if (!form || !item || typeof item !== 'object') return;
    const setVal = (name, value) => {
        const el = form.elements?.[name];
        if (el && typeof el.value !== 'undefined') el.value = String(value ?? '');
    };

    // Keep create mode safe: never copy the template ID into the new row primary key.
    setVal('question_wiki_id', '');
    __kbEditSetProductCategoryInput(item.product_category_name || '');
    setVal('question_type', item.question_type || '');
    setVal('if_bm25', item.if_bm25 === true ? 'true' : 'false');
    setVal('question', item.question || '');
    setVal('answer', item.answer || '');
    try { __kbAnswerSetMarkdown(item.answer || '', { from: 'kb-template' }); } catch {}
    setVal('answer_type', item.answer_type || '');
    setVal('similar_questions', __kbEditFormatListTextarea(item.similar_questions, { splitOnAsciiComma: true }));
    setVal('keyword_list', __kbEditFormatListTextarea(item.keyword_list, { splitOnAsciiComma: true }));
    setVal('image_urls', __kbEditFormatListTextarea(item.image_urls, { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true }));
    setVal('video_urls', __kbEditFormatListTextarea(item.video_urls, { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true }));
    setVal('file_urls', __kbEditFormatListTextarea(item.file_urls, { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true }));
    if (form.elements['link_type']) setVal('link_type', item.link_type || '');
    if (form.elements['link_url']) setVal('link_url', item.link_url || '');
    __kbEditApplyProductsToForm(item.product_name || '');

    const tagsEl = document.getElementById('kbEditTagsInput');
    if (tagsEl) tagsEl.value = Array.isArray(tags) ? tags.join(', ') : '';

    __kbEditTemplateRefId = String(templateId || item.question_wiki_id || item.id || '').trim();
    __kbEditTouched = true;
    __kbEditRefreshDirtyState();
    __kbEditScheduleDraftSave();
}

async function kbSearchTemplateById() {
    if (!__kbEditIsCreateMode) return;
    const input = document.getElementById('kbTemplateIdInput');
    const btn = document.getElementById('kbTemplateSearchBtn');
    const statusEl = document.getElementById('kbTemplateStatus');
    const resultEl = document.getElementById('kbTemplateResult');
    const rawId = String(input?.value || '').trim();
    if (!rawId) {
        if (statusEl) {
            statusEl.className = 'kb-template-status is-error';
            statusEl.textContent = '请输入要引用的已有条目 ID。';
        }
        return;
    }

    if (__kbEditHasMeaningfulCreateInput() && __kbEditTemplateRefId !== rawId) {
        const ok = confirm('当前表单已有内容，应用模板会覆盖已填写的业务字段。是否继续？');
        if (!ok) return;
    }

    if (btn) {
        btn.disabled = true;
        btn.textContent = '搜索中...';
    }
    if (statusEl) {
        statusEl.className = 'kb-template-status';
        statusEl.textContent = '正在搜索模板...';
    }

    try {
        const res = await api(`/kb/item?table=knowledge_base_v1&id=${encodeURIComponent(rawId)}`);
        if (!res || !res.success) throw new Error(res?.message || res?.error || '搜索失败');
        const item = res.data || {};
        if (!item || !Object.keys(item).length) {
            __kbEditTemplateRefId = '';
            __kbEditSyncTemplateReferenceUi('未找到该 ID 对应的条目。');
            if (statusEl) statusEl.className = 'kb-template-status is-error';
            if (resultEl) {
                resultEl.classList.add('d-none');
                resultEl.innerHTML = '';
            }
            __kbEditRenderPreview();
            return;
        }

        const sourceId = String(item.question_wiki_id || rawId).trim();
        const tags = await __kbEditFetchItemTags(sourceId);
        __kbEditApplyTemplateItem(item, sourceId, tags);
        __kbEditSyncTemplateReferenceUi();
        if (resultEl) {
            const question = String(item.question || '').trim();
            const answer = String(item.answer || '').trim();
            resultEl.classList.remove('d-none');
            resultEl.innerHTML = `
                <div class="kb-template-result-id">参考 ID：${_escapeHtml(sourceId)}</div>
                <div class="kb-template-result-question">${_escapeHtml(question || '暂无问题内容')}</div>
                <div class="kb-template-result-meta">${_escapeHtml(answer ? `答案 ${answer.length} 字` : '暂无答案内容')}</div>
            `;
        }
        showToast(`已按 ${sourceId} 填充模板，可继续编辑差异内容`);
    } catch (e) {
        if (statusEl) {
            statusEl.className = 'kb-template-status is-error';
            statusEl.textContent = '模板搜索失败：' + (e?.message || String(e));
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '搜索';
        }
    }
}

function kbClearTemplateReference() {
    __kbEditTemplateRefId = '';
    const input = document.getElementById('kbTemplateIdInput');
    if (input) input.value = '';
    const resultEl = document.getElementById('kbTemplateResult');
    if (resultEl) {
        resultEl.classList.add('d-none');
        resultEl.innerHTML = '';
    }
    __kbEditSyncTemplateReferenceUi('已清除参考 ID，当前已填字段保持不变。');
    __kbEditTouched = true;
    __kbEditRefreshDirtyState();
    __kbEditScheduleDraftSave();
}

window.kbSearchTemplateById = kbSearchTemplateById;
window.kbClearTemplateReference = kbClearTemplateReference;

async function openKBEditModal(id = null, options = {}) {
    const modal = document.getElementById('kbEditModal');
    const form = document.getElementById('kbEditForm');
    if (!modal || !form) return;
    options = options || {};
    const seq = ++__kbEditOpenSeq;
    __kbEditIsCreateMode = !id;
    __kbEditQualityContext = options.qualityTask || null;
    __kbEditDraftContextId = String(id || '__new__');
    __kbEditEnsureSyncBindings();
    __kbEditBindTemplatePicker();
    try { __kbAnswerEnsureTui(); } catch {}
    // Prevent cross-item leakage from previous in-flight AI streams / UI states.
    try { __aiCancelAllInFlight('kb-edit-open'); } catch {}
    try { __aiResetKbEditUiState(); } catch {}
    kbLoadClipboardSession();
    
    form.reset();
    __kbEditCurrentPreviewItem = null;
    __kbEditResetTemplatePicker();
    document.getElementById('kbEditTitle').innerText = __kbEditQualityContext ? '编辑管控任务内容' : (id ? '编辑数据' : '新增数据');
    const tagsEl = document.getElementById('kbEditTagsInput');
    if (tagsEl) tagsEl.value = '';
    try { if (!id) __kbAnswerSetMarkdown('', { from: 'openKBEditModal-create' }); } catch {}

    // Show early to avoid perceived lag and to ensure form fields are present.
    modal.classList.add('is-open');
    modal.style.display = 'flex';
    try { __kbAnswerScheduleLayoutRefresh(); } catch {}
    __kbEditScheduleTopReset();
    
    if (id) {
        const item = options.item || currentKBData.find(i => String(i.question_wiki_id) === String(id) || String(i.id) === String(id));
        if (item) {
            __kbEditCurrentPreviewItem = item;
            const formatListTextarea = (value, opts = {}) => {
                if (value === null || value === undefined) return '';
                const items = parseSmartListValue(value, opts);
                return items.length ? items.join('\n') : '';
            };
            
            const formatJsonTextarea = (value) => {
                if (value === null || value === undefined) return '';
                if (typeof value === 'string') {
                    const s = value.trim();
                    if (!s || s === '{}' || s === '[]' || s.toLowerCase() === 'null') return '';
                    return s;
                }
                if (Array.isArray(value)) return value.length ? JSON.stringify(value, null, 2) : '';
                if (typeof value === 'object') return Object.keys(value).length ? JSON.stringify(value, null, 2) : '';
                try {
                    return JSON.stringify(value, null, 2);
                } catch {
                    return String(value);
                }
            };
            
            // Populate fields
            form.elements['question_wiki_id'].value = item.question_wiki_id || '';
            // product_category_name is now a multi-select dropdown (rendered as readonly input)
            const pcEl = document.getElementById('productCategorySelectInput');
            if (pcEl) {
                const v = String(item.product_category_name || '').trim();
                pcEl.setAttribute('data-value', v);
                pcEl.value = v ? v.split(/[,\n，]+/).map(s => s.trim()).filter(Boolean).join('，') : '';
            } else {
                form.elements['product_category_name'].value = item.product_category_name || '';
            }
            form.elements['question_type'].value = item.question_type || '';
            form.elements['if_bm25'].value = (item.if_bm25 === true) ? 'true' : 'false';
            form.elements['question'].value = item.question || '';
            form.elements['answer'].value = item.answer || '';
            try { __kbAnswerSetMarkdown(item.answer || '', { from: 'openKBEditModal' }); } catch {}
            form.elements['answer_type'].value = item.answer_type || '';
            form.elements['product_name'].value = item.product_name || '';
            
            // Populate JSON/Details fields
            form.elements['similar_questions'].value = formatListTextarea(item.similar_questions, { splitOnAsciiComma: true });
            form.elements['keyword_list'].value = formatListTextarea(item.keyword_list, { splitOnAsciiComma: true });
            form.elements['image_urls'].value = formatListTextarea(item.image_urls, { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true });
            form.elements['video_urls'].value = formatListTextarea(item.video_urls, { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true });
            form.elements['file_urls'].value = formatListTextarea(item.file_urls, { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true });
            if (form.elements['link_type']) form.elements['link_type'].value = item.link_type || '';
            if (form.elements['link_url']) form.elements['link_url'].value = item.link_url || '';
            
            // Load KB tags for this item (方案A：在编辑弹窗维护标签)
            const tagsEl = document.getElementById('kbEditTagsInput');
            if (tagsEl) {
                const wikiId = String(item.question_wiki_id || item.id || '').trim();
                if (wikiId) {
                    try {
                        const tr = await api(`/kb/item/tags?libraryType=current&question_wiki_id=${encodeURIComponent(wikiId)}`);
                        if (tr && tr.success && Array.isArray(tr.tags)) {
                            tagsEl.value = tr.tags.join(', ');
                        }
                    } catch (e) {
                        console.error('Failed to load KB tags:', e);
                    }
                }
            }
            
            // Check products
            const prods = (item.product_name || '').split(/[,，]/).map(s => s.trim()).filter(s => s);
            
            // Identify non-catalog models
            const availableModels = Array.from(document.querySelectorAll('#productCheckboxes input.product-item-check')).map(cb => cb.value);
            const extraModels = prods.filter(p => !availableModels.includes(p));
            
            // Render extra models if any
            if (extraModels.length > 0 && window.renderExtraModels) {
                window.renderExtraModels(extraModels);
            }
            
            // Now check all boxes
            document.querySelectorAll('#productCheckboxes input.product-item-check').forEach(cb => {
                cb.checked = prods.includes(cb.value);
            });
            if (window.updateSelectAllStates) window.updateSelectAllStates();
        }
    }

    // Load product catalog for checkboxes (async; guard against race when switching items quickly)
    await loadProductCatalogForModal();
    if (seq !== __kbEditOpenSeq) return;
    // After catalog is ready, re-apply product checks for edit mode (create mode stays empty)
    if (id) {
        const item = __kbEditCurrentPreviewItem || options.item || currentKBData.find(i => String(i.question_wiki_id) === String(id) || String(i.id) === String(id));
        if (item) {
            const prods = (item.product_name || '').split(/[,，]/).map(s => s.trim()).filter(s => s);
            document.querySelectorAll('#productCheckboxes input.product-item-check').forEach(cb => {
                cb.checked = prods.includes(cb.value);
            });
            if (window.updateSelectAllStates) window.updateSelectAllStates();
        }
    }

    try {
        const clipboardBufferEl = document.getElementById('kbClipboardBuffer');
        if (clipboardBufferEl && !clipboardBufferEl.dataset.bound) {
            clipboardBufferEl.dataset.bound = '1';
            clipboardBufferEl.addEventListener('input', kbUpdateClipboardStats);
        }
        if (clipboardBufferEl && kbClipboardSessionItems.length > 0 && !String(clipboardBufferEl.value || '').trim()) {
            clipboardBufferEl.value = kbClipboardSessionItems.join('\n\n');
        }
        kbUpdateClipboardStats();
    } catch {}
    // Preload ops libraries for quick insert menu
    loadOpsLibrariesForToolbar().catch(() => {});
    // Bind lightweight UI helpers (stats / selected counts)
    try { __kbEditBindUiHelpers(); } catch {}
    try { __kbEditBindDirtyChecker(); } catch {}
    __kbEditCaptureInitialState(!id);
    const draft = __kbEditReadDraft(__kbEditDraftContextId);
    if (draft?.digest) {
        const savedText = __kbEditFormatTime(draft.savedAt);
        const shouldRestore = confirm(`检测到未提交草稿${savedText ? `（保存于 ${savedText}）` : ''}，是否恢复？`);
        if (shouldRestore) {
            __kbEditRestoreDraftDigest(draft.digest);
            __kbEditTouched = true;
            __kbEditRefreshDirtyState();
            __kbEditSetDraftStatus(draft.status || 'saved', draft.savedAt);
        } else {
            __kbEditClearDraft(__kbEditDraftContextId);
        }
    } else {
        __kbEditSetDraftStatus('clean');
    }
    __kbEditRenderPreview();
    __kbEditScheduleTopReset();
}

let __kbEditUiBound = false;
function __kbEditBindUiHelpers() {
    const form = document.getElementById('kbEditForm');
    if (!form) return;
    const aEl = form.elements['answer'];
    const pNameEl = document.getElementById('kbEditProductName');
    const pBox = document.getElementById('productCheckboxes');
    const countEl = document.getElementById('kbEditSelectedProductsCount');
    const productsDetailsEl = document.getElementById('kbEditProductsDetails');
    const productsToggleTextEl = document.getElementById('kbEditProductsToggleText');
    const statsEl = document.getElementById('answerStats');
    const pcInput = document.getElementById('productCategorySelectInput');
    const pcBtn = document.getElementById('productCategoryDropdownBtn');
    const pcMenu = document.getElementById('productCategoryDropdown');

    const updateAnswerStats = () => {
        if (!statsEl || !aEl) return;
        const text = String(aEl.value || '');
        const lines = text.length ? text.split('\n').length : 0;
        // Count non-whitespace characters as "字" to be more meaningful for CN
        const chars = text.replace(/\s+/g, '').length;
        statsEl.textContent = `${lines} 行 · ${chars} 字`;
    };

    const updateSelectedProductsCount = () => {
        if (!countEl) return;
        const checked = document.querySelectorAll('#productCheckboxes input.product-item-check:checked');
        countEl.textContent = String(checked ? checked.length : 0);
    };

    const updateProductsToggleText = () => {
        if (!productsDetailsEl || !productsToggleTextEl) return;
        productsToggleTextEl.textContent = productsDetailsEl.open ? '点击收起' : '点击展开';
    };

    const pcOptions = ['扫地机', '洗地机', '吸尘器', '洗衣机'];
    const parsePcValue = (v) => String(v || '').split(/[,\n，]+/).map(s => s.trim()).filter(Boolean);
    const setPcValue = (arr) => {
        const uniq = Array.from(new Set((arr || []).map(s => String(s).trim()).filter(Boolean)));
        const text = uniq.join('，');
        if (pcInput) pcInput.value = text;
        // Keep stored value in same field for backend: comma-separated
        if (pcInput) pcInput.setAttribute('data-value', uniq.join(','));
        if (pcInput && pcInput.name === 'product_category_name') {
            // also update the actual form value (same input)
            pcInput.value = text;
        }
        if (pcInput) {
            pcInput.dispatchEvent(new Event('input', { bubbles: true }));
            pcInput.dispatchEvent(new Event('change', { bubbles: true }));
        }
    };
    const getPcSelected = () => parsePcValue(pcInput?.getAttribute('data-value') || pcInput?.value || '');

    const renderPcMenu = () => {
        if (!pcMenu) return;
        const selected = new Set(getPcSelected());
        pcMenu.innerHTML = pcOptions.map(opt => {
            const checked = selected.has(opt) ? 'checked' : '';
            return `<div class="dropdown-item" style="display:flex; gap:8px; align-items:center;" data-opt="${_escapeAttr(opt)}">
                <input type="checkbox" ${checked} />
                <span>${_escapeHtml(opt)}</span>
            </div>`;
        }).join('');
    };

    const closePcMenu = () => {
        if (pcMenu) pcMenu.classList.remove('show');
    };
    const openPcMenu = () => {
        renderPcMenu();
        if (pcMenu) pcMenu.classList.add('show');
    };

    // Initial render
    updateAnswerStats();
    updateSelectedProductsCount();
    updateProductsToggleText();
    // init product category from existing input value (e.g. when editing)
    if (pcInput) {
        const init = parsePcValue(pcInput.value);
        pcInput.setAttribute('data-value', init.join(','));
        pcInput.value = init.join('，');
    }

    // Bind once
    if (__kbEditUiBound) return;
    __kbEditUiBound = true;

    if (aEl) {
        aEl.addEventListener('input', updateAnswerStats);
        aEl.addEventListener('change', updateAnswerStats);
        aEl.addEventListener('keyup', updateAnswerStats);
    }

    if (pNameEl) {
        pNameEl.addEventListener('input', updateSelectedProductsCount);
        pNameEl.addEventListener('change', updateSelectedProductsCount);
    }

    if (pBox) {
        pBox.addEventListener('change', (e) => {
            const t = e.target;
            if (t && t.matches && t.matches('input.product-item-check')) {
                updateSelectedProductsCount();
            }
        });
    }

    if (productsDetailsEl) {
        productsDetailsEl.addEventListener('toggle', updateProductsToggleText);
    }

    if (pcBtn) {
        pcBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!pcMenu) return;
            const isOpen = pcMenu.classList.contains('show');
            if (isOpen) closePcMenu();
            else openPcMenu();
        });
    }
    if (pcInput) {
        pcInput.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            openPcMenu();
        });
    }
    if (pcMenu) {
        pcMenu.addEventListener('click', (e) => {
            const item = e.target?.closest ? e.target.closest('.dropdown-item') : null;
            if (!item) return;
            const opt = item.getAttribute('data-opt');
            if (!opt) return;
            const cur = new Set(getPcSelected());
            if (cur.has(opt)) cur.delete(opt);
            else cur.add(opt);
            setPcValue(Array.from(cur));
            renderPcMenu();
        });
    }
    document.addEventListener('click', () => closePcMenu());
}

function closeKBEditModal(options = {}) {
    const { force = false } = options || {};
    if (__kbEditSaving && !force) return;

    const finishClose = () => {
        if (__kbEditDraftTimer) {
            clearTimeout(__kbEditDraftTimer);
            __kbEditDraftTimer = null;
        }
        try { __aiCancelAllInFlight('kb-edit-modal-closed'); } catch {}
        __aiResetKbEditUiState();
        const modal = document.getElementById('kbEditModal');
        if (modal) {
            modal.classList.remove('is-open');
            modal.style.display = 'none';
        }
        __kbEditQualityContext = null;
    };

    if (!force && __kbEditHasUnsavedChanges()) {
        showKbEditUnsavedCloseChoices().then((choice) => {
            if (choice === 'cancel') return;
            if (choice === 'save') {
                __kbEditSaveDraftNow();
            } else if (choice === 'discard') {
                __kbEditClearDraft(__kbEditDraftContextId);
            }
            finishClose();
        });
        return;
    }
    finishClose();
}

function kbNormalizeClipboardText(text) {
    return String(text || '')
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n')
        .replace(/\u200B/g, '')
        .trim();
}

let kbClipboardSessionItems = [];
const KB_CLIPBOARD_STORE_KEY = 'kb_clipboard_session_v1';

function kbSaveClipboardSession() {
    try {
        localStorage.setItem(KB_CLIPBOARD_STORE_KEY, JSON.stringify(kbClipboardSessionItems || []));
    } catch {}
}

function kbLoadClipboardSession() {
    try {
        const raw = localStorage.getItem(KB_CLIPBOARD_STORE_KEY);
        if (!raw) return;
        const arr = JSON.parse(raw);
        if (!Array.isArray(arr)) return;
        kbClipboardSessionItems = arr
            .map(x => kbNormalizeClipboardText(x))
            .filter(Boolean);
    } catch {}
}

function kbPushClipboardSession(text) {
    const normalized = kbNormalizeClipboardText(text);
    if (!normalized) return;
    const last = kbClipboardSessionItems.length > 0 ? kbClipboardSessionItems[kbClipboardSessionItems.length - 1] : '';
    if (last === normalized) return;
    kbClipboardSessionItems.push(normalized);
    kbSaveClipboardSession();
}

function kbUpdateClipboardStats() {
    const el = document.getElementById('kbClipboardBuffer');
    const stats = document.getElementById('kbClipboardStats');
    if (!el || !stats) return;
    const text = String(el.value || '');
    const lines = text ? text.split('\n').length : 0;
    const chars = text.replace(/\s+/g, '').length;
    stats.textContent = `${lines} 行 · ${chars} 字`;
}

async function kbReadClipboardToBuffer() {
    const el = document.getElementById('kbClipboardBuffer');
    if (!el) return;
    try {
        // Prefer session-captured multi-copy snippets in this operation.
        if (kbClipboardSessionItems.length > 0) {
            el.value = kbClipboardSessionItems.join('\n\n');
            kbUpdateClipboardStats();
            showToast(`已读取本次复制 ${kbClipboardSessionItems.length} 条`);
            return;
        }

        if (!navigator.clipboard || typeof navigator.clipboard.readText !== 'function') {
            alert('当前环境不支持直接读取剪切板，请先手动粘贴到暂存区。');
            return;
        }
        const raw = await navigator.clipboard.readText();
        const text = kbNormalizeClipboardText(raw);
        if (!text) {
            showToast('剪切板为空');
            return;
        }
        el.value = text;
        kbClipboardSessionItems = [text];
        kbSaveClipboardSession();
        kbUpdateClipboardStats();
        showToast('已读取剪切板');
    } catch (e) {
        alert(`读取剪切板失败：${e?.message || e}\n请手动粘贴到暂存区。`);
    }
}

function kbClearClipboardBuffer() {
    const el = document.getElementById('kbClipboardBuffer');
    if (!el) return;
    el.value = '';
    kbClipboardSessionItems = [];
    try { localStorage.removeItem(KB_CLIPBOARD_STORE_KEY); } catch {}
    kbUpdateClipboardStats();
    showToast('暂存区已清空');
}

function copyKBCellText(index, key) {
    const item = Array.isArray(currentKBData) ? currentKBData[index] : null;
    if (!item) return;
    const field = String(key || '').trim();
    const text = String(item[field] ?? '').trim();
    if (!text) {
        showToast('该字段为空');
        return;
    }
    copyToClipboard(text);
}

let __aiSimilarDraftItems = [];
window.__aiSimilarPanelVisible = false;
let __aiSimilarInFlight = false;
let __aiSimilarReqSeq = 0;
let __aiAnswerDraftResult = null;
const __aiInFlightControllers = new Set();

function __aiTrackController(controller) {
    if (!controller) return;
    __aiInFlightControllers.add(controller);
}

function __aiUntrackController(controller) {
    if (!controller) return;
    try { __aiInFlightControllers.delete(controller); } catch {}
}

function __aiCancelAllInFlight(reason = 'cancelled') {
    const arr = Array.from(__aiInFlightControllers);
    arr.forEach(c => {
        try { c.abort(reason); } catch {}
    });
    __aiInFlightControllers.clear();
}

function __aiResetKbEditUiState() {
    __aiSetMetrics('aiQuestionMetrics', '');
    __aiSetMetrics('aiQuestionTypeMetrics', '');
    __aiSetMetrics('aiAnswerStatus', '');
    __aiSetMetrics('aiSimilarMetrics', '');
    __aiSetAnswerButtonsLoading(false);
    __aiStreamPreviewReset();
    __aiStreamPreviewSetVisible(false);
    const qActions = document.getElementById('aiQuestionJsonActions');
    if (qActions) qActions.style.display = 'none';
    const aActions = document.getElementById('aiAnswerJsonActions');
    if (aActions) aActions.style.display = 'none';
    __aiAnswerHideCompare();
    __aiSimilarInFlight = false;
    __aiSimilarReqSeq += 1; // invalidate stale async callbacks
    __aiSimilarDraftItems = [];

    // Hide similar-question AI panel unless user explicitly triggers it.
    try {
        window.__aiSimilarPanelVisible = false;
        const panel = document.getElementById('aiSimilarPanel');
        const list = document.getElementById('aiSimilarList');
        if (list) list.innerHTML = '';
        if (panel) panel.classList.add('d-none');
    } catch {}
}

function __aiSetMetrics(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text || '';
}

function __aiDebounce(fn, waitMs = 800) {
    let t = null;
    return (...args) => {
        if (t) clearTimeout(t);
        t = setTimeout(() => fn(...args), waitMs);
    };
}

function __aiCjkishCount(text) {
    const m = String(text || '').match(/[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]/g);
    return m ? m.length : 0;
}

function __aiMaybeRepairMojibakeText(value) {
    if (typeof value !== 'string' || !value) return value;
    if (!/[ÃÂãäåæçèéêëìíîïðñòóôõöøùúûü][\u0080-\u00ff]/.test(value)) return value;
    if (typeof TextDecoder !== 'function') return value;
    try {
        const bytes = new Uint8Array(value.length);
        for (let i = 0; i < value.length; i += 1) {
            const code = value.charCodeAt(i);
            if (code > 255) return value;
            bytes[i] = code;
        }
        const repaired = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
        if (repaired !== value && __aiCjkishCount(repaired) > __aiCjkishCount(value)) {
            return repaired;
        }
    } catch {}
    return value;
}

function __aiRepairMojibakeDeep(value) {
    if (typeof value === 'string') return __aiMaybeRepairMojibakeText(value);
    if (Array.isArray(value)) return value.map(item => __aiRepairMojibakeDeep(item));
    if (value && typeof value === 'object') {
        const out = {};
        Object.keys(value).forEach(key => {
            out[key] = __aiRepairMojibakeDeep(value[key]);
        });
        return out;
    }
    return value;
}

async function __aiOptimize(area, task, inputs, extra = {}) {
    const controller = new AbortController();
    __aiTrackController(controller);
    const timeoutMs = 60000;
    const t = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const res = await fetch(API_BASE + '/ai/optimize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ area, task, inputs, ...extra }),
            signal: controller.signal
        });
        if (res.status === 401) {
            showLogin(true);
            throw new Error('Unauthorized');
        }
        const data = await res.json();
        return __aiRepairMojibakeDeep(data);
    } finally {
        clearTimeout(t);
        __aiUntrackController(controller);
    }
}

async function __aiOptimizeStream(area, task, inputs, extra = {}, onEvent) {
    const controller = new AbortController();
    __aiTrackController(controller);
    const timeoutMs = 120000;
    const t = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const res = await fetch(API_BASE + '/ai/optimize_stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/x-ndjson'
            },
            body: JSON.stringify({ area, task, inputs, ...extra }),
            signal: controller.signal
        });
        if (res.status === 401) {
            showLogin(true);
            throw new Error('Unauthorized');
        }
        if (!res.ok) {
            const text = await res.text();
            throw new Error(`HTTP ${res.status}: ${text}`);
        }
        if (!res.body) throw new Error('Streaming not supported');
        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buf = '';
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            let idx;
            while ((idx = buf.indexOf('\n')) >= 0) {
                const line = buf.slice(0, idx).trim();
                buf = buf.slice(idx + 1);
                if (!line) continue;
                let evt = null;
                try {
                    evt = __aiRepairMojibakeDeep(JSON.parse(line));
                } catch {
                    continue;
                }
                if (typeof onEvent === 'function') onEvent(evt);
                if (evt && (evt.type === 'final' || evt.type === 'error')) return evt;
            }
        }
        return { type: 'error', message: 'stream ended unexpectedly' };
    } finally {
        clearTimeout(t);
        __aiUntrackController(controller);
    }
}

function __aiGetKbEditForm() {
    return document.getElementById('kbEditForm');
}

function __aiStreamPreviewSetVisible(visible) {
    const el = document.getElementById('aiAnswerStreamPreview');
    if (!el) return;
    el.classList.toggle('d-none', !visible);
}

function __aiStreamPreviewReset() {
    const el = document.getElementById('aiAnswerStreamPreview');
    if (!el) return;
    el.textContent = '';
}

function __aiStreamPreviewAppend(text) {
    const el = document.getElementById('aiAnswerStreamPreview');
    if (!el) return;
    el.textContent += String(text || '');
    el.scrollTop = el.scrollHeight;
}

function __aiAnswerTextStats(text) {
    const s = String(text || '');
    const lines = s ? s.split('\n').length : 0;
    const chars = s.replace(/\s+/g, '').length;
    return `${lines} 行 · ${chars} 字`;
}

function __aiAnswerSetCompareText(id, text) {
    const el = document.getElementById(id);
    if (!el) return;
    const s = String(text || '').trim();
    el.textContent = s || '暂无内容';
    el.classList.toggle('is-empty', !s);
}

function __aiAnswerGetPanel() {
    return document.querySelector('#kbEditModal .kb-answer-panel');
}

function __aiAnswerSetReviewMode(active) {
    const isActive = !!active;
    const panel = __aiAnswerGetPanel();
    const editorWrap = document.getElementById('answerTuiEditorWrap');
    const comparePanel = document.getElementById('aiAnswerComparePanel');
    if (panel) panel.classList.toggle('is-ai-review', isActive);
    if (editorWrap) editorWrap.setAttribute('aria-hidden', isActive ? 'true' : 'false');
    if (comparePanel) comparePanel.setAttribute('aria-hidden', isActive ? 'false' : 'true');
    if (!isActive) {
        try { __kbAnswerScheduleLayoutRefresh(); } catch {}
    }
}

function __aiAnswerHideCompare() {
    __aiAnswerDraftResult = null;
    __aiAnswerSetReviewMode(false);
    const panel = document.getElementById('aiAnswerComparePanel');
    if (panel) {
        panel.classList.add('d-none');
        panel.scrollTop = 0;
    }
    __aiAnswerSetCompareText('aiAnswerOriginalText', '');
    __aiAnswerSetCompareText('aiAnswerRefinedText', '');
    __aiSetMetrics('aiAnswerCompareMeta', '对比原答案和 AI 优化后内容');
    __aiSetMetrics('aiAnswerOriginalCount', '0 字');
    __aiSetMetrics('aiAnswerRefinedCount', '0 字');
    const notesEl = document.getElementById('aiAnswerCompareNotes');
    if (notesEl) {
        notesEl.classList.add('d-none');
        notesEl.textContent = '';
    }
}

function __aiAnswerShowCompare(payload, task = '') {
    const original = String(payload?.original_answer ?? '');
    const refined = String(payload?.refined_answer ?? payload?.answer ?? '');
    const notes = payload?.notes;
    __aiAnswerDraftResult = { original_answer: original, refined_answer: refined, notes, task: String(task || '') };

    __aiAnswerSetCompareText('aiAnswerOriginalText', original);
    __aiAnswerSetCompareText('aiAnswerRefinedText', refined);
    __aiSetMetrics('aiAnswerOriginalCount', __aiAnswerTextStats(original));
    __aiSetMetrics('aiAnswerRefinedCount', __aiAnswerTextStats(refined));
    __aiSetMetrics('aiAnswerCompareMeta', refined ? '检查无误后可替换到答案编辑器，未确认前不会改动原文。' : 'AI 未返回可用的优化后内容');

    const notesEl = document.getElementById('aiAnswerCompareNotes');
    if (notesEl) {
        const notesText = Array.isArray(notes) ? notes.filter(Boolean).join('\n') : String(notes ?? '').trim();
        notesEl.textContent = notesText ? `备注：${notesText}` : '';
        notesEl.classList.toggle('d-none', !notesText);
    }

    const panel = document.getElementById('aiAnswerComparePanel');
    if (panel) {
        panel.classList.remove('d-none');
        panel.scrollTop = 0;
    }
    __aiAnswerSetReviewMode(true);
}

function aiAnswerApplyDraft() {
    const refined = String(__aiAnswerDraftResult?.refined_answer || '').trim();
    if (!refined) {
        alert('AI 优化后内容为空，无法替换');
        return;
    }
    __kbAnswerSetMarkdown(refined, { from: 'aiAnswerApplyDraft' });
    __aiAnswerHideCompare();
    __aiSetMetrics('aiAnswerStatus', '已替换为 AI 优化后内容');
}
window.aiAnswerApplyDraft = aiAnswerApplyDraft;

function aiAnswerCancelDraft() {
    __aiAnswerHideCompare();
    __aiSetMetrics('aiAnswerStatus', '已取消 AI 结果');
}
window.aiAnswerCancelDraft = aiAnswerCancelDraft;

function __aiSetAnswerButtonsLoading(isLoading, activeTask = null) {
    const ids = ['aiAnswerBtnStructure', 'aiAnswerBtnFault', 'aiAnswerBtnUsage', 'aiAnswerBtnFeature'];
    ids.forEach(id => {
        const btn = document.getElementById(id);
        if (!btn) return;
        if (!btn.dataset.origText) btn.dataset.origText = btn.textContent || '';
        btn.disabled = !!isLoading;
        btn.classList.toggle('ai-loading', !!isLoading);

        if (isLoading) {
            const btnTask = btn.getAttribute('data-ai-answer-task');
            if (activeTask && btnTask === activeTask) {
                btn.textContent = 'AI 处理中...';
            }
        } else {
            btn.textContent = btn.dataset.origText || btn.textContent;
        }
    });
}

function openFeedbackModal(title, message) {
    const modal = document.getElementById('feedbackModal');
    const tEl = document.getElementById('feedbackTitle');
    const mEl = document.getElementById('feedbackMessage');
    if (!modal || !tEl || !mEl) {
        alert((title ? title + '\n' : '') + (message || ''));
        return;
    }
    tEl.textContent = title || '提示';
    mEl.textContent = message || '';
    modal.style.display = 'block';
}

function closeFeedbackModal() {
    const modal = document.getElementById('feedbackModal');
    if (modal) modal.style.display = 'none';
}

// Allow closing feedback modal by clicking on the dimmed backdrop.
document.addEventListener('click', (e) => {
    const modal = document.getElementById('feedbackModal');
    if (!modal || modal.style.display === 'none') return;
    if (e.target === modal) {
        closeFeedbackModal();
    }
});
window.closeFeedbackModal = closeFeedbackModal;

async function copyAnswerPrompts() {
    const get = (id) => (document.getElementById(id)?.value || '').trim();
    const structure = get('aiPromptAnswerStructureInput');
    const fault = get('aiPromptAnswerFaultInput');
    const usage = get('aiPromptAnswerUsageInput');
    const feature = get('aiPromptAnswerFeatureInput');

    const content =
        "【通用处理（structure）】\n" + structure + "\n\n" +
        "【故障类处理（fault）】\n" + fault + "\n\n" +
        "【使用类处理（usage）】\n" + usage + "\n\n" +
        "【功能类处理（feature）】\n" + feature + "\n";

    if (!content.trim()) {
        openFeedbackModal('复制失败', '没有可复制的内容');
        return;
    }

    try {
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            await navigator.clipboard.writeText(content);
        } else {
            // fallback for older browsers / insecure contexts
            const ta = document.createElement('textarea');
            ta.value = content;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            ta.style.top = '0';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            const ok = document.execCommand('copy');
            document.body.removeChild(ta);
            if (!ok) throw new Error('execCommand(copy) failed');
        }
        openFeedbackModal('复制成功', '已复制到剪贴板');
    } catch (e) {
        openFeedbackModal('复制失败', '复制失败：' + (e?.message || String(e)));
    }
}
window.copyAnswerPrompts = copyAnswerPrompts;

function __aiGetUrlsList(form) {
    const all = [];
    const opts = { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true };
    const keys = ['image_urls', 'video_urls', 'file_urls'];
    keys.forEach(k => {
        const v = (form?.elements?.[k]?.value || '').trim();
        if (!v) return;
        all.push(...parseSmartListValue(v, opts));
    });
    const linkVal = (form?.elements?.['link_url']?.value || '').trim();
    if (linkVal) {
        all.push(...parseSmartListValue(linkVal, opts));
    }
    const out = [];
    const seen = new Set();
    all.forEach(u => {
        const s = String(u || '').trim();
        if (!s) return;
        if (seen.has(s)) return;
        seen.add(s);
        out.push(s);
    });
    return out;
}

function aiQuestionAction(task) {
    (async () => {
        const form = __aiGetKbEditForm();
        if (!form) return;
        const qEl = form.elements['question'];
        if (!qEl) return;

        const jsonActionsEl = document.getElementById('aiQuestionJsonActions');
        if (jsonActionsEl) jsonActionsEl.style.display = 'none';

        __aiSetMetrics('aiQuestionMetrics', 'AI 处理中...');
        try {
            const res = await __aiOptimize('question', task, { question: qEl.value });
            if (!res || !res.success) throw new Error(res?.message || 'AI 调用失败');
            const data = res.data || {};
            const m = res.metrics || {};

            // 现在仅支持 “AI 润色”（rewrite），不再做相似度/Flesch 阈值拦截
            if (task === 'rewrite' || task === 'grammar') {
                // 题区 Prompt 期望 before/after/question/notes 结构，这里直接把 JSON 展示给用户并提供按钮选择
                const text = JSON.stringify(data, null, 2);
                qEl.value = text;
                qEl.dispatchEvent(new Event('input', { bubbles: true }));
                if (jsonActionsEl) jsonActionsEl.style.display = 'flex';
                __aiSetMetrics('aiQuestionMetrics', '已返回结构化结果');
                return;
            }
        } catch (e) {
            __aiSetMetrics('aiQuestionMetrics', '');
            alert('AI 处理失败: ' + e.message);
        }
    })();
}
window.aiQuestionAction = aiQuestionAction;

function aiQuestionApplyJson(useAfter) {
    try {
        const form = __aiGetKbEditForm();
        if (!form) return;
        const qEl = form.elements['question'];
        if (!qEl) return;
        const raw = qEl.value || '';
        let obj = null;
        try {
            obj = JSON.parse(raw);
        } catch (e) {
            alert('当前问题内容不是合法的 JSON，无法执行操作');
            return;
        }
        if (!obj || typeof obj !== 'object') {
            alert('JSON 结构不正确，缺少 before/after 字段');
            return;
        }
        const before = typeof obj.before === 'string' ? obj.before : '';
        const after = typeof obj.after === 'string' ? obj.after : '';
        const target = useAfter ? after : before;
        if (!target) {
            alert('JSON 中未找到可用的 ' + (useAfter ? 'after' : 'before') + ' 字段');
            return;
        }
        qEl.value = target;
        qEl.dispatchEvent(new Event('input', { bubbles: true }));
        const jsonActionsEl = document.getElementById('aiQuestionJsonActions');
        if (jsonActionsEl) jsonActionsEl.style.display = 'none';
    } catch (e) {
        alert('操作失败: ' + e.message);
    }
}
window.aiQuestionApplyJson = aiQuestionApplyJson;

function aiQuestionTypeAction() {
    (async () => {
        const form = __aiGetKbEditForm();
        if (!form) return;
        const qEl = form.elements['question'];
        const qtEl = form.elements['question_type'];
        const productEl = form.elements['product_category_name'];
        if (!qEl || !qtEl) return;

        __aiSetMetrics('aiQuestionTypeMetrics', 'AI 处理中...');
        try {
            const res = await __aiOptimize('question_type', 'classify', {
                question: qEl.value || '',
                product_category_name: productEl?.value || ''
            });
            if (!res || !res.success) throw new Error(res?.message || 'AI 调用失败');
            const data = res.data || {};
            if (typeof data.question_type === 'string' && data.question_type.trim()) {
                qtEl.value = data.question_type.trim();
                qtEl.dispatchEvent(new Event('input', { bubbles: true }));
                __aiSetMetrics('aiQuestionTypeMetrics', '已完成分类');
            } else {
                __aiSetMetrics('aiQuestionTypeMetrics', 'AI 未返回可用结果');
            }
        } catch (e) {
            __aiSetMetrics('aiQuestionTypeMetrics', '');
            alert('AI 分类失败: ' + e.message);
        }
    })();
}
window.aiQuestionTypeAction = aiQuestionTypeAction;

function aiAnswerAction(task) {
    (async () => {
        const form = __aiGetKbEditForm();
        if (!form) return;
        const qEl = form.elements['question'];
        const aEl = form.elements['answer'];
        const fileUrlsEl = form.elements['file_urls'];
        if (!aEl) return;
        try { __kbAnswerSyncToTextarea({ emit: false }); } catch {}
        const originalAnswerBeforeAi = String(aEl.value || '');

        // 每次调用 AI 前先隐藏 JSON 操作按钮
        const jsonActionsEl = document.getElementById('aiAnswerJsonActions');
        if (jsonActionsEl) jsonActionsEl.style.display = 'none';
        __aiAnswerHideCompare();

        __aiSetMetrics('aiAnswerStatus', 'AI 处理中...');
        __aiSetAnswerButtonsLoading(true, task);
        __aiStreamPreviewReset();
        __aiStreamPreviewSetVisible(true);
        try {
            const finalEvt = await __aiOptimizeStream('answer', task, {
                question: qEl?.value || '',
                answer: aEl.value || '',
                urls: __aiGetUrlsList(form)
            }, {}, (evt) => {
                if (!evt || !evt.type) return;
                if (evt.type === 'delta' && typeof evt.text === 'string') {
                    __aiStreamPreviewAppend(evt.text);
                }
                if (evt.type === 'status' && typeof evt.message === 'string') {
                    __aiSetMetrics('aiAnswerStatus', evt.message);
                }
            });

            if (!finalEvt || finalEvt.type === 'error') {
                throw new Error(finalEvt?.message || 'AI 流式调用失败');
            }

            const res = finalEvt.result;
            if (!res || !res.success) throw new Error(res?.message || 'AI 调用失败');
            const data = res.data || {};
            __aiSetMetrics('aiAnswerStatus', '已完成');

            const t = String(task || '').trim();
            const isJsonTask = (t === 'structure' || t === 'fault' || t === 'usage' || t === 'feature');
            if (isJsonTask) {
                const payload = {
                    original_answer: (typeof data.original_answer === 'string') ? data.original_answer : originalAnswerBeforeAi,
                    refined_answer: (typeof data.refined_answer === 'string') ? data.refined_answer : (typeof data.answer === 'string' ? data.answer : ''),
                    notes: (data.notes === undefined ? null : data.notes)
                };
                if (payload.refined_answer.trim()) {
                    __aiAnswerShowCompare(payload, t);
                } else {
                    __aiSetMetrics('aiAnswerStatus', 'AI 未返回可用结果');
                }
            } else if (typeof data.answer === 'string' && data.answer.trim()) {
                __aiAnswerShowCompare({
                    original_answer: originalAnswerBeforeAi,
                    refined_answer: data.answer,
                    notes: data.notes
                }, t);
            } else {
                __aiSetMetrics('aiAnswerStatus', 'AI 未返回可用结果');
            }
            if (fileUrlsEl && Array.isArray(data.urls) && data.urls.length) {
                const opts = { splitOnAsciiComma: true, splitOnChineseCommaWhenUrlList: true, isUrlList: true };
                const existing = parseSmartListValue(fileUrlsEl.value || '', opts);
                const merged = Array.from(new Set([...existing, ...data.urls.map(x => String(x).trim()).filter(Boolean)]));
                fileUrlsEl.value = merged.join('\n');
                fileUrlsEl.dispatchEvent(new Event('input', { bubbles: true }));
            }
        } catch (e) {
            __aiSetMetrics('aiAnswerStatus', '');
            alert('AI 处理失败: ' + e.message);
        } finally {
            __aiSetAnswerButtonsLoading(false);
            __aiStreamPreviewSetVisible(false);
        }
    })();
}
window.aiAnswerAction = aiAnswerAction;

function aiAnswerApplyJson(useRefined) {
    try {
        if (__aiAnswerDraftResult) {
            if (useRefined) aiAnswerApplyDraft();
            else aiAnswerCancelDraft();
            return;
        }
        const form = __aiGetKbEditForm();
        if (!form) return;
        const aEl = form.elements['answer'];
        if (!aEl) return;
        const raw = aEl.value || '';
        let obj = null;
        try {
            obj = JSON.parse(raw);
        } catch (e) {
            alert('当前内容不是合法的 JSON，无法执行操作');
            return;
        }
        if (!obj || typeof obj !== 'object') {
            alert('JSON 结构不正确，缺少 original_answer/refined_answer');
            return;
        }
        const original = typeof obj.original_answer === 'string' ? obj.original_answer : '';
        const refined = typeof obj.refined_answer === 'string' ? obj.refined_answer : '';
        const target = useRefined ? refined : original;
        if (!target) {
            alert('JSON 中未找到可用的 ' + (useRefined ? 'refined_answer' : 'original_answer') + ' 字段');
            return;
        }
        __kbAnswerSetMarkdown(target, { from: 'aiAnswerApplyJson' });
        const jsonActionsEl = document.getElementById('aiAnswerJsonActions');
        if (jsonActionsEl) jsonActionsEl.style.display = 'none';
    } catch (e) {
        alert('操作失败: ' + e.message);
    }
}
window.aiAnswerApplyJson = aiAnswerApplyJson;

function aiSimilarGenerate() {
    (async () => {
        if (__aiSimilarInFlight) return;
        const form = __aiGetKbEditForm();
        if (!form) return;
        const qEl = form.elements['question'];
        const panel = document.getElementById('aiSimilarPanel');
        const list = document.getElementById('aiSimilarList');
        if (!qEl || !panel || !list) return;
        const q = (qEl.value || '').trim();
        if (!q) {
            alert('请先填写问题');
            return;
        }

        const reqId = ++__aiSimilarReqSeq;
        __aiSimilarInFlight = true;
        window.__aiSimilarPanelVisible = true;
        panel.classList.remove('d-none');
        list.innerHTML = '';
        __aiSetMetrics('aiSimilarMetrics', 'AI 生成中...');

        try {
            const res = await __aiOptimize('similar', 'generate', { question: q }, {
                target_min: 0.75,
                target_max: 0.85,
                count_min: 3,
                count_max: 5,
                difficulty: (typeof window.__aiCurrentDifficulty === 'number') ? window.__aiCurrentDifficulty : null
            });
            if (reqId !== __aiSimilarReqSeq) return;
            if (!res || !res.success) throw new Error(res?.message || 'AI 调用失败');
            const items = Array.isArray(res.data?.items) ? res.data.items : [];
            const sims = Array.isArray(res.metrics?.cosine_sims) ? res.metrics.cosine_sims : [];
            const distinct = res.metrics?.distinct_ngram_ratio;
            __aiSetMetrics('aiSimilarMetrics', `相似度 ${res.metrics?.cosine_min?.toFixed?.(3) ?? ''}-${res.metrics?.cosine_max?.toFixed?.(3) ?? ''} | 多样性 ${(distinct ?? 0).toFixed?.(2) ?? ''}`);

            __aiSimilarDraftItems = items
                .map((it, idx) => ({
                    text: (it && typeof it.text === 'string') ? it.text.trim() : '',
                    difficulty: (it && typeof it.difficulty === 'number') ? it.difficulty : null,
                    sim: (typeof sims[idx] === 'number') ? sims[idx] : null
                }))
                .filter(x => x.text);

            if (__aiSimilarDraftItems.length === 0) {
                list.innerHTML = '<div class="text-muted" style="font-size:12px;">未生成有效相似问题</div>';
                return;
            }

            list.innerHTML = '';
            __aiSimilarDraftItems.forEach((it, idx) => {
                const row = document.createElement('div');
                row.className = 'ai-similar-item';
                const input = document.createElement('input');
                input.type = 'text';
                input.value = it.text;
                input.addEventListener('input', () => {
                    __aiSimilarDraftItems[idx].text = input.value;
                });
                const score = document.createElement('div');
                score.className = 'ai-similar-score';
                const simText = (typeof it.sim === 'number') ? it.sim.toFixed(3) : '--';
                score.textContent = `cos ${simText}`;
                row.appendChild(input);
                row.appendChild(score);
                list.appendChild(row);
            });
        } catch (e) {
            if (reqId !== __aiSimilarReqSeq) return;
            const isTimeout = String(e && (e.name || e.message) || '').toLowerCase().includes('abort');
            __aiSetMetrics('aiSimilarMetrics', isTimeout ? 'AI 超时，请重试' : '');
            alert('AI 生成失败: ' + (isTimeout ? '请求超时' : e.message));
        } finally {
            if (reqId === __aiSimilarReqSeq) __aiSimilarInFlight = false;
        }
    })();
}
window.aiSimilarGenerate = aiSimilarGenerate;

function aiSimilarApply() {
    const form = __aiGetKbEditForm();
    if (!form) return;
    const sqEl = form.elements['similar_questions'];
    if (!sqEl) return;
    const lines = (__aiSimilarDraftItems || []).map(x => String(x.text || '').trim()).filter(Boolean);
    if (lines.length < 3) {
        alert('没有可替换的相似问题');
        return;
    }
    sqEl.value = lines.join('\n');
    sqEl.dispatchEvent(new Event('input', { bubbles: true }));
    __aiSimilarDraftItems = lines.map(t => ({ text: t, difficulty: null, sim: null }));
    aiSimilarRefresh();
}
window.aiSimilarApply = aiSimilarApply;

function aiSimilarRefresh() {
    const form = __aiGetKbEditForm();
    if (!form) return;
    const sqEl = form.elements['similar_questions'];
    if (!sqEl) return;
    const panel = document.getElementById('aiSimilarPanel');
    const list = document.getElementById('aiSimilarList');
    if (!panel || !list) return;

    const lines = String(sqEl.value || '')
        .split('\n')
        .map(s => s.trim())
        .filter(Boolean);

    window.__aiSimilarPanelVisible = true;
    panel.classList.remove('d-none');
    __aiSimilarDraftItems = lines.map(t => ({ text: t, difficulty: null, sim: null }));
    list.innerHTML = '';
    __aiSimilarDraftItems.forEach((it, idx) => {
        const row = document.createElement('div');
        row.className = 'ai-similar-item';
        const input = document.createElement('input');
        input.type = 'text';
        input.value = it.text;
        input.addEventListener('input', () => {
            __aiSimilarDraftItems[idx].text = input.value;
        });
        const score = document.createElement('div');
        score.className = 'ai-similar-score';
        score.textContent = 'cos --';
        row.appendChild(input);
        row.appendChild(score);
        list.appendChild(row);
    });
    __aiSetMetrics('aiSimilarMetrics', lines.length ? `已刷新 ${lines.length} 条` : '相似问题为空');
}
window.aiSimilarRefresh = aiSimilarRefresh;

window.__aiDebouncedSimilarGenerate = __aiDebounce(aiSimilarGenerate, 900);

async function loadProductCatalogForModal() {
    const container = document.getElementById('productCheckboxes');
    if (!container) return;
    
    container.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">加载中...</div>';

    try {
        const res = await api('/kb/product_catalog');
        let catalog = res || {};
        
        // Ensure catalog is an object { Category: [Models] }
        if (Array.isArray(catalog)) {
            // Fallback if data is flat array
            catalog = { "未分类": catalog };
        } else if (res.data) {
             catalog = res.data;
        }
        
        container.innerHTML = '';
        
        // 1. Global Select All
        const globalSelectDiv = document.createElement('div');
        globalSelectDiv.className = 'product-select-all-global';
        
        const globalLabel = document.createElement('label');
        globalLabel.style.fontWeight = 'bold';
        globalLabel.style.display = 'flex';
        globalLabel.style.alignItems = 'center';
        globalLabel.style.gap = '8px';
        
        const globalCb = document.createElement('input');
        globalCb.type = 'checkbox';
        globalCb.id = 'globalSelectAll';
        globalCb.addEventListener('change', () => {
            if (window.toggleAllProducts) window.toggleAllProducts(globalCb.checked);
        });
        
        globalLabel.appendChild(globalCb);
        globalLabel.appendChild(document.createTextNode(' 全选'));
        globalSelectDiv.appendChild(globalLabel);
        container.appendChild(globalSelectDiv);

        // 2. Iterate Categories
        Object.keys(catalog).forEach(category => {
            const models = catalog[category];
            if (!Array.isArray(models) || models.length === 0) return;

            const section = document.createElement('div');
            section.className = 'product-category-section';
            
            // Category Header
            const header = document.createElement('h4');
            header.className = 'product-category-header';
            
            const headerLabel = document.createElement('label');
            headerLabel.style.display = 'flex';
            headerLabel.style.alignItems = 'center';
            headerLabel.style.gap = '8px';
            headerLabel.style.cursor = 'pointer';
            
            const headerCb = document.createElement('input');
            headerCb.type = 'checkbox';
            headerCb.className = 'category-select-all';
            headerCb.dataset.category = category;
            headerCb.addEventListener('change', () => {
                if (window.toggleCategoryProducts) window.toggleCategoryProducts(category, headerCb.checked);
            });
            
            headerLabel.appendChild(headerCb);
            headerLabel.appendChild(document.createTextNode(` ${category}`));
            header.appendChild(headerLabel);
            section.appendChild(header);

            // Product Grid
            const grid = document.createElement('div');
            grid.className = 'product-grid';
            
            models.forEach(model => {
                const item = document.createElement('div');
                item.className = 'product-checkbox-item';
                
                const label = document.createElement('label');
                label.title = model;
                
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.className = 'product-item-check';
                cb.name = 'product_name';
                cb.value = model;
                cb.dataset.category = category;
                cb.addEventListener('change', () => {
                    if (window.updateSelectAllStates) window.updateSelectAllStates();
                });
                
                const nameSpan = document.createElement('span');
                nameSpan.className = 'product-name';
                nameSpan.textContent = model;
                
                label.appendChild(cb);
                label.appendChild(nameSpan);
                item.appendChild(label);
                grid.appendChild(item);
            });
            section.appendChild(grid);
            container.appendChild(section);
        });

    } catch (e) {
        console.error(e);
        container.innerHTML = '<small class="text-danger">加载失败: ' + e.message + '</small>';
    }
}

window.renderExtraModels = function(models) {
    const container = document.getElementById('productCheckboxes');
    if (!container || !models || models.length === 0) return;
    
    // Check if extra section exists
    let extraSection = document.getElementById('extra-product-section');
    if (!extraSection) {
        extraSection = document.createElement('div');
        extraSection.id = 'extra-product-section';
        extraSection.className = 'product-category-section';
        extraSection.style.borderTop = '1px dashed #ccc';
        extraSection.style.marginTop = '15px';
        extraSection.style.paddingTop = '10px';
        
        const header = document.createElement('h4');
        header.className = 'product-category-header';
        header.innerHTML = `
            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; color: #d9534f;">
                <input type="checkbox" class="category-select-all" data-category="extra_legacy" onchange="toggleCategoryProducts('extra_legacy', this.checked)">
                非库内机型 (历史数据)
            </label>
        `;
        extraSection.appendChild(header);
        
        const grid = document.createElement('div');
        grid.className = 'product-grid';
        grid.id = 'extra-product-grid';
        extraSection.appendChild(grid);
        
        container.appendChild(extraSection);
    }
    
    const grid = document.getElementById('extra-product-grid');
    
    models.forEach(model => {
        // Avoid duplicates
        const exists = Array.from(grid.querySelectorAll('input.product-item-check')).some(cb => cb.value === model);
        if (exists) return;
        
        const item = document.createElement('div');
        item.className = 'product-checkbox-item';
        
        const label = document.createElement('label');
        label.title = model;
        label.style.color = '#666';
        
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'product-item-check';
        cb.name = 'product_name';
        cb.value = model;
        cb.dataset.category = 'extra_legacy';
        cb.addEventListener('change', () => {
            if (window.updateSelectAllStates) window.updateSelectAllStates();
        });
        
        const nameSpan = document.createElement('span');
        nameSpan.className = 'product-name';
        nameSpan.textContent = model;
        
        label.appendChild(cb);
        label.appendChild(nameSpan);
        item.appendChild(label);
        grid.appendChild(item);
    });
};

// Helper functions for Product Checkboxes
window.updateProductNameInput = function() {
    const checkedProducts = Array.from(document.querySelectorAll('#productCheckboxes input.product-item-check:checked'))
        .map(cb => cb.value)
        .filter(v => v); // Filter out empty strings if any
        
    const input = document.getElementById('kbEditProductName');
    if (input) {
        input.value = checkedProducts.join(',');
        // Keep dependent UI in sync (e.g. "已选 X 个", dirty state).
        try {
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        } catch {}
    }
};

window.toggleAllProducts = function(checked) {
    document.querySelectorAll('#productCheckboxes input[type="checkbox"]').forEach(cb => {
        cb.checked = checked;
    });
    window.updateProductNameInput();
};

window.toggleCategoryProducts = function(category, checked) {
    // Select both the category checkbox and all product checkboxes in that category
    const catCb = document.querySelector(`.category-select-all[data-category="${category}"]`);
    if (catCb) catCb.checked = checked;

    document.querySelectorAll(`#productCheckboxes input.product-item-check[data-category="${category}"]`).forEach(cb => {
        cb.checked = checked;
    });
    
    // Update global select all state
    const globalCheckbox = document.getElementById('globalSelectAll');
    if (globalCheckbox) {
        const allProducts = document.querySelectorAll('.product-item-check');
        const allChecked = Array.from(allProducts).every(p => p.checked);
        const someChecked = Array.from(allProducts).some(p => p.checked);
        globalCheckbox.checked = allChecked;
        globalCheckbox.indeterminate = someChecked && !allChecked;
    }
    window.updateProductNameInput();
};

window.updateSelectAllStates = function() {
    // 1. Update Category Select Alls
    document.querySelectorAll('.product-category-section').forEach(section => {
        const catCheckbox = section.querySelector('.category-select-all');
        if (!catCheckbox) return;
        
        const category = catCheckbox.dataset.category;
        const products = section.querySelectorAll('.product-item-check');
        if (products.length === 0) return;
        
        const allChecked = Array.from(products).every(p => p.checked);
        const someChecked = Array.from(products).some(p => p.checked);
        
        catCheckbox.checked = allChecked;
        catCheckbox.indeterminate = someChecked && !allChecked;
    });
    
    // 2. Update Global Select All
    const globalCheckbox = document.getElementById('globalSelectAll');
    if (globalCheckbox) {
        const allProducts = document.querySelectorAll('.product-item-check');
        if (allProducts.length > 0) {
            const allChecked = Array.from(allProducts).every(p => p.checked);
            const someChecked = Array.from(allProducts).some(p => p.checked);
            globalCheckbox.checked = allChecked;
            globalCheckbox.indeterminate = someChecked && !allChecked;
        }
    }
    window.updateProductNameInput();
};

function __kbParseTagNames(input) {
    const s = String(input ?? '').trim();
    if (!s) return [];
    const parts = s.split(/[\n,，]/).map(x => String(x ?? '').trim()).filter(Boolean);
    const out = [];
    const seen = new Set();
    parts.forEach(p => {
        if (!seen.has(p)) {
            seen.add(p);
            out.push(p);
        }
    });
    return out;
}

async function saveKBItem() {
    const { data, tagNames } = __kbEditBuildSubmitPayload();
    
    const btn = document.getElementById('saveKBItemBtn');
    __kbEditSaving = true;
    btn.disabled = true;
    btn.innerText = '保存中...';
    
    try {
        if (!navigator.onLine) {
            __kbEditQueuePendingSync({ data, tagNames });
            __kbEditSaveDraftNow();
            __kbEditSetDraftStatus('pending_sync');
            showToast('当前离线，已保存到本地并将在联网后自动同步');
            return;
        }
        const res = await api('/kb/update', 'POST', data);
        
        // 调试日志：输出完整响应
        console.log('[DEBUG] KB Update Response:', res);
        console.log('[DEBUG] Response Keys:', Object.keys(res || {}));
        console.log('[DEBUG] res.success:', res.success);
        console.log('[DEBUG] typeof res.success:', typeof res.success);
        
        if (!res.success) {
            const errorMsg = res.message || res.error || '未知错误';
            console.error('[DEBUG] Save Failed:', errorMsg);
            console.error('[DEBUG] Full Response:', JSON.stringify(res, null, 2));
            alert('保存失败: ' + errorMsg);
            return;
        }
        
        console.log('[DEBUG] Save Success!');

        // Sync KB tags after saving row content (even when no_change=true)
        const savedWikiId = String(res.question_wiki_id || data.question_wiki_id || '').trim();
        if (savedWikiId) {
            try {
                const tr = await api('/kb/item/tags', 'PUT', {
                    libraryType: 'current',
                    question_wiki_id: savedWikiId,
                    tagNames
                });
                if (!tr || !tr.success) {
                    showToast('保存标签失败: ' + (tr?.message || '未知错误'), 'error');
                } else {
                    // Refresh tag dictionary so the filter dropdown can show newly created tags immediately.
                    try { await fetchKBAllTags(); } catch {}
                }
            } catch (e) {
                showToast('保存标签异常: ' + e.message, 'error');
            }
        }

        // 检查是否有警告信息
        if (res.warning) {
            showToast(res.warning, 'warning');
        }

        if (res.no_change) {
            showToast('未检测到字段变化，无需保存内容，但已尝试更新标签');
        } else {
            openFeedbackModal('保存成功', '当前知识库条目已保存。');
        }

        __kbEditTouched = false;
        __kbEditInitialDigest = __kbEditCollectDigest();
        __kbEditClearDraft(__kbEditDraftContextId);
        const qualityContext = __kbEditQualityContext;
        closeKBEditModal({ force: true });
        // 保存后必须清空分页缓存，否则会继续命中旧数据导致“预览未更新”。
        clearKBCache();
        if (qualityContext && typeof qcLoadTasks === 'function') {
            await qcLoadTasks(qcTaskPage);
            await qcLoadRawIssues(qcRawPage);
        } else {
            await loadKBTable(kbCurrentPage);
        }
        if (typeof loadModifications === 'function') loadModifications(1);
    } catch (e) {
        alert('保存异常: ' + e.message);
    } finally {
        __kbEditSaving = false;
        btn.disabled = false;
        btn.innerText = '保存';
    }
}

// ==========================================
// Export Logic
// ==========================================

function openExportModal() {
    const modal = document.getElementById('exportModal');
    if (!modal) return;
    
    // Update selected count
    const countSpan = document.getElementById('exportSelectedCount');
    if (countSpan) {
        countSpan.innerText = `(${selectedKBRows.size} 条)`;
    }
    
    // Check/Uncheck "Selected" radio based on selection
    const selectedRadio = document.getElementById('exportSelectedRadio');
    const allRadio = document.querySelector('input[name="exportScope"][value="all"]');
    
    if (selectedKBRows.size > 0) {
        if (selectedRadio) {
            selectedRadio.disabled = false;
            selectedRadio.checked = true;
        }
    } else {
        if (selectedRadio) {
            selectedRadio.disabled = true;
            selectedRadio.checked = false;
        }
        if (allRadio) allRadio.checked = true;
    }
    
    // Generate Column Checkboxes
    const colContainer = document.getElementById('columnSelector');
    if (colContainer) {
        colContainer.innerHTML = '';
        kbColumns.forEach(col => {
            if (col.key === 'checkbox') return; // Skip checkbox column
            
            const label = document.createElement('label');
            label.className = 'checkbox-label';
            label.style.display = 'block';
            label.style.marginBottom = '5px';
            
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.value = col.field || col.key; // Use field name for backend
            cb.checked = col.visible !== false; // Default to visible columns
            cb.dataset.title = col.title;
            
            label.appendChild(cb);
            label.appendChild(document.createTextNode(' ' + col.title));
            colContainer.appendChild(label);
        });
    }
    
    // Initialize column selector visibility
    toggleExportCols();
    
    modal.style.display = 'block';
}

function closeExportModal() {
    const modal = document.getElementById('exportModal');
    if (modal) modal.style.display = 'none';
}

function toggleExportCols() {
    const selectedColsRadio = document.querySelector('input[name="exportCols"][value="selected"]');
    const colSelector = document.getElementById('columnSelector');
    
    if (selectedColsRadio && selectedColsRadio.checked) {
        if (colSelector) colSelector.style.display = 'block';
    } else {
        if (colSelector) colSelector.style.display = 'none';
    }
}

function confirmExport() {
    // 1. Get Scope
    const scope = document.querySelector('input[name="exportScope"]:checked')?.value || 'all';
    
    // 2. Get Columns
    const colScope = document.querySelector('input[name="exportCols"]:checked')?.value || 'all';
    let columns = '*';
    
    if (colScope === 'selected') {
        const checkedCols = Array.from(document.querySelectorAll('#columnSelector input:checked'))
            .map(cb => cb.value);
        
        if (checkedCols.length === 0) {
            alert('请至少选择一列导出');
            return;
        }
        columns = checkedCols.join(',');
    }
    
    // 3. Build Query Params
    const params = new URLSearchParams();
    
    // Common Filters (same as loadKBTable)
    const tableInputs = document.querySelectorAll('input[name="kbTable"]');
    let table = 'knowledge_base_v1';
    tableInputs.forEach(input => { if (input.checked) table = input.value; });
    params.append('table', table);
    
    // Only apply filters if exporting ALL (filtered results)
    // If exporting SELECTED, we just use IDs
    
    if (scope === 'selected') {
        if (selectedKBRows.size === 0) {
            alert('未选择任何数据');
            return;
        }
        // Use 'in.(id1,id2)' format for PostgREST if supported, or just pass comma separated
        // The backend updated code handles comma separated list in 'ids' param
        const ids = Array.from(selectedKBRows).join(',');
        params.append('ids', ids);
    } else {
        // Export All (Filtered)
        const id = document.getElementById('idSearch').value.trim();
        const product = document.getElementById('productNameSearch').value.trim();
        const question = document.getElementById('questionSearch').value.trim();
        const similarQuestion = document.getElementById('similarQuestionSearch') ? document.getElementById('similarQuestionSearch').value.trim() : '';
        const answer = document.getElementById('answerSearch').value.trim();
        
        const statusChips = document.querySelectorAll('#reviewStatusChips .tag-chip.active');
        const statuses = Array.from(statusChips).map(chip => chip.dataset.value);
        
        if (id) params.append('id', id);
        if (product) params.append('product', product);
        if (question) params.append('question', question);
        if (similarQuestion) params.append('similar_question', similarQuestion);
        if (answer) params.append('answer', answer);
        if (statuses.length > 0) params.append('review_status', statuses.join(','));
    }
    
    // Columns
    if (columns !== '*') {
        params.append('columns', columns);
    }
    
    // Trigger Download
    const url = `/api/kb/export?${params.toString()}`;
    window.open(url, '_blank');
    
    closeExportModal();
}

// ==========================================
// Matrix View Logic (Preserved)
// ==========================================
let matrixProductCategoryFilter = '';
let matrixMappingCategoryFilter = '';
let matrixColumnModelSelected = new Set();
let matrixAllModels = [];
let matrixColumnModelUIBound = false;
let matrixPendingChanges = new Map();
let matrixSubmitOperationId = null;
let matrixSubmitInFlight = false;
let matrixSubmitAttempt = 0;
let matrixMarkFilter = { modified: true, unmodified: true };
let currentMatrixSubmitLogDetails = [];

function matrixRandomId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        return window.crypto.randomUUID();
    }
    return 'op_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 10);
}

function matrixChangeKey(wikiId, productName) {
    return `${String(wikiId || '').trim()}::${String(productName || '').trim()}`;
}

function recordMatrixPendingChange(change) {
    const wikiId = String(change.question_wiki_id || '').trim();
    const productName = String(change.product_name || '').trim();
    const key = matrixChangeKey(wikiId, productName);
    if (!wikiId || !productName) return;
    
    const prev = matrixPendingChanges.get(key);
    if (!prev) {
        matrixPendingChanges.set(key, {
            question_wiki_id: wikiId,
            product_name: productName,
            old_is_configured: !!change.old_is_configured,
            new_is_configured: !!change.new_is_configured,
            edit_source: change.edit_source || '',
            updated_at: Date.now()
        });
        return;
    }
    
    prev.new_is_configured = !!change.new_is_configured;
    if (change && Object.prototype.hasOwnProperty.call(change, 'override_old') && change.override_old === true) {
        prev.old_is_configured = !!change.old_is_configured;
    }
    if (change.edit_source) prev.edit_source = change.edit_source;
    prev.updated_at = Date.now();
    
    if (prev.old_is_configured === prev.new_is_configured) {
        matrixPendingChanges.delete(key);
    }
}

function setMatrixSubmitButtonLoading(isLoading) {
    const btnSelected = document.getElementById('matrixSubmitChangesBtn');
    const btnAll = document.getElementById('matrixSubmitAllChangesBtn');
    const selectedText = '提交已选修改';
    const allText = '提交全量修改';
    const loadingHtml = '<span class="spinner-border spinner-border-sm"></span> 提交中...';
    
    if (btnSelected) {
        btnSelected.disabled = isLoading;
        btnSelected.innerHTML = isLoading ? loadingHtml : selectedText;
    }
    if (btnAll) {
        btnAll.disabled = isLoading;
        btnAll.innerHTML = isLoading ? loadingHtml : allText;
    }
}

function validateMatrixPendingChanges(changes) {
    const errors = [];
    if (!Array.isArray(changes) || changes.length === 0) {
        errors.push('没有可提交的修改。');
        return { ok: false, errors };
    }
    
    changes.forEach((c, idx) => {
        const prefix = `第 ${idx + 1} 条`;
        if (!c || typeof c !== 'object') {
            errors.push(`${prefix}: 记录格式非法`);
            return;
        }
        if (!c.question_wiki_id || !String(c.question_wiki_id).trim()) errors.push(`${prefix}: 缺少 question_wiki_id`);
        if (!c.product_name || !String(c.product_name).trim()) errors.push(`${prefix}: 缺少 product_name`);
        if (typeof c.old_is_configured !== 'boolean') errors.push(`${prefix}: old_is_configured 必须是布尔值`);
        if (typeof c.new_is_configured !== 'boolean') errors.push(`${prefix}: new_is_configured 必须是布尔值`);
        if (c.old_is_configured === c.new_is_configured) errors.push(`${prefix}: 修改前后无差异`);
    });
    
    const uniqKeys = new Set(changes.map(c => matrixChangeKey(c.question_wiki_id, c.product_name)));
    if (uniqKeys.size !== changes.length) errors.push('存在重复的 (question_wiki_id, product_name) 组合，请刷新后重试。');
    
    return { ok: errors.length === 0, errors };
}

function collectMatrixMismatchChangesFromCurrentView() {
    const out = [];
    const seen = new Set();
    const cols = Array.isArray(matrixColumns) ? matrixColumns : [];
    const rows = Array.isArray(currentMatrixData) ? currentMatrixData : [];
    rows.forEach(row => {
        const wid = String(row?.question_wiki_id || '').trim();
        if (!wid) return;
        const source = row?.source_products;
        if (!Array.isArray(source)) return;
        const sourceSet = toMatrixNormalizedStringSet(source);
        cols.forEach(prod => {
            const prodKey = String(prod ?? '').trim();
            if (!prodKey) return;
            const cellData = row?.products?.[prodKey];
            const currentConfigured = !!(cellData && cellData.is_configured);
            const sourceConfigured = sourceSet.has(normalizeMatrixProductName(prodKey));
            if (currentConfigured === sourceConfigured) return;
            const editSource = normalizeMatrixEditSource(cellData);
            if (editSource !== 'cell' && editSource !== 'bulk') return;
            const key = matrixChangeKey(wid, prodKey);
            if (seen.has(key)) return;
            seen.add(key);
            out.push({
                question_wiki_id: wid,
                product_name: prodKey,
                old_is_configured: !!sourceConfigured,
                new_is_configured: !!currentConfigured,
                edit_source: editSource,
                override_old: true
            });
        });
    });
    return out;
}

async function submitMatrixChanges() {
    if (matrixSubmitInFlight) return;
    if (!selectedMatrixRows || selectedMatrixRows.size === 0) {
        alert('请先勾选要提交的行（行内出现🟢/🔴的机型才会被提交）');
        return;
    }
    
    matrixSubmitInFlight = true;
    setMatrixSubmitButtonLoading(true);
    
    try {
        const preview = await api('/matrix/mismatch_changes', 'POST', {
            wiki_ids: Array.from(selectedMatrixRows)
        });
        if (!preview || !preview.success) {
            throw new Error((preview && (preview.message || preview.error)) || '获取待提交修改失败');
        }
        const changes = Array.isArray(preview.changes) ? preview.changes : [];
        if (changes.length === 0) {
            showToast('选中行没有可提交的🟢/🔴修改', 'warning');
            return;
        }

        const affectedCount = Number.isFinite(preview.affected_wiki_ids_count)
            ? preview.affected_wiki_ids_count
            : new Set(changes.map(c => String(c?.question_wiki_id || '').trim()).filter(Boolean)).size;
        
        if (!confirm(`将提交选中行中的 🟢/🔴 修改：${changes.length} 格（涉及 ${affectedCount} 条知识条目）。\n确认继续？`)) {
            return;
        }
        
        const submitRes = await submitMatrixChangesInBatches(changes, {
            onProgress: (doneBatches, totalBatches) => {
                const btn = document.getElementById('matrixSubmitChangesBtn');
                if (btn) btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> 提交中 (${doneBatches}/${totalBatches})...`;
            }
        });
        
        showToast(`提交完成：${changes.length} 格（涉及 ${affectedCount} 条知识条目）`, 'success');
        if (submitRes && Array.isArray(submitRes.warnings) && submitRes.warnings.length > 0) {
            showToast(`提交完成，但修改记录写入有告警：${submitRes.warnings[0]}`, 'warning');
        }
        if (typeof loadModifications === 'function') loadModifications(1);
    } catch (e) {
        showToast('提交异常: ' + e.message, 'error');
    } finally {
        matrixSubmitInFlight = false;
        setMatrixSubmitButtonLoading(false);
    }
}

async function submitMatrixAllChanges() {
    if (matrixSubmitInFlight) return;
    matrixSubmitInFlight = true;
    setMatrixSubmitButtonLoading(true);
    
    try {
        const preview = await api('/matrix/mismatch_changes', 'POST', {});
        if (!preview || !preview.success) {
            throw new Error((preview && (preview.message || preview.error)) || '获取待提交修改失败');
        }
        const changes = Array.isArray(preview.changes) ? preview.changes : [];
        if (changes.length === 0) {
            showToast('全量没有可提交的🟢/🔴修改', 'warning');
            return;
        }

        const affectedCount = Number.isFinite(preview.affected_wiki_ids_count)
            ? preview.affected_wiki_ids_count
            : new Set(changes.map(c => String(c?.question_wiki_id || '').trim()).filter(Boolean)).size;
        
        if (!confirm(`将提交全量 🟢/🔴 修改：${changes.length} 格（涉及 ${affectedCount} 条知识条目）。\n确认继续？`)) {
            return;
        }
        
        const submitRes = await submitMatrixChangesInBatches(changes, {
            onProgress: (doneBatches, totalBatches) => {
                const btn = document.getElementById('matrixSubmitAllChangesBtn');
                if (btn) btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> 提交中 (${doneBatches}/${totalBatches})...`;
            }
        });
        
        showToast(`全量提交完成：${changes.length} 格（涉及 ${affectedCount} 条知识条目）`, 'success');
        if (submitRes && Array.isArray(submitRes.warnings) && submitRes.warnings.length > 0) {
            showToast(`全量提交完成，但修改记录写入有告警：${submitRes.warnings[0]}`, 'warning');
        }
        if (typeof loadModifications === 'function') loadModifications(1);
    } catch (e) {
        showToast('全量提交异常: ' + e.message, 'error');
    } finally {
        matrixSubmitInFlight = false;
        setMatrixSubmitButtonLoading(false);
    }
}

async function submitMatrixChangesInBatches(changes, opts = {}) {
    const list = Array.isArray(changes) ? changes : [];
    if (list.length === 0) return { warnings: [], operationIds: [] };

    const chunkSize = 800;
    const grouped = new Map();
    list.forEach(c => {
        const wid = String(c?.question_wiki_id || '').trim();
        if (!wid) return;
        if (!grouped.has(wid)) grouped.set(wid, []);
        grouped.get(wid).push(c);
    });

    const wikiIds = Array.from(grouped.keys()).sort();
    const batches = [];
    let current = [];
    let currentLen = 0;
    wikiIds.forEach(wid => {
        const group = grouped.get(wid) || [];
        if (group.length === 0) return;
        if (currentLen > 0 && currentLen + group.length > chunkSize) {
            batches.push(current);
            current = [];
            currentLen = 0;
        }
        if (group.length > chunkSize && currentLen === 0) {
            batches.push(group);
            return;
        }
        current.push(...group);
        currentLen += group.length;
    });
    if (currentLen > 0) batches.push(current);

    const totalBatches = batches.length;
    const warnings = [];
    const operationIds = [];
    for (let i = 0; i < batches.length; i++) {
        const batchIndex = i + 1;
        if (opts && typeof opts.onProgress === 'function') opts.onProgress(batchIndex, totalBatches);

        const batch = batches[i];
        const res = await api('/matrix/submit_changes', 'POST', {
            operation_id: matrixRandomId(),
            attempt: 1,
            changes: batch
        });
        
        if (!res || !res.success) {
            if (res && Array.isArray(res.errors) && res.errors.length > 0) {
                throw new Error(res.errors.join('\n'));
            }
            throw new Error((res && (res.message || res.error)) || '提交失败');
        }
        if (res.operation_id) operationIds.push(res.operation_id);
        if (Array.isArray(res.warnings) && res.warnings.length > 0) warnings.push(...res.warnings);
    }
    return { warnings, operationIds };
}

async function openMatrixSubmitLogsModal() {
    const modal = document.getElementById('matrixSubmitLogsModal');
    if (!modal) return;
    modal.style.display = 'block';
    await loadMatrixSubmitLogs();
}

function closeMatrixSubmitLogsModal() {
    const modal = document.getElementById('matrixSubmitLogsModal');
    if (modal) modal.style.display = 'none';
}

async function loadMatrixSubmitLogs() {
    const statusEl = document.getElementById('matrixSubmitLogsStatus');
    const tbody = document.getElementById('matrixSubmitLogsTbody');
    if (statusEl) statusEl.innerText = '加载中...';
    if (tbody) tbody.innerHTML = '';
    
    try {
        const res = await api('/matrix/submit_logs?limit=50');
        if (!res || !res.success) {
            if (statusEl) statusEl.innerText = '加载失败';
            return;
        }
        const rows = res.data || [];
        if (rows.length === 0) {
            if (statusEl) statusEl.innerText = '暂无日志';
            return;
        }
        if (statusEl) statusEl.innerText = `共 ${rows.length} 条`;
        
        if (!tbody) return;
        rows.forEach(r => {
            const tr = document.createElement('tr');
            const err = r.error_message ? escapeHtml(String(r.error_message)) : '';
            const opId = String(r.operation_id || '');
            tr.innerHTML = `
                <td style="font-family: monospace; font-size: 12px;">${escapeHtml(opId)}</td>
                <td>${escapeHtml(r.status || '')}</td>
                <td>${escapeHtml(String(r.attempts ?? ''))}</td>
                <td>${escapeHtml(r.created_by || '')}</td>
                <td style="max-width: 320px; white-space: normal;">${err}</td>
                <td style="font-size: 12px;">${escapeHtml((r.updated_at || r.created_at || '') + '')}</td>
                <td>
                    <button class="action-btn btn-sm" onclick="openMatrixSubmitLogDetailsModal('${_escapeAttr(opId)}')">明细</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        if (statusEl) statusEl.innerText = '加载异常: ' + e.message;
    }
}

function closeMatrixSubmitLogDetailsModal() {
    const modal = document.getElementById('matrixSubmitLogDetailsModal');
    if (modal) modal.style.display = 'none';
}

function _matrixSubmitStatusText(value) {
    return value ? '已配置' : '未配置';
}

function _buildMatrixSubmitDetailItem(item) {
    const beforeObj = (item && item.before && typeof item.before === 'object') ? item.before : {
        question: item?.question || '',
        answer: item?.answer || '',
        products: ''
    };
    const afterObj = (item && item.after && typeof item.after === 'object') ? item.after : {
        question: item?.question || '',
        answer: item?.answer || '',
        products: ''
    };
    return {
        kb_id: item?.question_wiki_id || '',
        question_wiki_id: item?.question_wiki_id || '',
        source_module: item?.source_module || '机型矩阵管理',
        modification_time: item?.submitted_at || '',
        before: beforeObj,
        after: afterObj,
        changed_fields: Array.isArray(item?.changed_fields) && item.changed_fields.length > 0 ? item.changed_fields : ['products']
    };
}

function openMatrixSubmitDetail(index) {
    const item = currentMatrixSubmitLogDetails[index];
    if (!item) return;
    _openModDetailsByItem(_buildMatrixSubmitDetailItem(item));
}
window.openMatrixSubmitDetail = openMatrixSubmitDetail;

async function openMatrixSubmitLogDetailsModal(operationId) {
    const opId = String(operationId || '').trim();
    if (!opId) return;
    const modal = document.getElementById('matrixSubmitLogDetailsModal');
    const metaEl = document.getElementById('matrixSubmitLogDetailsMeta');
    const statusEl = document.getElementById('matrixSubmitLogDetailsStatus');
    const tbody = document.getElementById('matrixSubmitLogDetailsTbody');
    currentMatrixSubmitLogDetails = [];
    if (metaEl) metaEl.textContent = `operation_id: ${opId}`;
    if (statusEl) statusEl.textContent = '加载中...';
    if (tbody) tbody.innerHTML = '';
    if (modal) modal.style.display = 'block';

    try {
        const res = await api(`/matrix/submit_logs/${encodeURIComponent(opId)}/details?limit=500`);
        if (!res || !res.success) {
            if (statusEl) statusEl.textContent = res?.message || '加载失败';
            return;
        }
        const rows = Array.isArray(res.data) ? res.data : [];
        currentMatrixSubmitLogDetails = rows;
        if (statusEl) {
            statusEl.textContent = `共 ${rows.length} 条按钮变更，涉及 ${res.affected_wiki_ids_count || 0} 条知识条目`;
        }
        if (!tbody) return;
        if (rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="empty-message">暂无明细</td></tr>';
            return;
        }
        rows.forEach((item, idx) => {
            const tr = document.createElement('tr');
            const qText = item?.question || '';
            tr.innerHTML = `
                <td style="font-family: monospace; font-size: 12px;">${escapeHtml(item?.question_wiki_id || '')}</td>
                <td>${tdRenderExpandableText(`matrix-submit-detail:${item?.question_wiki_id || idx}:question`, qText, { placeholder: '-' })}</td>
                <td>${escapeHtml(item?.product_name || '')}</td>
                <td>${escapeHtml(_matrixSubmitStatusText(!!item?.old_is_configured))}</td>
                <td>${escapeHtml(_matrixSubmitStatusText(!!item?.new_is_configured))}</td>
                <td>${escapeHtml(item?.edit_source || '-')}</td>
                <td>${escapeHtml(item?.submitted_by || '-')}</td>
                <td style="font-size: 12px;">${escapeHtml(item?.submitted_at ? new Date(item.submitted_at).toLocaleString() : '-')}</td>
                <td><button class="action-btn btn-sm" onclick="openMatrixSubmitDetail(${idx})">详情</button></td>
            `;
            tbody.appendChild(tr);
        });
        tdRefreshCellOverflow(document.getElementById('matrixSubmitLogDetailsTable') || document);
    } catch (e) {
        if (statusEl) statusEl.textContent = '加载异常: ' + e.message;
    }
}
window.openMatrixSubmitLogDetailsModal = openMatrixSubmitLogDetailsModal;
window.closeMatrixSubmitLogDetailsModal = closeMatrixSubmitLogDetailsModal;

function normalizeMatrixEditSource(cellData) {
    if (!cellData) return '';
    const src = (cellData.edit_source || '').toString().trim();
    if (src === 'cell' || src === 'bulk') return src;
    if (cellData.manual_edit) return 'cell';
    return '';
}

function normalizeMatrixProductName(value) {
    return String(value ?? '')
        .replace(/\u3000/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function canonicalMatrixProductName(value) {
    return normalizeMatrixProductName(value).toLowerCase().replace(/[\s\-_·・.。/\\()（）\[\]【】]+/g, '');
}

function toMatrixStringSet(list) {
    const s = new Set();
    (list || []).forEach(v => {
        const k = (v ?? '').toString().trim();
        if (k) s.add(k);
    });
    return s;
}

function toMatrixNormalizedStringSet(list) {
    const s = new Set();
    (list || []).forEach(v => {
        const k = normalizeMatrixProductName(v);
        if (k) s.add(k);
    });
    return s;
}

function setMatrixMarkFilter(kind, enabled) {
    const k = String(kind || '').toLowerCase();
    if (k !== 'modified' && k !== 'unmodified') return;
    matrixMarkFilter[k] = !!enabled;
    cancelMatrixSelection();
    loadMatrixData(1);
}

function buildMatrixMarkTotalPayload() {
    const id = document.getElementById('matrixSearchId')?.value.trim() || '';
    const q = document.getElementById('matrixSearchQuestion')?.value.trim() || '';
    const a = document.getElementById('matrixSearchAnswer')?.value.trim() || '';
    const pModels = Array.from(matrixSearchProductSelected);
    const columns = Array.isArray(matrixColumns) ? matrixColumns : [];

    const payload = {
        id,
        q,
        a,
        pc: matrixProductCategoryFilter || '',
        mc: matrixMappingCategoryFilter || '',
        col_models: matrixColumnModelSelected.size > 0 ? Array.from(matrixColumnModelSelected) : [],
        marks: { ...matrixMarkFilter },
        columns
    };

    if (pModels.length > 0) {
        payload.p_models = pModels;
        payload.p_mode = matrixProductMatchMode || 'any';
    }

    return payload;
}

async function refreshMatrixFilteredTotal() {
    matrixFilteredTotal = matrixTotal || 0;
}

function getMatrixRowMarkerFlags(row) {
    let hasGreen = false;
    let hasRed = false;
    let hasYellow = false;
    
    const cols = Array.isArray(matrixColumns) ? matrixColumns : [];
    const sourceAvailable = Array.isArray(row?.source_products);
    const prevAvailable = Array.isArray(row?.prev_products);
    
    const sourceSet = sourceAvailable ? toMatrixNormalizedStringSet(row.source_products) : new Set();
    const prevSet = prevAvailable ? toMatrixNormalizedStringSet(row.prev_products) : new Set();
    
    for (const prod of cols) {
        const prodKey = (prod ?? '').toString().trim();
        if (!prodKey) continue;
        const prodNorm = normalizeMatrixProductName(prodKey);
        
        if (sourceAvailable && prevAvailable) {
            if (sourceSet.has(prodNorm) !== prevSet.has(prodNorm)) {
                hasYellow = true;
            }
        }
        
        if (sourceAvailable) {
            const cellData = row?.products?.[prodKey];
            const currentConfigured = !!(cellData && cellData.is_configured);
            const sourceConfigured = sourceSet.has(prodNorm);
            if (currentConfigured !== sourceConfigured) {
                const src = normalizeMatrixEditSource(cellData);
                if (src === 'cell') hasRed = true;
                else if (src === 'bulk') hasGreen = true;
            }
        }
        
        if (hasGreen && hasRed && hasYellow) break;
    }
    
    return { hasGreen, hasRed, hasYellow };
}

function filterMatrixRowsByMarks(rows) {
    const list = Array.isArray(rows) ? rows : [];
    const wantModified = !!matrixMarkFilter.modified;
    const wantUnmodified = !!matrixMarkFilter.unmodified;
    const anyWanted = wantModified || wantUnmodified;
    if (!anyWanted) return [];
    if (wantModified && wantUnmodified) return list;

    return list.filter(r => {
        const f = getMatrixRowMarkerFlags(r);
        const isModified = !!f.hasGreen || !!f.hasRed;
        return wantModified ? isModified : !isModified;
    });
}

function renderMatrixCellHtml(isConfigured, editSource, showYellowDiff) {
    const statusHtml = isConfigured
        ? '<span class="matrix-cell-configured">✅</span>'
        : '<span class="matrix-cell-unconfigured">⚪</span>';
    
    const diffHtml = showYellowDiff
        ? '<span class="matrix-diff-icon" title="此刻库/前刻库机型不一致">🟡</span>'
        : '';
    
    if (editSource === 'cell') {
        return `${statusHtml}${diffHtml}<span class="matrix-origin-icon matrix-origin-cell" title="手动点击单格修改导致与同步源不一致">🔴</span>`;
    }
    if (editSource === 'bulk') {
        return `${statusHtml}${diffHtml}<span class="matrix-origin-icon matrix-origin-bulk" title="按钮修改导致与同步源不一致">🟢</span>`;
    }
    return `${statusHtml}${diffHtml}`;
}

function setMatrixChipActive(container, value) {
    container.querySelectorAll('.tag-chip').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.value === value);
    });
}

function renderMatrixChips(containerId, values, activeValue, onSelect) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    let normalizedValues = [];
    if (Array.isArray(values)) {
        normalizedValues = values;
    } else if (values && typeof values === 'object') {
        normalizedValues = Object.keys(values);
    }
    const uniq = Array.from(new Set((normalizedValues || []).filter(v => v && String(v).trim()))).map(v => String(v).trim());
    const allValue = '';
    
    container.innerHTML = '';

    if (uniq.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'matrix-empty-state';
        empty.innerText = '暂无分类项';
        container.appendChild(empty);
        return;
    }
    
    const makeChip = (label, value) => {
        const chip = document.createElement('div');
        chip.className = 'tag-chip' + (value === activeValue ? ' active' : '');
        chip.dataset.value = value;
        chip.innerText = label;
        chip.onclick = () => {
            onSelect(value);
            setMatrixChipActive(container, value);
        };
        return chip;
    };
    
    container.appendChild(makeChip('全部', allValue));
    uniq.forEach(v => container.appendChild(makeChip(v, v)));
}

function renderMatrixMappingCategorySelect(values, activeValue) {
    const select = document.getElementById('matrixMappingCategorySelect');
    if (!select) return;

    let normalizedValues = [];
    if (Array.isArray(values)) {
        normalizedValues = values;
    } else if (values && typeof values === 'object') {
        normalizedValues = Object.keys(values);
    }

    const uniq = Array.from(new Set((normalizedValues || []).filter(v => v && String(v).trim()))).map(v => String(v).trim());
    const currentValue = activeValue || '';
    select.innerHTML = '';

    const allOption = document.createElement('option');
    allOption.value = '';
    allOption.textContent = '全部映射分类';
    select.appendChild(allOption);

    uniq.forEach(v => {
        const option = document.createElement('option');
        option.value = v;
        option.textContent = v;
        select.appendChild(option);
    });

    select.value = uniq.includes(currentValue) ? currentValue : '';
}

let matrixProductMatchMode = 'any';
let matrixSearchProductSelected = new Set();
let matrixSearchProductUIBound = false;

function setMatrixProductMatchMode(mode) {
    const m = String(mode || '').toLowerCase();
    matrixProductMatchMode = (m === 'all') ? 'all' : 'any';
    const anyBtn = document.getElementById('matrixMatchModeAny');
    const allBtn = document.getElementById('matrixMatchModeAll');
    if (anyBtn) anyBtn.classList.toggle('active', matrixProductMatchMode === 'any');
    if (allBtn) allBtn.classList.toggle('active', matrixProductMatchMode === 'all');
    if (anyBtn) anyBtn.setAttribute('aria-pressed', matrixProductMatchMode === 'any' ? 'true' : 'false');
    if (allBtn) allBtn.setAttribute('aria-pressed', matrixProductMatchMode === 'all' ? 'true' : 'false');
    if (matrixSearchProductUIBound) loadMatrixData(1);
}

function setMatrixMarkFilterMode(mode) {
    const normalized = String(mode || 'all').toLowerCase();
    if (normalized === 'modified') {
        matrixMarkFilter = { modified: true, unmodified: false };
    } else if (normalized === 'unmodified') {
        matrixMarkFilter = { modified: false, unmodified: true };
    } else {
        matrixMarkFilter = { modified: true, unmodified: true };
    }

    const activeMode = matrixMarkFilter.modified && matrixMarkFilter.unmodified
        ? 'all'
        : (matrixMarkFilter.modified ? 'modified' : 'unmodified');

    const allBtn = document.getElementById('matrixStatusTabAll');
    const modifiedBtn = document.getElementById('matrixStatusTabModified');
    const unmodifiedBtn = document.getElementById('matrixStatusTabUnmodified');
    if (allBtn) allBtn.classList.toggle('active', activeMode === 'all');
    if (modifiedBtn) modifiedBtn.classList.toggle('active', activeMode === 'modified');
    if (unmodifiedBtn) unmodifiedBtn.classList.toggle('active', activeMode === 'unmodified');

    cancelMatrixSelection();
    loadMatrixData(1);
}

function parseMatrixProductSearchText(text) {
    const s = String(text || '').trim();
    if (!s) return [];
    if (!/[,\n，]/.test(s)) return [];
    const parts = s.split(/[,\n，]+/).map(x => x.trim()).filter(Boolean);
    return Array.from(new Set(parts));
}

function renderMatrixSearchProductSelectedChips() {
    const container = document.getElementById('matrixSearchProductSelectedChips');
    if (!container) return;
    container.innerHTML = '';
    const selected = Array.from(matrixSearchProductSelected);
    selected.forEach(model => {
        const chip = document.createElement('div');
        chip.className = 'tag-chip active';
        chip.style.display = 'inline-flex';
        chip.style.alignItems = 'center';
        chip.style.gap = '8px';
        const text = document.createElement('span');
        text.innerText = model;
        chip.appendChild(text);
        const close = document.createElement('span');
        close.innerText = '×';
        close.style.cursor = 'pointer';
        close.style.fontWeight = 'bold';
        close.onclick = (e) => {
            e.stopPropagation();
            matrixSearchProductSelected.delete(model);
            renderMatrixSearchProductSelectedChips();
            loadMatrixData(1);
        };
        chip.appendChild(close);
        container.appendChild(chip);
    });
}

function clearMatrixSearchProductFilter(load = true) {
    matrixSearchProductSelected.clear();
    renderMatrixSearchProductSelectedChips();
    const input = document.getElementById('matrixSearchProductInput');
    if (input) input.value = '';
    const dropdown = document.getElementById('matrixSearchProductDropdown');
    if (dropdown) dropdown.classList.remove('show');
    if (load) loadMatrixData(1);
}
window.clearMatrixSearchProductFilter = clearMatrixSearchProductFilter;
window.setMatrixMarkFilterMode = setMatrixMarkFilterMode;
window.setMatrixProductMatchMode = setMatrixProductMatchMode;

function toggleMatrixMoreMenu(button, event) {
    if (event) event.stopPropagation();
    const menu = button?.nextElementSibling;
    if (!menu) return;
    const shouldOpen = menu.classList.contains('d-none');
    document.querySelectorAll('#matrixView .matrix-more-menu').forEach(el => el.classList.add('d-none'));
    menu.classList.toggle('d-none', !shouldOpen);
}
window.toggleMatrixMoreMenu = toggleMatrixMoreMenu;

function closeMatrixMoreMenu(element) {
    const menu = element?.closest('.matrix-more-menu');
    if (menu) menu.classList.add('d-none');
}
window.closeMatrixMoreMenu = closeMatrixMoreMenu;

function openMatrixDiffComparePicker() {
    matrixDiffCompareEnabled = true;
    const btn = document.getElementById('matrixColumnModelDropdownBtn');
    if (btn) btn.click();
    const input = document.getElementById('matrixColumnModelInput');
    if (input) input.focus();
    renderMatrixTable();
}
window.openMatrixDiffComparePicker = openMatrixDiffComparePicker;

async function loadMatrixDiffCompareDataIfNeeded(selectedModels) {
    const models = Array.isArray(selectedModels) ? selectedModels.filter(Boolean) : [];
    if (!matrixDiffCompareEnabled || models.length < 2) return false;
    await loadMatrixData(1);
    return true;
}

function getMatrixDiffCompareModels() {
    return Array.from(matrixColumnModelSelected || []).filter(m => String(m || '').trim());
}

function isMatrixDiffCompareActive() {
    return matrixDiffCompareEnabled && getMatrixDiffCompareModels().length >= 2;
}

function getMatrixProductConfigured(row, productName) {
    const prodKey = String(productName || '').trim();
    const products = row && row.products ? row.products : {};
    const direct = products[prodKey];
    if (direct) return !!direct.is_configured;
    const targetNorm = normalizeMatrixProductName(prodKey);
    const matchedKey = Object.keys(products).find(key => normalizeMatrixProductName(key) === targetNorm);
    if (matchedKey) return !!(products[matchedKey] && products[matchedKey].is_configured);
    const targetCanonical = canonicalMatrixProductName(prodKey);
    const canonicalKey = Object.keys(products).find(key => canonicalMatrixProductName(key) === targetCanonical);
    if (canonicalKey) return !!(products[canonicalKey] && products[canonicalKey].is_configured);
    const sourceSet = toMatrixNormalizedStringSet(row?.source_products || []);
    if (sourceSet.has(targetNorm)) return true;
    const sourceCanonical = new Set((row?.source_products || []).map(canonicalMatrixProductName).filter(Boolean));
    return sourceCanonical.has(targetCanonical);
}

function getMatrixDiffMinorityModels(row, selectedModels) {
    const models = Array.isArray(selectedModels) ? selectedModels : [];
    const groups = new Map();
    models.forEach(model => {
        const key = getMatrixProductConfigured(row, model) ? '1' : '0';
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(model);
    });
    if (groups.size <= 1) return new Set();
    const sizes = Array.from(groups.values()).map(items => items.length);
    const minSize = Math.min(...sizes);
    const maxSize = Math.max(...sizes);
    if (minSize === maxSize) return new Set();
    const out = new Set();
    groups.forEach(items => {
        if (items.length === minSize) items.forEach(model => out.add(model));
    });
    return out;
}

function filterMatrixRowsForDiffCompare(rows, selectedModels) {
    const models = Array.isArray(selectedModels) ? selectedModels : [];
    if (models.length < 2) return Array.isArray(rows) ? rows : [];
    return (Array.isArray(rows) ? rows : []).filter(row => {
        const states = models.map(model => getMatrixProductConfigured(row, model));
        return new Set(states).size > 1;
    });
}

function updateMatrixDiffCompareNotice(active) {
    const el = document.getElementById('matrixDiffCompareNotice');
    if (!el) return;
    el.classList.toggle('d-none', !active);
}

function setupMatrixSearchProductFilterUI() {
    if (matrixSearchProductUIBound) return;
    const input = document.getElementById('matrixSearchProductInput');
    const btn = document.getElementById('matrixSearchProductDropdownBtn');
    const dropdown = document.getElementById('matrixSearchProductDropdown');
    const container = input?.closest('.input-with-dropdown') || input?.parentElement;
    if (!input || !btn || !dropdown || !container) return;

    function renderDropdown() {
        dropdown.innerHTML = '';
        const q = input.value.trim().toLowerCase();
        const selected = matrixSearchProductSelected;
        const filtered = (matrixAllModels || [])
            .filter(m => m && !selected.has(m))
            .filter(m => !q || String(m).toLowerCase().includes(q))
            .slice(0, 120);
        if (filtered.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'dropdown-item';
            empty.style.color = '#999';
            empty.style.cursor = 'default';
            empty.textContent = '没有可选机型';
            dropdown.appendChild(empty);
            return;
        }
        filtered.forEach(model => {
            const item = document.createElement('div');
            item.className = 'dropdown-item';
            item.textContent = model;
            item.onclick = (e) => {
                e.stopPropagation();
                matrixSearchProductSelected.add(model);
                input.value = '';
                renderMatrixSearchProductSelectedChips();
                renderDropdown();
                dropdown.classList.add('show');
                loadMatrixData(1);
                input.focus();
            };
            dropdown.appendChild(item);
        });
    }

    btn.onclick = (e) => {
        e.stopPropagation();
        e.preventDefault();
        const isVisible = dropdown.classList.contains('show');
        if (isVisible) {
            dropdown.classList.remove('show');
            container.classList.remove('is-open');
            return;
        }
        renderDropdown();
        dropdown.classList.add('show');
        container.classList.add('is-open');
        input.focus();
    };

    input.addEventListener('focus', () => {
        renderDropdown();
        dropdown.classList.add('show');
        container.classList.add('is-open');
    });

    input.addEventListener('input', () => {
        if (dropdown.classList.contains('show')) {
            renderDropdown();
        }
    });

    container.addEventListener('click', (e) => {
        if (e.target === input) return;
        input.focus();
        if (!dropdown.classList.contains('show')) {
            renderDropdown();
            dropdown.classList.add('show');
        }
    });

    document.addEventListener('click', (e) => {
        if (!container.contains(e.target) && !dropdown.contains(e.target) && e.target !== btn) {
            dropdown.classList.remove('show');
            container.classList.remove('is-open');
        }
    });

    matrixSearchProductUIBound = true;
    const matchModeSelect = document.getElementById('matrixMappingCategorySelect');
    if (matchModeSelect) {
        matchModeSelect.addEventListener('change', (e) => {
            matrixMappingCategoryFilter = e.target.value || '';
            loadMatrixData(1);
        });
    }
    renderMatrixSearchProductSelectedChips();
    setMatrixProductMatchMode(matrixProductMatchMode);
}

async function loadMatrixData(page = 1, options = {}) {
    const id = document.getElementById('matrixSearchId')?.value.trim() || '';
    const q = document.getElementById('matrixSearchQuestion').value.trim();
    const a = document.getElementById('matrixSearchAnswer')?.value.trim() || '';
    const pModels = Array.from(matrixSearchProductSelected);
    
    const params = new URLSearchParams({
        page: page,
        per_page: matrixPageSize,
        id: id,
        q: q,
        a: a
    });

    const wantModified = !!matrixMarkFilter.modified;
    const wantUnmodified = !!matrixMarkFilter.unmodified;
    params.append('mark_modified', wantModified ? '1' : '0');
    params.append('mark_unmodified', wantUnmodified ? '1' : '0');
    
    if (pModels.length > 0) {
        params.append('p_models', pModels.join(','));
        params.append('p_mode', matrixProductMatchMode || 'any');
    }
    
    if (matrixProductCategoryFilter) params.append('pc', matrixProductCategoryFilter);
    if (matrixMappingCategoryFilter) params.append('mc', matrixMappingCategoryFilter);
    if (matrixColumnModelSelected.size > 0) {
        params.append('col_models', Array.from(matrixColumnModelSelected).join(','));
    }
    if (isMatrixDiffCompareActive()) params.append('diff_compare', '1');

    const tbody = document.getElementById('matrixTableBody');
    if (!tbody) return;
    const requestKey = params.toString();
    if (options.reuse && matrixLoaded && matrixLastRequestKey === requestKey) {
        renderMatrixTable();
        updateMatrixPagination();
        refreshMatrixFilteredTotal();
        return;
    }
    tbody.innerHTML = '<tr><td colspan="100" class="empty-message">加载中...</td></tr>';

    try {
        await ensureMatrixAllModelsLoaded();
        setupMatrixColumnModelFilterUI();
        setupMatrixSearchProductFilterUI();
        
        const res = await api(`/matrix/data?${params.toString()}`);
        if (res.error) {
            tbody.innerHTML = `<tr><td colspan="100" class="error-message">加载失败: ${res.error}</td></tr>`;
            return;
        }

        currentMatrixData = res.data;
        matrixColumns = (res.columns || []).filter(c => String(c || '').trim() && String(c || '').trim() !== '测试型号');
        matrixTotal = res.total;
        matrixCurrentPage = res.page;
        matrixLoaded = true;
        matrixLastRequestKey = requestKey;
        
        if (Array.isArray(res.product_categories)) {
            renderMatrixChips(
                'matrixProductCategoryChips',
                res.product_categories,
                matrixProductCategoryFilter,
                (v) => {
                    matrixProductCategoryFilter = v;
                    loadMatrixData(1);
                }
            );
        }
        
        if (Array.isArray(res.mapping_categories)) {
            renderMatrixMappingCategorySelect(res.mapping_categories, matrixMappingCategoryFilter);
        }
        
        renderMatrixTable();
        updateMatrixPagination();
        refreshMatrixFilteredTotal();
        
    } catch (e) {
        console.error("Load matrix failed", e);
        tbody.innerHTML = '<tr><td colspan="100" class="error-message">系统错误: ' + e.message + '</td></tr>';
    }
}

function renderMatrixTable() {
    const thead = document.getElementById('matrixTableHead');
    const tbody = document.getElementById('matrixTableBody');
    
    if (!currentMatrixData || currentMatrixData.length === 0) {
        thead.innerHTML = '';
        updateMatrixDiffCompareNotice(false);
        tbody.innerHTML = '<tr><td colspan="100" class="empty-message">暂无数据</td></tr>';
        return;
    }
    
    const diffCompareModels = getMatrixDiffCompareModels();
    const diffCompareActive = isMatrixDiffCompareActive();
    const rowsToRender = Array.isArray(currentMatrixData) ? currentMatrixData : [];
    updateMatrixDiffCompareNotice(diffCompareActive);

    let headHtml = `
        <th class="matrix-fixed-header matrix-fixed-left" style="width: 40px; text-align: center;">
            <input type="checkbox" id="matrixSelectAll" onchange="toggleSelectAllMatrix()">
        </th>
        <th class="matrix-fixed-header matrix-fixed-left-2" style="min-width: 80px; width: 90px; max-width: 100px;">ID</th>
        <th class="matrix-fixed-header" style="min-width: 100px; width: 120px; max-width: 150px;">分类</th>
        <th class="matrix-fixed-header" style="min-width: 250px; width: 280px; max-width: 300px;">问题</th>
        <th class="matrix-fixed-header" style="min-width: 400px; width: 460px; max-width: 500px;">答案</th>
    `;
    
    const columnsToRender = diffCompareActive ? diffCompareModels : matrixColumns;
    columnsToRender.forEach(prod => {
        let hasCellEdit = false;
        let hasBulkEdit = false;
        for (const row of (rowsToRender || [])) {
            if (!Array.isArray(row?.source_products)) continue;
            const prodKey = (prod ?? '').toString().trim();
            const sourceSet = toMatrixNormalizedStringSet(row.source_products);
            const cellData = row?.products?.[prodKey];
            const currentConfigured = getMatrixProductConfigured(row, prodKey);
            const sourceConfigured = sourceSet.has(normalizeMatrixProductName(prodKey));
            const mismatch = currentConfigured !== sourceConfigured;
            if (!mismatch) continue;
            const src = normalizeMatrixEditSource(cellData);
            if (src === 'cell') hasCellEdit = true;
            else if (src === 'bulk') hasBulkEdit = true;
            if (hasCellEdit && hasBulkEdit) break;
        }
        
        let iconsHtml = '';
        if (hasCellEdit || hasBulkEdit) {
            const parts = [];
            if (hasCellEdit) parts.push('<span class="matrix-origin-header-icon" title="本页包含手动单格修改">🔴</span>');
            if (hasBulkEdit) parts.push('<span class="matrix-origin-header-icon" title="本页包含按钮批量修改">🟢</span>');
            iconsHtml = `<span class="matrix-origin-header-icons">${parts.join('')}</span>`;
        }
        
        headHtml += `<th class="matrix-fixed-header matrix-prod-header" style="min-width: 60px; width: 70px; max-width: 80px; text-align: center;">${escapeHtml(prod)}${iconsHtml}</th>`;
    });
    
    thead.innerHTML = headHtml;
    tbody.innerHTML = '';
    
    if (!rowsToRender || rowsToRender.length === 0) {
        tbody.innerHTML = `<tr><td colspan="100" class="empty-message">${diffCompareActive ? '当前选中机型无差异行' : '无符合筛选的行'}</td></tr>`;
        makeTableResizable('matrixTable');
        tdRefreshCellOverflow(document.getElementById('matrixTable') || document);
        return;
    }
    
    rowsToRender.forEach(row => {
        const tr = document.createElement('tr');
        const minorityModels = diffCompareActive && diffCompareModels.length >= 3
            ? getMatrixDiffMinorityModels(row, diffCompareModels)
            : new Set();
        
        const isSelected = selectedMatrixRows.has(row.question_wiki_id);
        const checkTd = document.createElement('td');
        checkTd.className = "matrix-body-fixed-left";
        checkTd.style.textAlign = "center";
        checkTd.innerHTML = `<input type="checkbox" class="matrix-row-check" value="${row.question_wiki_id}" ${isSelected ? 'checked' : ''} onchange="toggleMatrixRow('${row.question_wiki_id}')">`;
        tr.appendChild(checkTd);
        
        const idTd = document.createElement('td');
        idTd.className = "matrix-body-fixed-left-2";
        const wid = row.question_wiki_id || '';
        idTd.innerText = wid;
        idTd.classList.add('matrix-id-cell', 'matrix-detail-cell');
        idTd.dataset.colTitle = 'ID';
        idTd.dataset.fullText = wid;
        idTd.dataset.modalAllowed = '1';
        idTd.onclick = () => copyToClipboard(wid);
        tr.appendChild(idTd);
        
        const catTd = document.createElement('td');
        const catText = row.product_category || row.product_category_name || '-';
        catTd.innerText = catText;
        catTd.classList.add('matrix-detail-cell');
        catTd.dataset.colTitle = '分类';
        catTd.dataset.fullText = catText;
        catTd.dataset.modalAllowed = '1';
        tr.appendChild(catTd);
        
        const qTd = document.createElement('td');
        const qText = row.question_content || row.question || '';
        qTd.classList.add('matrix-detail-cell');
        qTd.dataset.colTitle = '问题';
        qTd.dataset.fullText = qText;
        qTd.dataset.modalAllowed = '1';
        qTd.innerHTML = tdRenderExpandableText(`matrix:${wid}:question`, qText, { placeholder: '-' });
        tr.appendChild(qTd);
        
        const aTd = document.createElement('td');
        const aText = row.answer_content || row.answer || '';
        aTd.classList.add('matrix-detail-cell');
        aTd.dataset.colTitle = '答案';
        aTd.dataset.fullText = aText;
        aTd.dataset.modalAllowed = '1';
        aTd.innerHTML = tdRenderExpandableText(`matrix:${wid}:answer`, aText, { placeholder: '-' });
        tr.appendChild(aTd);
        
        columnsToRender.forEach(prod => {
            const td = document.createElement('td');
            td.className = 'matrix-config-cell';
            td.style.textAlign = 'center';
            const prodKey = (prod ?? '').toString().trim();
            const cellData = row.products[prodKey];
            const isConfigured = getMatrixProductConfigured(row, prodKey);
            const sourceAvailable = Array.isArray(row.source_products);
            const prevAvailable = Array.isArray(row.prev_products);
            const sourceSet = sourceAvailable ? toMatrixNormalizedStringSet(row.source_products) : new Set();
            const prevSet = prevAvailable ? toMatrixNormalizedStringSet(row.prev_products) : new Set();
            const prodNorm = normalizeMatrixProductName(prodKey);
            const sourceConfigured = sourceSet.has(prodNorm);
            const mismatch = sourceAvailable ? (!!isConfigured !== sourceConfigured) : false;
            const showYellowDiff = sourceAvailable && prevAvailable ? (sourceSet.has(prodNorm) !== prevSet.has(prodNorm)) : false;
            const editSource = mismatch ? normalizeMatrixEditSource(cellData) : '';
            if (minorityModels.has(prodKey)) td.classList.add('matrix-diff-minority-cell');
            
            td.innerHTML = renderMatrixCellHtml(!!isConfigured, editSource, showYellowDiff);
            td.title = isConfigured ? "已配置 (点击取消)" : "未配置 (点击启用)";
            td.onclick = () => toggleMatrixConfig(row.question_wiki_id, prod, !isConfigured, td);
            tr.appendChild(td);
        });
        
        tbody.appendChild(tr);
    });

    // 使矩阵表格支持调整列宽
    makeTableResizable('matrixTable');
    matrixBindCompactTableInteractions();
    tdRefreshCellOverflow(document.getElementById('matrixTable') || document);
    matrixRefreshCompactOverflow(document.getElementById('matrixTable') || document);
}

function updateMatrixPagination() {
    const info = document.getElementById('matrixPageInfo');
    const prev = document.getElementById('prevMatrixPageBtn');
    const next = document.getElementById('nextMatrixPageBtn');
    const totalPages = Math.max(1, Math.ceil((matrixTotal || 0) / (matrixPageSize || 1)));
    const currentPage = Math.min(Math.max(1, matrixCurrentPage || 1), totalPages);
    
    if (info) {
        info.innerText = `第 ${currentPage}/${totalPages} 页 ｜ 共 ${matrixTotal} 条`;
    }
    if (prev) prev.disabled = matrixCurrentPage <= 1;
    if (next) next.disabled = matrixCurrentPage * matrixPageSize >= matrixTotal;
}

function changeMatrixPage(offset) {
    loadMatrixData(matrixCurrentPage + offset);
}

function changeMatrixPageSize() {
    matrixPageSize = parseInt(document.getElementById('matrixPageSizeSelect').value);
    loadMatrixData(1);
}

function resetMatrixSearch() {
    const idEl = document.getElementById('matrixSearchId');
    if (idEl) idEl.value = '';
    document.getElementById('matrixSearchQuestion').value = '';
    const ansEl = document.getElementById('matrixSearchAnswer');
    if (ansEl) ansEl.value = '';
    clearMatrixSearchProductFilter(false);
    setMatrixProductMatchMode('any');
    matrixMarkFilter = { modified: true, unmodified: true };
    const mappingSelect = document.getElementById('matrixMappingCategorySelect');
    if (mappingSelect) mappingSelect.value = '';
    matrixProductCategoryFilter = '';
    matrixMappingCategoryFilter = '';
    matrixColumnModelSelected.clear();
    matrixDiffCompareEnabled = false;
    renderMatrixColumnModelSelectedChips();
    const columnInput = document.getElementById('matrixColumnModelInput');
    if (columnInput) columnInput.value = '';
    setMatrixMarkFilterMode('all');
}

async function ensureMatrixAllModelsLoaded() {
    if (Array.isArray(matrixAllModels) && matrixAllModels.length > 0) return;
    const res = await api('/matrix/products');
    if (res && res.success && Array.isArray(res.data)) {
        matrixAllModels = res.data;
    } else {
        matrixAllModels = [];
    }
}

function renderMatrixColumnModelSelectedChips() {
    const container = document.getElementById('matrixColumnModelSelectedChips');
    if (!container) return;
    container.innerHTML = '';
    
    const selected = Array.from(matrixColumnModelSelected);
    selected.forEach(model => {
        const chip = document.createElement('div');
        chip.className = 'tag-chip active';
        chip.style.display = 'inline-flex';
        chip.style.alignItems = 'center';
        chip.style.gap = '8px';
        
        const text = document.createElement('span');
        text.innerText = model;
        chip.appendChild(text);
        
        const close = document.createElement('span');
        close.innerText = '×';
        close.style.cursor = 'pointer';
        close.style.fontWeight = 'bold';
        close.onclick = (e) => {
            e.stopPropagation();
            matrixColumnModelSelected.delete(model);
            if (matrixColumnModelSelected.size < 2) matrixDiffCompareEnabled = false;
            renderMatrixColumnModelSelectedChips();
            loadMatrixData(1);
        };
        chip.appendChild(close);
        
        container.appendChild(chip);
    });
}

function clearMatrixColumnModelFilter() {
    matrixColumnModelSelected.clear();
    matrixDiffCompareEnabled = false;
    renderMatrixColumnModelSelectedChips();
    const input = document.getElementById('matrixColumnModelInput');
    if (input) input.value = '';
    const dropdown = document.getElementById('matrixColumnModelDropdown');
    if (dropdown) dropdown.classList.remove('show');
    loadMatrixData(1);
}

function setupMatrixColumnModelFilterUI() {
    if (matrixColumnModelUIBound) return;
    
    const input = document.getElementById('matrixColumnModelInput');
    const btn = document.getElementById('matrixColumnModelDropdownBtn');
    const dropdown = document.getElementById('matrixColumnModelDropdown');
    const container = input?.closest('.input-with-dropdown') || input?.parentElement;
    
    if (!input || !btn || !dropdown || !container) return;
    
    function renderDropdown() {
        dropdown.innerHTML = '';
        const q = input.value.trim().toLowerCase();
        const selected = matrixColumnModelSelected;
        const filtered = (matrixAllModels || [])
            .filter(m => m && !selected.has(m))
            .filter(m => !q || String(m).toLowerCase().includes(q))
            .slice(0, 80);
        
        if (filtered.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'dropdown-item';
            empty.style.color = '#999';
            empty.style.cursor = 'default';
            empty.textContent = '没有可选型号';
            dropdown.appendChild(empty);
            return;
        }
        
        filtered.forEach(model => {
            const item = document.createElement('div');
            item.className = 'dropdown-item';
            item.textContent = model;
            item.onclick = (e) => {
                e.stopPropagation();
                matrixColumnModelSelected.add(model);
                input.value = '';
                renderMatrixColumnModelSelectedChips();
                renderDropdown();
                dropdown.classList.add('show');
                if (matrixDiffCompareEnabled && matrixColumnModelSelected.size >= 2) {
                    loadMatrixDiffCompareDataIfNeeded(Array.from(matrixColumnModelSelected)).then(loaded => {
                        if (!loaded) renderMatrixTable();
                    });
                } else loadMatrixData(1);
                input.focus();
            };
            dropdown.appendChild(item);
        });
    }
    
    btn.onclick = (e) => {
        e.stopPropagation();
        e.preventDefault();
        const isVisible = dropdown.classList.contains('show');
        if (isVisible) {
            dropdown.classList.remove('show');
            container.classList.remove('is-open');
            return;
        }
        renderDropdown();
        dropdown.classList.add('show');
        container.classList.add('is-open');
        input.focus();
    };
    
    input.addEventListener('focus', () => {
        renderDropdown();
        dropdown.classList.add('show');
        container.classList.add('is-open');
    });
    
    input.addEventListener('input', () => {
        if (dropdown.classList.contains('show')) {
            renderDropdown();
        }
    });
    
    container.addEventListener('click', (e) => {
        if (e.target === input) return;
        input.focus();
        if (!dropdown.classList.contains('show')) {
            renderDropdown();
            dropdown.classList.add('show');
        }
    });
    
    document.addEventListener('click', (e) => {
        if (!container.contains(e.target) && !dropdown.contains(e.target) && e.target !== btn) {
            dropdown.classList.remove('show');
            container.classList.remove('is-open');
        }
    });
    
    matrixColumnModelUIBound = true;
    renderMatrixColumnModelSelectedChips();
}

async function toggleMatrixConfig(wiki_id, product_name, new_status, cellElement) {
    const originalHtml = cellElement.innerHTML;
    cellElement.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    const rowBefore = currentMatrixData.find(r => r.question_wiki_id === wiki_id);
    const oldStatus = !!(rowBefore && rowBefore.products && rowBefore.products[product_name] && rowBefore.products[product_name].is_configured);
    try {
        const res = await api('/matrix/update', 'POST', {
            question_wiki_id: wiki_id,
            product_name: product_name,
            is_configured: new_status
        });
        if (res.error) {
            showToast(res.error, 'error');
            cellElement.innerHTML = originalHtml;
            return;
        }
        const row = currentMatrixData.find(r => r.question_wiki_id === wiki_id);
        if (row) {
            if (!row.products[product_name]) row.products[product_name] = {};
            row.products[product_name].is_configured = new_status;
            row.products[product_name].manual_edit = true;
            row.products[product_name].edit_source = 'cell';
            if (Object.prototype.hasOwnProperty.call(res, 'source_products')) {
                row.source_products = Array.isArray(res.source_products) ? res.source_products : null;
            }
            if (Object.prototype.hasOwnProperty.call(res, 'prev_products')) {
                row.prev_products = Array.isArray(res.prev_products) ? res.prev_products : null;
            }
        }
        const container = document.getElementById('matrixTableContainer');
        const scrollLeft = container ? container.scrollLeft : 0;
        const scrollTop = container ? container.scrollTop : 0;
        renderMatrixTable();
        if (container) {
            container.scrollLeft = scrollLeft;
            container.scrollTop = scrollTop;
        }
        recordMatrixPendingChange({
            question_wiki_id: wiki_id,
            product_name: product_name,
            old_is_configured: oldStatus,
            new_is_configured: !!new_status,
            edit_source: 'cell'
        });
    } catch (e) {
        cellElement.innerHTML = originalHtml;
        showToast('更新失败: ' + e.message, 'error');
    }
}

function toggleSelectAllMatrix() {
    const checked = document.getElementById('matrixSelectAll').checked;
    document.querySelectorAll('.matrix-row-check').forEach(cb => {
        cb.checked = checked;
        if (checked) selectedMatrixRows.add(cb.value);
        else selectedMatrixRows.delete(cb.value);
    });
    updateMatrixBulkToolbarState();
}

function toggleMatrixRow(id) {
    if (selectedMatrixRows.has(id)) selectedMatrixRows.delete(id);
    else selectedMatrixRows.add(id);
    
    const allChecked = Array.from(document.querySelectorAll('.matrix-row-check')).every(cb => cb.checked);
    const selectAll = document.getElementById('matrixSelectAll');
    if (selectAll) {
        selectAll.checked = allChecked;
        selectAll.indeterminate = !allChecked && selectedMatrixRows.size > 0;
    }
    updateMatrixBulkToolbarState();
}

function updateMatrixBulkToolbarState() {
    const toolbar = document.getElementById('matrixBulkToolbar');
    if (toolbar) toolbar.classList.toggle('d-none', selectedMatrixRows.size === 0);
}

function cancelMatrixSelection() {
    selectedMatrixRows.clear();
    document.querySelectorAll('.matrix-row-check').forEach(cb => cb.checked = false);
    const selectAll = document.getElementById('matrixSelectAll');
    if (selectAll) {
        selectAll.checked = false;
        selectAll.indeterminate = false;
    }
    updateMatrixBulkToolbarState();
}

let matrixBulkPendingIsConfigured = null;

function openMatrixBulkConfigModal(isConfigured) {
    const modal = document.getElementById('matrixBulkConfigModal');
    const countEl = document.getElementById('matrixBulkSelectedCount');
    const statusEl = document.getElementById('matrixBulkTargetStatus');
    const select = document.getElementById('matrixBulkProductSelect');
    
    if (countEl) countEl.innerText = String(selectedMatrixRows.size);
    if (statusEl) statusEl.innerText = isConfigured ? '已配置' : '未配置';
    if (select) {
        select.innerHTML = '';
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = '请选择机型';
        select.appendChild(placeholder);
        
        (matrixColumns || []).forEach(p => {
            const opt = document.createElement('option');
            opt.value = p;
            opt.textContent = p;
            select.appendChild(opt);
        });
    }
    
    if (modal) modal.style.display = 'block';
}

function closeMatrixBulkConfigModal() {
    const modal = document.getElementById('matrixBulkConfigModal');
    if (modal) modal.style.display = 'none';
    matrixBulkPendingIsConfigured = null;
}

async function bulkSetMatrixConfig(isConfigured) {
    if (selectedMatrixRows.size === 0) {
        showToast('请先选择要操作的行', 'warning');
        return;
    }
    matrixBulkPendingIsConfigured = !!isConfigured;
    openMatrixBulkConfigModal(!!isConfigured);
}

async function confirmMatrixBulkConfigModal() {
    if (selectedMatrixRows.size === 0) {
        showToast('请先选择要操作的行', 'warning');
        closeMatrixBulkConfigModal();
        return;
    }
    
    const isConfigured = !!matrixBulkPendingIsConfigured;
    const select = document.getElementById('matrixBulkProductSelect');
    const product = (select && select.value ? String(select.value).trim() : '');
    if (!product) {
        showToast('请选择机型', 'warning');
        return;
    }
    if (!matrixColumns.includes(product)) {
        showToast('机型不存在，请刷新后重试', 'error');
        return;
    }
    
    const changesToRecord = Array.from(selectedMatrixRows).map(wikiId => {
        const row = currentMatrixData.find(r => r.question_wiki_id === wikiId);
        const oldStatus = !!(row && row.products && row.products[product] && row.products[product].is_configured);
        return {
            question_wiki_id: wikiId,
            product_name: product,
            old_is_configured: oldStatus,
            new_is_configured: !!isConfigured,
            edit_source: 'bulk'
        };
    }).filter(c => c.old_is_configured !== c.new_is_configured);
    
    try {
        const res = await api('/matrix/batch_update', 'POST', {
            question_wiki_ids: Array.from(selectedMatrixRows),
            product_name: product,
            is_configured: isConfigured
        });
        if (res.error) showToast('批量操作失败: ' + res.error, 'error');
        else {
            changesToRecord.forEach(recordMatrixPendingChange);
            showToast(`批量操作完成！成功更新/创建: ${res.updated} 条记录`, 'success');
            cancelMatrixSelection();
            loadMatrixData(matrixCurrentPage);
        }
    } catch (e) {
        showToast('批量操作异常: ' + e.message, 'error');
    } finally {
        closeMatrixBulkConfigModal();
    }
}

function openSyncMatrixModal() {
    const modal = document.getElementById('matrixSyncModal');
    modal.style.display = 'block';
    
    // Initialize Sync Option Cards Interaction
    const cards = modal.querySelectorAll('.sync-option-card');
    cards.forEach(card => {
        const radio = card.querySelector('input[type="radio"]');
        
        // Click on card triggers radio
        card.onclick = (e) => {
            // Prevent double triggering if clicking directly on radio
            if (e.target !== radio) {
                radio.checked = true;
                updateSelectedCard();
            }
        };
        
        // Listen for radio change
        radio.onchange = updateSelectedCard;
    });
    
    function updateSelectedCard() {
        cards.forEach(c => {
            const r = c.querySelector('input[type="radio"]');
            if (r.checked) {
                c.classList.add('selected');
            } else {
                c.classList.remove('selected');
            }
        });
    }
    
    // Initial update
    updateSelectedCard();
}

async function confirmSyncMatrix() {
    const mode = document.querySelector('input[name="matrixSyncMode"]:checked').value;
    const btn = document.querySelector('#matrixSyncModal .primary-btn');
    const originalText = btn.innerText;
    
    if (mode === 'reset' && !confirm('警告：重置模式将清空矩阵中所有手动配置的数据！确定要继续吗？')) return;
    if (mode === 'content_refresh' && !confirm('警告：此操作将强制更新所有内容（保留产品配置），确定要继续吗？')) return;
    
    btn.disabled = true;
    btn.innerText = "同步中...";
    try {
        const res = await api('/matrix/sync', 'POST', { mode: mode });
        if (res.error) showToast('同步失败: ' + res.error, 'error');
        else {
            showToast(`同步成功！新增 ${res.added} 条，更新 ${res.updated} 条，删除 ${res.deleted} 条`, 'success');
            document.getElementById('matrixSyncModal').style.display = 'none';
            loadMatrixData(1);
        }
    } catch (e) {
        showToast('同步请求失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerText = originalText;
    }
}

function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) {
        console.warn('Toast container not found');
        alert(message);
        return;
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = 'info-circle';
    if (type === 'success') icon = 'check-circle';
    if (type === 'error') icon = 'times-circle';
    if (type === 'warning') icon = 'exclamation-triangle';

    const titleMap = {
        'success': '成功',
        'error': '错误',
        'warning': '警告',
        'info': '提示'
    };

    toast.innerHTML = `
        <i class="fas fa-${icon} toast-icon"></i>
        <div class="toast-content">
            <div class="toast-title">${titleMap[type] || '提示'}</div>
            <div class="toast-message">${message}</div>
        </div>
        <i class="fas fa-times toast-close" onclick="this.parentElement.remove()"></i>
    `;

    container.appendChild(toast);

    // Trigger reflow
    toast.offsetHeight;
    
    // Show
    setTimeout(() => toast.classList.add('show'), 10);

    // Auto dismiss
    if (duration > 0) {
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
}

/* Deprecated: Use Product Manager instead
async function addMatrixColumn() {
    const product = prompt("请输入新机型名称:");
    if (!product) return;
    try {
        const res = await api('/matrix/add_column', 'POST', { product_name: product });
        if (res.error) alert(res.error);
        else {
            alert('添加成功');
            loadMatrixData(matrixCurrentPage);
        }
    } catch (e) {
        alert('添加失败: ' + e.message);
    }
}
*/

// ==========================================
// Matrix Clone Config Modal
// ==========================================
let copyConfigState = {
    mode: 'model', // 'model' or 'category'
    targets: [],
    availableTargets: []
};

async function openCopyConfigModal() {
    const modal = document.getElementById('copyConfigModal');
    if (!modal) return;
    
    // Reset State
    copyConfigState.targets = [];
    renderCopyTargets();
    
    // Clear Inputs
    const modelSelect = document.getElementById('copySourceModel');
    if (modelSelect) modelSelect.value = '';
    
    const catSelect = document.getElementById('copySourceCategory');
    if (catSelect) catSelect.value = '';
    
    const targetInput = document.getElementById('copyTargetInput');
    if (targetInput) targetInput.value = '';
    
    // Reset Stats
    const modelStats = document.getElementById('copyModelStats');
    if (modelStats) modelStats.innerText = '请选择源机型...';
    
    const catStats = document.getElementById('copyCategoryStats');
    if (catStats) catStats.innerText = '请选择源分类...';
    
    // Show Modal
    modal.style.display = 'flex';
    
    // Switch to default mode (this loads sources)
    switchCopyMode('model');

    const updateBtnLabel = () => {
        const btn = document.querySelector('#copyConfigModal .primary-btn');
        if (!btn) return;
        const strategy = document.querySelector('input[name="copyStrategy"]:checked')?.value || 'append';
        btn.innerText = strategy === 'force_sync' ? '开始替换' : '开始追加';
    };
    updateBtnLabel();
    const strategyRadios = document.querySelectorAll('input[name="copyStrategy"]');
    strategyRadios.forEach(r => {
        if (r.dataset.listenerAttached) return;
        r.addEventListener('change', updateBtnLabel);
        r.dataset.listenerAttached = 'true';
    });
    
    // Setup event listener for input (if not already attached)
    const input = document.getElementById('copyTargetInput');
    if (input && !input.dataset.listenerAttached) {
        // Enter key
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addCopyTarget();
            }
        });

        // Autocomplete Input
        const suggestions = document.getElementById('targetSuggestions');
        input.addEventListener('input', (e) => {
            const val = e.target.value.trim().toLowerCase();
            if (!val) {
                suggestions.style.display = 'none';
                return;
            }
            
            const matches = (copyConfigState.availableTargets || []).filter(t => 
                t.toLowerCase().includes(val) && !copyConfigState.targets.includes(t)
            );
            
            if (matches.length > 0) {
                suggestions.innerHTML = matches.map(t => 
                    `<div class="suggestion-item" style="padding: 8px; cursor: pointer; border-bottom: 1px solid #eee;">${t}</div>`
                ).join('');
                suggestions.style.display = 'block';
                
                // Add click listeners to items
                suggestions.querySelectorAll('.suggestion-item').forEach(item => {
                    item.addEventListener('click', () => {
                        input.value = item.innerText;
                        suggestions.style.display = 'none';
                        input.focus();
                    });
                    item.addEventListener('mouseover', () => item.style.backgroundColor = '#f0f0f0');
                    item.addEventListener('mouseout', () => item.style.backgroundColor = 'white');
                });
            } else {
                suggestions.style.display = 'none';
            }
        });

        // Hide on outside click
        document.addEventListener('click', (e) => {
            if (e.target !== input && !suggestions.contains(e.target)) {
                suggestions.style.display = 'none';
            }
        });

        input.dataset.listenerAttached = 'true';
    }
}

function closeCopyConfigModal() {
    const modal = document.getElementById('copyConfigModal');
    if (modal) modal.style.display = 'none';
}

function switchCopyMode(mode) {
    copyConfigState.mode = mode;
    
    // Update Tabs UI
    const tabModel = document.getElementById('tab-copy-model');
    const tabCategory = document.getElementById('tab-copy-category');
    
    if (mode === 'model') {
        tabModel.classList.add('active');
        tabModel.style.borderBottom = '3px solid #9B59B6';
        tabModel.style.color = '#9B59B6';
        tabModel.style.fontWeight = 'bold';
        
        tabCategory.classList.remove('active');
        tabCategory.style.borderBottom = '3px solid transparent';
        tabCategory.style.color = '#666';
        tabCategory.style.fontWeight = 'normal';
        
        document.getElementById('copy-model-content').style.display = 'block';
        document.getElementById('copy-category-content').style.display = 'none';
    } else {
        tabCategory.classList.add('active');
        tabCategory.style.borderBottom = '3px solid #9B59B6';
        tabCategory.style.color = '#9B59B6';
        tabCategory.style.fontWeight = 'bold';
        
        tabModel.classList.remove('active');
        tabModel.style.borderBottom = '3px solid transparent';
        tabModel.style.color = '#666';
        tabModel.style.fontWeight = 'normal';
        
        document.getElementById('copy-model-content').style.display = 'none';
        document.getElementById('copy-category-content').style.display = 'block';
    }
    
    // Reset Stats
    document.getElementById('copyModelStats').innerText = '请选择源机型...';
    document.getElementById('copyCategoryStats').innerText = '请选择源分类...';
    
    // Load sources for the selected mode
    loadCopySources();
}

async function loadCopySources() {
    try {
        // Always fetch products for datalist (Target Models)
        const productsRes = await api('/matrix/products');
        const catalogProducts = productsRes.catalog || productsRes.data || [];
        
        // Store for autocomplete
        copyConfigState.availableTargets = catalogProducts;
        
        // Removed datalist population code as we use custom autocomplete now

        if (copyConfigState.mode === 'model') {
            // Populate Source Model Select (Use Catalog Products ONLY as requested)
            const select = document.getElementById('copySourceModel');
            if (select) {
                select.innerHTML = '<option value="">请选择...</option>' + 
                    catalogProducts.map(p => `<option value="${p}">${p}</option>`).join('');
            }
        } else {
            // Fetch Categories for Source Category Select (Use Model Mappings as requested)
            const mappingsRes = await api('/model_mappings');
            const categories = Object.keys(mappingsRes || {}).sort();
            
            const select = document.getElementById('copySourceCategory');
            if (select) {
                select.innerHTML = '<option value="">请选择...</option>' + 
                    categories.map(c => `<option value="${c}">${c}</option>`).join('');
            }
        }
    } catch (e) {
        console.error('Failed to load copy sources:', e);
        showToast('加载源数据失败: ' + e.message, 'error');
    }
}

async function fetchCopyStats() {
    const mode = copyConfigState.mode;
    let source = '';
    let statsElem = null;
    
    if (mode === 'model') {
        source = document.getElementById('copySourceModel').value;
        statsElem = document.getElementById('copyModelStats');
    } else {
        source = document.getElementById('copySourceCategory').value;
        statsElem = document.getElementById('copyCategoryStats');
    }
        
    if (!source) {
        if (statsElem) statsElem.innerText = mode === 'model' ? '请选择源机型...' : '请选择源分类...';
        return;
    }
    
    if (statsElem) statsElem.innerText = '正在计算...';
    
    try {
        const res = await api(`/matrix/stats?mode=${mode}&source=${encodeURIComponent(source)}`, 'GET');
        if (res.success && statsElem) {
            if (mode === 'category') {
                statsElem.innerText = `找到 ${res.count} 条完全匹配的知识条目`;
            } else {
                statsElem.innerText = `已找到 ${res.count} 条关联的知识库条目`;
            }
        } else if (statsElem) {
            statsElem.innerText = '无法获取统计数据';
        }
    } catch (e) {
        console.error('Failed to fetch stats:', e);
        if (statsElem) statsElem.innerText = '获取统计失败';
    }
}

function addCopyTarget() {
    const input = document.getElementById('copyTargetInput');
    if (!input) return;
    
    const val = input.value.trim();
    if (!val) return;
    
    if (copyConfigState.targets.includes(val)) {
        showToast('该机型已添加', 'warning');
        return;
    }
    
    copyConfigState.targets.push(val);
    input.value = '';
    renderCopyTargets();
}

function removeCopyTarget(target) {
    copyConfigState.targets = copyConfigState.targets.filter(t => t !== target);
    renderCopyTargets();
}

function renderCopyTargets() {
    const container = document.getElementById('copyTargetList');
    if (!container) return;
    
    if (copyConfigState.targets.length === 0) {
        container.innerHTML = '<span style="color: #999; font-style: italic; padding: 5px;">暂无目标机型</span>';
        return;
    }
    
    container.innerHTML = copyConfigState.targets.map(t => `
        <span class="tag" style="background: #e1bee7; color: #4a148c; padding: 4px 10px; border-radius: 16px; display: inline-flex; align-items: center; margin: 2px; font-size: 14px;">
            ${t}
            <span onclick="removeCopyTarget('${t}')" style="cursor: pointer; margin-left: 8px; font-weight: bold; font-size: 16px; line-height: 1;">&times;</span>
        </span>
    `).join('');
}

async function executeCopyConfig() {
    const mode = copyConfigState.mode;
    let source = '';
    
    if (mode === 'model') {
        source = document.getElementById('copySourceModel').value;
    } else {
        source = document.getElementById('copySourceCategory').value;
    }
    
    if (!source) {
        showToast('请选择源' + (mode === 'model' ? '机型' : '分类'), 'error');
        return;
    }
    
    if (copyConfigState.targets.length === 0) {
        showToast('请至少添加一个目标机型', 'error');
        return;
    }
    
    const strategyElem = document.querySelector('input[name="copyStrategy"]:checked');
    const strategy = strategyElem ? strategyElem.value : 'append';

    if (strategy === 'force_sync') {
        const ok = confirm('你选择了【强制同步】策略。\n这会删除源机型在相关条目中的关联，并用目标机型替换。\n\n确认继续？');
        if (!ok) return;
    }
    
    // UI Loading state
    const btn = document.querySelector('#copyConfigModal .primary-btn');
    const originalText = btn.innerText;
    if (btn) {
        btn.innerText = '正在处理...';
        btn.disabled = true;
    }
    
    try {
        const res = await api('/matrix/clone_config', 'POST', {
            mode,
            source,
            targets: copyConfigState.targets,
            strategy
        });
        
        if (res.success) {
            const removed = res.removed_count || 0;
            showToast(`成功更新 ${res.updated_count} 条记录${removed ? `，移除 ${removed} 条源机型关联` : ''}`, 'success');
            const pending = Array.isArray(res.pending_changes) ? res.pending_changes : [];
            if (pending.length > 0) {
                pending.forEach(c => recordMatrixPendingChange({
                    question_wiki_id: c.question_wiki_id,
                    product_name: c.product_name,
                    old_is_configured: !!c.old_is_configured,
                    new_is_configured: !!c.new_is_configured,
                    edit_source: c.edit_source || 'bulk'
                }));
                showToast(`已生成待提交修改 ${pending.length} 条，请点击“提交修改”`, 'info', 5000);
            }
            closeCopyConfigModal();
            // Refresh matrix view if it's currently active
            if (currentTab === 'matrixView') {
                loadMatrixData(matrixCurrentPage || 1);
            }
        } else {
            showToast('操作失败: ' + (res.message || '未知错误'), 'error');
        }
    } catch (e) {
        console.error('Execute copy config error:', e);
        showToast('请求错误: ' + e.message, 'error');
    } finally {
        if (btn) {
            btn.innerText = originalText;
            btn.disabled = false;
        }
    }
}

function exportMatrix() {
    if (!currentMatrixData || currentMatrixData.length === 0) {
        if (!confirm('当前视图无数据，是否导出全量矩阵？')) return;
    }
    
    // Get current filter params
    const id = document.getElementById('matrixSearchId')?.value.trim() || '';
    const q = document.getElementById('matrixSearchQuestion')?.value.trim() || '';
    const a = document.getElementById('matrixSearchAnswer')?.value.trim() || '';
    const pModels = Array.from(matrixSearchProductSelected);
    
    const params = new URLSearchParams();
    if (id) params.append('id', id);
    if (q) params.append('q', q);
    if (a) params.append('a', a);
    if (pModels.length > 0) {
        params.append('p_models', pModels.join(','));
        params.append('p_mode', matrixProductMatchMode || 'any');
    }
    if (matrixProductCategoryFilter) params.append('pc', matrixProductCategoryFilter);
    if (matrixMappingCategoryFilter) params.append('mc', matrixMappingCategoryFilter);
    if (matrixColumnModelSelected.size > 0) {
        params.append('col_models', Array.from(matrixColumnModelSelected).join(','));
    }
    params.append('mark_modified', matrixMarkFilter.modified ? '1' : '0');
    params.append('mark_unmodified', matrixMarkFilter.unmodified ? '1' : '0');
    if (isMatrixDiffCompareActive()) params.append('diff_compare', '1');
    
    window.location.href = '/api/matrix/export?' + params.toString();
}

// ==========================================
// Scoring View (Basic Support)
// ==========================================

async function loadScoringData(options = {}) {
    if ((isScoringInProgress() || isScoringPaused()) && !options.force) {
        renderScoringTable(true);
        updateScoringProgressUI();
        return;
    }
    if (options.reuse && scoringLoaded && !options.force) {
        renderScoringTable();
        updateScoringStats();
        updateScoringProgressUI();
        return;
    }
    
    const tbody = document.getElementById('scoringTableBody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="10" class="empty-message">加载中...</td></tr>';
    
    try {
        const res = await api('/scoring/data');
        if (res.success) {
            currentScoringData = (res.data || []).map(item => {
                // Parse score_data if it exists and is a string
                if (item.score_data) {
                    try {
                        const parsed = typeof item.score_data === 'string' ? JSON.parse(item.score_data) : item.score_data;
                        
                        // Map Chinese keys to English keys expected by renderScoringTable
                        // Structure might be nested under "维度得分" or flat
                        const scores = parsed['维度得分'] || parsed;
                        
                        const mapped = {
                            quality: scores['问题质量'] || scores['质量得分'],
                            compliance: scores['答案合规与准确性'] || scores['合规得分'],
                            timeliness: scores['时效性'] || scores['时效得分'],
                            utility: scores['实际解决力'] || scores['实用得分'],
                            redundancy: scores['非冗余与相关性'] || scores['冗余扣分'],
                            multimedia: scores['多媒体加分'] || scores['多媒体得分'],
                            
                            suggestion: parsed['处理建议'] || parsed['修改建议'],
                            analysis: parsed['分析过程'] || parsed['扣分分析'],
                            
                            // total_score is usually at root level, but override if present in JSON
                            total_score: parsed['总分'] !== undefined ? parsed['总分'] : item.total_score
                        };

                        // Flatten parsed properties into the item for easy access
                        return { ...item, ...parsed, ...mapped };
                    } catch (e) {
                        console.error('Error parsing score_data for', item.kb_id, e);
                        return item;
                    }
                }
                return item;
            });
            scoringLoaded = true;
            scoringPage = 1;
            renderScoringTable();
            updateScoringStats();
        } else {
            if (tbody) tbody.innerHTML = `<tr><td colspan="10" class="error-message">加载失败: ${res.message}</td></tr>`;
        }
    } catch (e) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="10" class="error-message">系统错误: ${e.message}</td></tr>`;
    }
}

function parseScoringScoreFilter(value) {
    if (value === undefined || value === null) return null;
    const text = String(value).trim();
    if (!text) return null;
    const score = Number(text);
    return Number.isFinite(score) ? score : null;
}

function getScoringItemTotalScore(item) {
    const rawScore = item?.total_score ?? item?.score;
    if (rawScore === undefined || rawScore === null || rawScore === '') return null;
    const score = Number(rawScore);
    return Number.isFinite(score) ? score : null;
}

const SCORING_DIMENSION_CONFIG = [
    { key: 'quality', label: '质' },
    { key: 'compliance', label: '规' },
    { key: 'timeliness', label: '时' },
    { key: 'utility', label: '解' },
    { key: 'redundancy', label: '冗' },
    { key: 'multimedia', label: '媒' }
];

function formatScoringDimensionValue(item, key) {
    const value = item?.[key];
    return value !== undefined && value !== null && value !== '' ? String(value) : '-';
}

function renderScoringDimensionSummary(item) {
    return `
        <div class="scoring-metric-grid">
            ${SCORING_DIMENSION_CONFIG.map(dim => `
                <span class="scoring-metric-pill" title="${_escapeAttr(dim.label)}：${_escapeAttr(formatScoringDimensionValue(item, dim.key))}">
                    <span>${dim.label}</span>
                    <b>${_escapeHtml(formatScoringDimensionValue(item, dim.key))}</b>
                </span>
            `).join('')}
        </div>
    `;
}

function buildScoringResultPreview(item) {
    const suggestion = String(item?.suggestion || '').trim();
    const analysis = String(item?.analysis || '').trim();
    if (suggestion && analysis) return `建议：${suggestion}\n分析：${analysis}`;
    if (suggestion) return `建议：${suggestion}`;
    if (analysis) return `分析：${analysis}`;
    return '';
}

function getScoringFilterValues() {
    return {
        idFilter: document.getElementById('scoreSearchId')?.value.trim().toLowerCase() || '',
        productFilter: document.getElementById('scoreSearchProduct')?.value.trim().toLowerCase() || '',
        questionFilter: document.getElementById('scoreSearchQuestion')?.value.trim().toLowerCase() || '',
        statusFilter: document.getElementById('scoreSearchStatus')?.value || '',
        minTotalScore: parseScoringScoreFilter(document.getElementById('scoreSearchMinTotal')?.value),
        maxTotalScore: parseScoringScoreFilter(document.getElementById('scoreSearchMaxTotal')?.value)
    };
}

function scoringItemMatchesFilters(item, filters = getScoringFilterValues()) {
    if (filters.idFilter && !String(item.kb_id || item.id).toLowerCase().includes(filters.idFilter)) return false;
    if (filters.productFilter && !String(item.product_name || '').toLowerCase().includes(filters.productFilter)) return false;
    if (filters.questionFilter && !String(item.question_content || '').toLowerCase().includes(filters.questionFilter)) return false;
    if (filters.statusFilter && item.status !== filters.statusFilter) return false;

    if (filters.minTotalScore !== null || filters.maxTotalScore !== null) {
        const totalScore = getScoringItemTotalScore(item);
        if (totalScore === null) return false;
        if (filters.minTotalScore !== null && totalScore < filters.minTotalScore) return false;
        if (filters.maxTotalScore !== null && totalScore > filters.maxTotalScore) return false;
    }

    return true;
}
function renderScoringTable(filter = false) {
    const tbody = document.getElementById('scoringTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    let data = currentScoringData;

    // Client-side filtering
    if (filter) {
        const filters = getScoringFilterValues();
        data = data.filter(item => scoringItemMatchesFilters(item, filters));
    }
    
    // Pagination
    const start = (scoringPage - 1) * scoringPageSize;
    const end = start + scoringPageSize;
    const pageData = data.slice(start, end);
    
    if (pageData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="empty-message">暂无评分数据，请点击“同步打分数据”</td></tr>';
        updateScoringPagination(data.length);
        return;
    }
    
    pageData.forEach(item => {
        const tr = document.createElement('tr');
        const id = item.kb_id || item.id;
        
        // Checkbox
        const tdCheck = document.createElement('td');
        const isChecked = selectedScoringRows.has(id);
        tdCheck.innerHTML = `<input type="checkbox" class="scoring-row-check" value="${id}" ${isChecked ? 'checked' : ''} onchange="toggleScoringRow('${id}')">`;
        tr.appendChild(tdCheck);

        // ID
        const tdId = document.createElement('td');
        tdId.className = 'scoring-id-cell';
        tdId.appendChild(document.createTextNode(id));
        
        // Single score icon
        const scoreIcon = document.createElement('i');
        scoreIcon.className = 'fas fa-sync-alt';
        scoreIcon.style.marginLeft = '8px';
        scoreIcon.style.cursor = 'pointer';
        scoreIcon.style.color = '#0d6efd';
        scoreIcon.title = '点击重新评分';
        
        if (item.status === 'scoring') {
            scoreIcon.classList.add('fa-spin');
            scoreIcon.style.cursor = 'not-allowed';
            scoreIcon.style.opacity = '0.6';
        } else {
            scoreIcon.onclick = (e) => {
                e.stopPropagation();
                // Trigger scoring for this single item
                streamEvaluate([id], null, '', { useCache: false });
            };
        }
        
        tdId.appendChild(scoreIcon);
        tdId.title = id;
        tr.appendChild(tdId);
        
        // Product (Not in kb_scores usually, placeholder)
        const tdProd = document.createElement('td');
        tdProd.className = 'scoring-product-cell';
        const productText = item.product_name || '-';
        tdProd.innerHTML = `<div class="scoring-product-preview" title="${_escapeAttr(productText)}">${_escapeHtml(productText)}</div>`;
        tr.appendChild(tdProd);
        
        // Question
        const tdQ = document.createElement('td');
        tdQ.className = 'scoring-text-cell scoring-question-cell';
        tdQ.innerHTML = tdRenderExpandableText(`score:${id}:question`, item.question_content || '', { placeholder: '-' });
        tr.appendChild(tdQ);
        
        // Answer
        const tdA = document.createElement('td');
        tdA.className = 'scoring-text-cell scoring-answer-cell';
        tdA.innerHTML = tdRenderExpandableText(`score:${id}:answer`, item.answer_content || '', { placeholder: '-' });
        tr.appendChild(tdA);
        
        // Score dimensions
        const tdDimensions = document.createElement('td');
        tdDimensions.className = 'scoring-breakdown-cell';
        tdDimensions.innerHTML = item.status === 'scoring'
            ? '<i class="fas fa-spinner fa-spin text-muted"></i>'
            : renderScoringDimensionSummary(item);
        tr.appendChild(tdDimensions);

        // Total Score
        const tdScore = document.createElement('td');
        tdScore.className = 'scoring-total-cell';
        if (item.status === 'scoring') {
            tdScore.innerHTML = '<i class="fas fa-spinner fa-spin text-primary"></i>';
        } else {
            const score = getScoringItemTotalScore(item);
            tdScore.textContent = score !== undefined && score !== null ? score : '-';
            if (score !== null) {
                if (score < 70) tdScore.classList.add('score-low');
                else if (score < 85) tdScore.classList.add('score-medium');
                else tdScore.classList.add('score-high');
            }
            tdScore.style.fontWeight = 'bold';
        }
        tr.appendChild(tdScore);
        
        // Suggestion and analysis preview
        const tdResult = document.createElement('td');
        tdResult.className = 'scoring-text-cell scoring-result-cell';
        tdResult.innerHTML = tdRenderExpandableText(`score:${id}:result`, buildScoringResultPreview(item), { placeholder: '-' });
        tr.appendChild(tdResult);

        // Status
        const tdStatus = document.createElement('td');
        tdStatus.className = 'scoring-status-cell';
        const status = item.status || 'unscored';
        let badgeClass = 'badge-secondary';
        let statusText = '未评分';
        
        if (status === 'scored') { badgeClass = 'badge-success'; statusText = '已评分'; }
        else if (status === 'scoring') { badgeClass = 'badge-info'; statusText = '评分中'; } // Changed to info/blue for active state
        else if (status === 'outdated') { badgeClass = 'badge-danger'; statusText = '已过期'; }
        
        tdStatus.innerHTML = `<span class="badge ${badgeClass}">${statusText}</span>`;
        tr.appendChild(tdStatus);

        // Action
        const tdAction = document.createElement('td');
        tdAction.className = 'scoring-action-cell';
        tdAction.innerHTML = `<button class="action-btn btn-sm" onclick="viewScoreDetail('${id}')">详情</button>`;
        tr.appendChild(tdAction);

        tbody.appendChild(tr);
    });
    
    updateScoringPagination(data.length);
    updateScoringStats();
    
    // 使评分表格支持调整列宽
    makeTableResizable('scoringTable');
    tdRefreshCellOverflow(document.getElementById('scoringTable') || document);
}

function updateScoringPagination(total) {
    const info = document.getElementById('scoringPageInfo');
    if (info) info.textContent = `共 ${total} 条`;
    
    const prevBtn = document.getElementById('prevScoringPageBtn');
    const nextBtn = document.getElementById('nextScoringPageBtn');
    
    if (prevBtn) prevBtn.disabled = scoringPage <= 1;
    // Use the filtered total count, not the global total
    if (nextBtn) nextBtn.disabled = (scoringPage * scoringPageSize) >= total;
}

function changeScoringPage(delta) {
    const newPage = scoringPage + delta;
    if (newPage < 1) return;
    scoringPage = newPage;
    renderScoringTable(true);
}

function changeScoringPageSize() {
    scoringPageSize = parseInt(document.getElementById('scoringPageSizeSelect').value);
    scoringPage = 1;
    renderScoringTable(true);
}

function toggleScoringRow(id) {
    const cb = document.querySelector(`.scoring-row-check[value="${id}"]`);
    if (cb && cb.checked) {
        selectedScoringRows.add(id);
    } else {
        selectedScoringRows.delete(id);
    }
    updateScoringStats();
}

function toggleSelectAllScoring() {
    const selectAll = document.getElementById('selectAllScoring');
    const checks = document.querySelectorAll('.scoring-row-check');
    
    checks.forEach(cb => {
        cb.checked = selectAll.checked;
        if (selectAll.checked) {
            selectedScoringRows.add(cb.value);
        } else {
            selectedScoringRows.delete(cb.value);
        }
    });
    updateScoringStats();
}

function resetScoringFilter() {
    document.getElementById('scoreSearchId').value = '';
    document.getElementById('scoreSearchProduct').value = '';
    document.getElementById('scoreSearchQuestion').value = '';
    document.getElementById('scoreSearchStatus').value = '';
    document.getElementById('scoreSearchMinTotal').value = '';
    document.getElementById('scoreSearchMaxTotal').value = '';
    scoringPage = 1;
    renderScoringTable(false);
}

function viewScoreDetail(id) {
    const item = currentScoringData.find(i => (i.kb_id || i.id) == id);
    if (!item) {
        alert("未找到数据");
        return;
    }
    
    // Helper for score color
    const getScoreColor = (s) => s >= 80 ? '#28a745' : (s < 60 ? '#dc3545' : '#ffc107');
    const totalScoreColor = getScoreColor(item.total_score || 0);

    // Helper for safe HTML
    const safeHtml = (str) => str ? str.replace(/</g, "&lt;").replace(/>/g, "&gt;") : '';

    let rawDataDisplay = '{}';
    try {
        if (item.score_data) {
            rawDataDisplay = typeof item.score_data === 'object' 
                ? JSON.stringify(item.score_data, null, 2) 
                : item.score_data;
            if (typeof rawDataDisplay === 'string' && rawDataDisplay.trim().startsWith('{')) {
                try {
                    const parsed = JSON.parse(rawDataDisplay);
                    rawDataDisplay = JSON.stringify(parsed, null, 2);
                } catch(e) {}
            }
        }
    } catch(e) {
        rawDataDisplay = String(item.score_data);
    }

    // Helper to render dimension card
    const renderDimensionCard = (label, score, max, isBonus=false) => {
        const scoreVal = parseFloat(score);
        const hasScore = !isNaN(scoreVal);
        const displayScore = hasScore ? scoreVal : '-';
        
        // Calculate percentage
        let pct = 0;
        if (hasScore) {
            if (isBonus) {
                 pct = scoreVal > 0 ? 100 : 0;
            } else {
                 pct = Math.min(100, (scoreVal / (parseFloat(max) || 1)) * 100);
            }
        }
        
        const barColor = isBonus ? '#28a745' : '#0d6efd';
        
        return `
            <div style="background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px; display: flex; flex-direction: column;">
                <div style="display: flex; justify-content: space-between; font-size: 13px; color: #666; margin-bottom: 6px;">
                    <span>${label}</span>
                    <span style="font-size: 12px; opacity: 0.7;">/${max}</span>
                </div>
                <div style="font-size: 20px; font-weight: 700; color: #333; margin-bottom: 8px;">
                    ${displayScore}
                </div>
                <div style="height: 4px; background: #f0f0f0; border-radius: 2px; overflow: hidden; margin-top: auto;">
                    <div style="width: ${pct}%; height: 100%; background: ${barColor}; transition: width 0.3s ease;"></div>
                </div>
            </div>
        `;
    };

    let content = `
        <div class="score-detail-container" style="padding: 5px;">
            <!-- Header: Score & Status -->
            <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #eee;">
                <div>
                    <div style="font-size: 13px; color: #888; margin-bottom: 4px;">当前状态</div>
                    <div class="status-badge status-${item.status || 'unknown'}" style="font-size: 14px; display: inline-block; padding: 4px 12px; border-radius: 20px; background: #f0f0f0; font-weight: 600;">
                        ${item.status || '未评分'}
                    </div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 13px; color: #888; margin-bottom: 4px;">综合得分</div>
                    <div style="font-size: 42px; font-weight: 800; color: ${totalScoreColor}; line-height: 1; letter-spacing: -1px;">
                        ${item.total_score || '-'}
                    </div>
                </div>
            </div>

            <!-- Q&A Section -->
            <div style="display: grid; gap: 16px; margin-bottom: 24px;">
                <div style="background: #f8f9fa; border-radius: 8px; padding: 16px; border-left: 4px solid #6c757d;">
                    <h4 style="margin: 0 0 8px 0; color: #495057; font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Question</h4>
                    <div style="font-size: 16px; color: #212529; font-weight: 500; line-height: 1.5;">
                        ${safeHtml(item.question_content)}
                    </div>
                </div>
                
                <div style="background: #f8f9fa; border-radius: 8px; padding: 16px; border-left: 4px solid #0d6efd;">
                    <h4 style="margin: 0 0 8px 0; color: #495057; font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Answer</h4>
                    <div style="font-size: 15px; color: #333; line-height: 1.6; max-height: 300px; overflow-y: auto; white-space: pre-wrap; padding-right: 5px;" class="custom-scrollbar">
                        ${safeHtml(item.answer_content)}
                    </div>
                </div>

                <!-- Product Section -->
                <div style="background: #f8f9fa; border-radius: 8px; padding: 16px; border-left: 4px solid #198754;">
                    <h4 style="margin: 0 0 8px 0; color: #495057; font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Product</h4>
                    <div style="font-size: 15px; color: #333; line-height: 1.6;">
                        ${safeHtml(item.product_name || '未指定产品')}
                    </div>
                </div>
            </div>

            <!-- Dimensions Grid -->
            <div style="margin-bottom: 24px;">
                <h4 style="margin: 0 0 16px 0; color: #333; font-size: 16px; font-weight: 700; display: flex; align-items: center;">
                    <span style="width: 4px; height: 16px; background: #0d6efd; border-radius: 2px; margin-right: 8px;"></span>
                    维度得分详情
                </h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 12px;">
                    ${renderDimensionCard('问题质量', item.quality, 10)}
                    ${renderDimensionCard('答案合规', item.compliance, 30)}
                    ${renderDimensionCard('时效性', item.timeliness, 20)}
                    ${renderDimensionCard('解决力', item.utility, 30)}
                    ${renderDimensionCard('非冗余', item.redundancy, 10)}
                    ${renderDimensionCard('多媒体', item.multimedia, '+10', true)}
                </div>
            </div>

            <!-- Analysis & Suggestion -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px;">
                <div style="background: #e7f5ff; border: 1px solid #d0ebff; border-radius: 8px; padding: 16px;">
                    <h4 style="margin: 0 0 10px 0; color: #0056b3; font-size: 15px; display: flex; align-items: center;">
                        <span style="font-size: 18px; margin-right: 6px;">🤖</span> 分析评价
                    </h4>
                    <div style="color: #495057; font-size: 14px; line-height: 1.6;">${item.analysis || '暂无分析'}</div>
                </div>
                
                <div style="background: #fff9db; border: 1px solid #ffec99; border-radius: 8px; padding: 16px;">
                    <h4 style="margin: 0 0 10px 0; color: #856404; font-size: 15px; display: flex; align-items: center;">
                        <span style="font-size: 18px; margin-right: 6px;">💡</span> 优化建议
                    </h4>
                    <div style="color: #495057; font-size: 14px; line-height: 1.6;">${item.suggestion || item.remarks || '暂无建议'}</div>
                </div>
            </div>

            <!-- Raw Data (Collapsed) -->
            <details style="border-top: 1px solid #eee; padding-top: 12px;">
                <summary style="cursor: pointer; color: #adb5bd; font-size: 12px; font-weight: 500; user-select: none;">查看原始 JSON 数据</summary>
                <pre style="margin-top: 12px; background: #212529; color: #f8f9fa; padding: 16px; border-radius: 8px; overflow-x: auto; font-family: 'Consolas', monospace; font-size: 12px; line-height: 1.4;">${rawDataDisplay}</pre>
            </details>
        </div>
    `;
    
    const modal = document.getElementById('scoreDetailModal');
    const container = document.getElementById('scoreDetailContent');
    if (modal && container) {
        container.innerHTML = content;
        modal.style.display = 'block';
    } else {
        // Fallback to KB Detail Modal if Score Detail Modal is missing
        const kbModal = document.getElementById('kbDetailModal');
        const kbContainer = document.getElementById('kbDetailContent');
        if (kbModal && kbContainer) {
            kbContainer.innerHTML = content;
            kbModal.style.display = 'block';
        } else {
            alert('详情模态框未找到');
        }
    }
}

async function clearScoringCache() {
    if (isScoringInProgress() || isScoringPaused()) {
        alert('当前有评分任务正在进行或已暂停，请结束后再清空缓存。');
        return;
    }
    
    try {
        const summary = await api('/scoring/cache_summary');
        if (!summary || !summary.success) {
            throw new Error(summary?.message || '获取评分缓存数量失败');
        }
        const count = summary.count || 0;
        const ok = await showDangerConfirmModal(
            '清空评分缓存确认',
            `即将删除全部评分缓存 ${count} 条。系统会先在本地 instance/backups/scoring_cache 生成 JSON 备份；操作完成后评分列表会变为空。确认继续？`,
            '备份并清空'
        );
        if (!ok) return;

        const res = await api('/scoring/clear_cache', 'POST', { confirm_clear: true, expected_count: count });
        if (res.success) {
            alert(`评分缓存已清空，共删除 ${res.deleted || 0} 条。\n备份文件：${res.backup_path || '未返回'}`);
            loadScoringData();
        } else {
            alert('操作失败: ' + res.message);
        }
    } catch (e) {
        alert('系统错误: ' + e.message);
    }
}

function isScoringInProgress() {
    return !!(scoringRunState && scoringRunState.active);
}

function isScoringPaused() {
    return !!(scoringRunState && scoringRunState.paused);
}

function getScoringElapsedText() {
    if (!scoringRunState.startedAt) return '';
    const elapsed = Math.max(0, Math.round((Date.now() - scoringRunState.startedAt) / 1000));
    if (elapsed < 60) return `${elapsed}s`;
    const minutes = Math.floor(elapsed / 60);
    const seconds = elapsed % 60;
    return `${minutes}m${String(seconds).padStart(2, '0')}s`;
}

function startScoringRun(label, ids, options = {}) {
    const cleanIds = Array.from(new Set((ids || []).filter(Boolean).map(String)));
    scoringRunState = {
        active: true,
        paused: false,
        pauseRequested: false,
        label: label || '评分',
        total: cleanIds.length,
        processed: 0,
        success: 0,
        errors: 0,
        startedAt: Date.now(),
        lastErrors: [],
        failedIds: new Set(),
        pendingIds: cleanIds.slice(),
        options: { ...(options || {}) },
        batchSize: options.batchSize || 20,
        kind: options.kind || '',
        activeIds: new Set(cleanIds)
    };
    if (scoringProgressTimer) clearInterval(scoringProgressTimer);
    scoringProgressTimer = setInterval(updateScoringProgressUI, 1000);
    updateScoringProgressUI();
}

function advanceScoringRun(kind, id) {
    if (!isScoringInProgress()) return;
    const key = id !== undefined && id !== null ? String(id) : '';
    let didAdvance = false;
    if (key && scoringRunState.activeIds.has(key)) {
        scoringRunState.activeIds.delete(key);
        scoringRunState.pendingIds = (scoringRunState.pendingIds || []).filter(x => String(x) !== key);
        scoringRunState.processed += 1;
        didAdvance = true;
    } else if (!key && scoringRunState.processed < scoringRunState.total) {
        scoringRunState.processed += 1;
        didAdvance = true;
    }
    if (!didAdvance) return;
    if (kind === 'error') {
        scoringRunState.errors += 1;
        if (key) scoringRunState.failedIds.add(key);
    } else {
        scoringRunState.success += 1;
        if (key) scoringRunState.failedIds.delete(key);
    }
    updateScoringProgressUI();
}

function addScoringRunError(id, message) {
    if (!isScoringInProgress()) return;
    const err = {
        id: id || '-',
        message: message || 'Unknown error'
    };
    scoringRunState.lastErrors = [err, ...(scoringRunState.lastErrors || [])].slice(0, 5);
}

function finishScoringRun() {
    if (!isScoringInProgress() && !isScoringPaused()) return;
    scoringRunState.active = false;
    scoringRunState.paused = false;
    scoringRunState.pauseRequested = false;
    scoringRunState.pendingIds = [];
    if (scoringRunState.failedIds) scoringRunState.failedIds.clear();
    if (scoringRunState.activeIds) scoringRunState.activeIds.clear();
    if (scoringProgressTimer) {
        clearInterval(scoringProgressTimer);
        scoringProgressTimer = null;
    }
    updateScoringProgressUI();
}

function getScoringProgressText() {
    if (!isScoringInProgress() && !isScoringPaused()) return '';
    const total = scoringRunState.total || 0;
    const processed = Math.min(scoringRunState.processed || 0, total);
    const elapsedText = getScoringElapsedText();
    const suffix = elapsedText ? ` | 用时: ${elapsedText}` : '';
    const stateText = scoringRunState.pauseRequested ? '暂停中' : (scoringRunState.paused ? '已暂停' : (scoringRunState.label || '评分中'));
    return `${stateText}: ${processed}/${total} | 成功: ${scoringRunState.success} | 失败: ${scoringRunState.errors}${suffix}`;
}

function getScoringErrorSummaryText() {
    if ((!isScoringInProgress() && !isScoringPaused()) || !scoringRunState.lastErrors || scoringRunState.lastErrors.length === 0) return '';
    return scoringRunState.lastErrors
        .map(err => `${err.id}: ${err.message}`)
        .join('；');
}

function setScoringButtonLabel(btn, text) {
    if (!btn) return;
    const iconMap = {
        batchScoreBtn: 'fas fa-magic',
        evaluateAllBtn: 'fas fa-bolt',
        pauseScoringBtn: 'fas fa-pause',
        resumeScoringBtn: 'fas fa-play'
    };
    const iconClass = iconMap[btn.id];
    if (iconClass) {
        btn.innerHTML = `<i class="${iconClass}"></i><span>${escapeHtml(text)}</span>`;
    } else {
        btn.textContent = text;
    }
}

function setScoringControlsDisabled(disabled, activeBtn = null) {
    const controlIds = ['syncScoringBtn', 'refreshScoringBtn', 'batchScoreBtn', 'evaluateAllBtn'];
    controlIds.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        if (activeBtn && el === activeBtn) return;
        el.disabled = !!disabled;
    });
    const clearBtn = document.querySelector('button[onclick="clearScoringCache()"]');
    if (clearBtn && (!activeBtn || clearBtn !== activeBtn)) clearBtn.disabled = !!disabled;
}

function updateScoringProgressUI() {
    const btn = document.getElementById('evaluateAllBtn') || document.querySelector('button[onclick="evaluateAll()"]');
    const batchBtn = document.getElementById('batchScoreBtn');
    const pauseBtn = document.getElementById('pauseScoringBtn');
    const resumeBtn = document.getElementById('resumeScoringBtn');
    const progressText = getScoringProgressText();
    
    setScoringControlsDisabled(isScoringInProgress() || isScoringPaused());
    
    if (isScoringInProgress()) {
        if (btn) setScoringButtonLabel(btn, progressText || '评分中...');
        if (batchBtn) setScoringButtonLabel(batchBtn, progressText || '评分中...');
        if (pauseBtn) {
            pauseBtn.disabled = !!scoringRunState.pauseRequested;
            setScoringButtonLabel(pauseBtn, scoringRunState.pauseRequested ? '暂停中...' : '暂停');
        }
        if (resumeBtn) resumeBtn.disabled = true;
    } else if (isScoringPaused()) {
        if (btn) setScoringButtonLabel(btn, progressText || '评分已暂停');
        if (batchBtn) setScoringButtonLabel(batchBtn, progressText || '评分已暂停');
        if (pauseBtn) {
            pauseBtn.disabled = true;
            setScoringButtonLabel(pauseBtn, '暂停');
        }
        if (resumeBtn) resumeBtn.disabled = false;
    } else {
        if (batchBtn) setScoringButtonLabel(batchBtn, '批量评分');
        if (pauseBtn) {
            pauseBtn.disabled = true;
            setScoringButtonLabel(pauseBtn, '暂停');
        }
        if (resumeBtn) resumeBtn.disabled = true;
        updateEvaluateAllButtonLabel();
    }
    
    updateScoringStats();
}

function refreshScoringTableIfVisible() {
    if (currentTab === 'scoringView') {
        renderScoringTable(true);
    } else {
        updateScoringStats();
    }
}

function pauseScoring() {
    if (!isScoringInProgress()) {
        alert(isScoringPaused() ? '评分已经暂停，可以点击“继续评分”恢复。' : '当前没有正在进行的评分任务。');
        return;
    }
    scoringRunState.pauseRequested = true;
    updateScoringProgressUI();
}

function requeueFailedScoringItemsForRetry() {
    if (!scoringRunState || !scoringRunState.failedIds || scoringRunState.failedIds.size === 0) return 0;
    const failedIds = Array.from(scoringRunState.failedIds);
    const pendingSet = new Set((scoringRunState.pendingIds || []).map(String));
    failedIds.forEach(id => {
        pendingSet.add(String(id));
        scoringRunState.activeIds.add(String(id));
    });
    scoringRunState.pendingIds = Array.from(pendingSet);
    scoringRunState.processed = Math.max(0, (scoringRunState.processed || 0) - failedIds.length);
    scoringRunState.errors = Math.max(0, (scoringRunState.errors || 0) - failedIds.length);
    scoringRunState.failedIds.clear();
    scoringRunState.lastErrors = [];
    return failedIds.length;
}

async function resumeScoring() {
    if (!isScoringPaused()) {
        alert('当前没有已暂停的评分任务。');
        return;
    }
    const retryCount = requeueFailedScoringItemsForRetry();
    const pendingIds = (scoringRunState.pendingIds || []).slice();
    if (pendingIds.length === 0) {
        finishScoringRun();
        alert('没有剩余待评分项。');
        return;
    }
    scoringRunState.active = true;
    scoringRunState.paused = false;
    scoringRunState.pauseRequested = false;
    scoringRunState.startedAt = Date.now();
    if (scoringProgressTimer) clearInterval(scoringProgressTimer);
    scoringProgressTimer = setInterval(updateScoringProgressUI, 1000);
    updateScoringProgressUI();
    if (retryCount > 0) {
        console.info(`已将 ${retryCount} 个失败项重新加入继续评分队列`);
    }
    try {
        const result = await continueScoringRun();
        if (result && result.completed) {
            if (result.kind === 'batchSelected') {
                selectedScoringRows.clear();
                document.querySelectorAll('.scoring-row-check').forEach(cb => cb.checked = false);
            }
            alert(`${result.label || '评分'}完成。\n成功: ${result.success}\n失败: ${result.errors}`);
            loadScoringData({ force: true });
        }
    } catch (e) {
        alert('继续评分异常: ' + e.message);
    }
}

async function continueScoringRun() {
    const batchSize = scoringRunState.batchSize || 20;
    const useCache = scoringRunState.options && scoringRunState.options.useCache !== undefined
        ? !!scoringRunState.options.useCache
        : (document.getElementById('useCacheCb') ? document.getElementById('useCacheCb').checked : true);

    while (isScoringInProgress() && (scoringRunState.pendingIds || []).length > 0) {
        if (scoringRunState.pauseRequested) {
            scoringRunState.active = false;
            scoringRunState.paused = true;
            if (scoringProgressTimer) {
                clearInterval(scoringProgressTimer);
                scoringProgressTimer = null;
            }
            updateScoringProgressUI();
            return { paused: true };
        }

        const batchIds = scoringRunState.pendingIds.slice(0, batchSize);
        await streamEvaluate(batchIds, null, '', { useCache });
    }

    if (isScoringInProgress()) {
        const success = scoringRunState.success;
        const errors = scoringRunState.errors;
        const label = scoringRunState.label;
        const kind = scoringRunState.kind;
        finishScoringRun();
        return { completed: true, success, errors, label, kind };
    }
    return { completed: !isScoringPaused() };
}

// Shared streaming evaluation logic
async function streamEvaluate(ids, btn, originalText, options = {}) {
    const ownsRunState = !isScoringInProgress();
    if (ownsRunState) {
        startScoringRun(options.runLabel || '评分中', ids);
    }
    
    if (btn) {
        btn.disabled = true;
        setScoringButtonLabel(btn, '准备评分...');
    }

    // 1. Mark selected rows as "scoring" in UI immediately
    ids.forEach(id => {
        const item = currentScoringData.find(i => (i.kb_id || i.id) === id);
        if (item) {
            item.status = 'scoring';
        }
    });
    refreshScoringTableIfVisible(); // Re-render to show spinners when the scoring view is visible

    try {
        const useCache =
            options && options.useCache !== undefined
                ? !!options.useCache
                : (document.getElementById('useCacheCb') ? document.getElementById('useCacheCb').checked : true);
        
        // Use fetch for streaming response
        const response = await fetch('/api/scoring/evaluate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream' // Request SSE-like stream
            },
            body: JSON.stringify({ ids: ids, use_cache: useCache })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let successCount = 0;
        let errorCount = 0;

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const msg = JSON.parse(line);
                    
                    if (msg.type === 'result') {
                        successCount++;
                        // Update local data with result
                        const result = msg.data;
                        const itemIndex = currentScoringData.findIndex(i => (i.kb_id || i.id) === result.kb_id);
                        advanceScoringRun('success', result.kb_id);
                        
                        if (itemIndex !== -1) {
                            // Update item fields
                            const item = currentScoringData[itemIndex];
                            item.total_score = result.total_score;
                            item.quality = result.quality;
                            item.compliance = result.compliance;
                            item.timeliness = result.timeliness;
                            item.utility = result.utility;
                            item.redundancy = result.redundancy;
                            item.multimedia = result.multimedia;
                            item.suggestion = result.suggestion;
                            item.analysis = result.analysis;
                            item.status = 'scored'; // Mark as scored
                        }
                        refreshScoringTableIfVisible();
                        
                        if (btn && !isScoringInProgress()) setScoringButtonLabel(btn, `评分中 (${successCount}/${ids.length})`);

                    } else if (msg.type === 'error') {
                        errorCount++;
                        console.error('Score error for ID', msg.id, msg.message);
                        const item = currentScoringData.find(i => (i.kb_id || i.id) === msg.id);
                        if (item) item.status = 'unscored'; // Revert status
                        addScoringRunError(msg.id, msg.message);
                        advanceScoringRun('error', msg.id);
                        refreshScoringTableIfVisible();
                    } else if (msg.type === 'done') {
                        if (ownsRunState && scoringRunState && scoringRunState.activeIds && scoringRunState.activeIds.size === 0) {
                            finishScoringRun();
                        }
                    }
                } catch (e) {
                    console.error('JSON parse error', e, line);
                }
            }
        }
        
        if (isScoringInProgress() && scoringRunState.activeIds && scoringRunState.activeIds.size > 0 && ownsRunState) {
            Array.from(scoringRunState.activeIds).forEach(id => {
                addScoringRunError(id, '评分连接已结束但未收到结果');
                const item = currentScoringData.find(i => (i.kb_id || i.id) === id);
                if (item && item.status === 'scoring') item.status = 'unscored';
                advanceScoringRun('error', id);
            });
            refreshScoringTableIfVisible();
        }
        
        return { success: successCount, errors: errorCount };
        
    } catch (e) {
        // Revert status of stuck items
        ids.forEach(id => {
             const item = currentScoringData.find(i => (i.kb_id || i.id) === id);
             if (item && item.status === 'scoring') item.status = 'unscored';
             addScoringRunError(id, e.message);
             advanceScoringRun('error', id);
        });
        refreshScoringTableIfVisible();
        throw e;
    } finally {
        if (ownsRunState) finishScoringRun();
        if (btn && !isScoringInProgress()) {
            btn.disabled = false;
            btn.innerText = originalText;
        }
    }
}

async function batchEvaluateSelected() {
    if (isScoringInProgress() || isScoringPaused()) {
        alert('当前已有评分任务正在进行，请等待完成后再发起新的评分。');
        return;
    }
    
    if (selectedScoringRows.size === 0) {
        alert("请先选择要评分的条目");
        return;
    }
    
    // Convert Set to Array
    const ids = Array.from(selectedScoringRows);

    if (!confirm(`确定要对选中的 ${ids.length} 条记录进行评分吗？\n评分将逐条进行，请勿关闭页面。`)) return;

    const btn = document.getElementById('batchScoreBtn');
    const batchSize = 4;
    
    try {
        startScoringRun('批量评分', ids, { useCache: false, batchSize, kind: 'batchSelected' });
        const result = await continueScoringRun();
        if (result && result.paused) {
            alert(`批量评分已暂停。\n已处理: ${scoringRunState.processed}/${scoringRunState.total}\n成功: ${scoringRunState.success}\n失败: ${scoringRunState.errors}`);
            return;
        }
        selectedScoringRows.clear();
        document.querySelectorAll('.scoring-row-check').forEach(cb => cb.checked = false);
        alert(`评分结束。\n成功: ${result?.success ?? 0}\n失败: ${result?.errors ?? 0}`);
    } catch (e) {
        alert('评分请求异常: ' + e.message);
    } finally {
	        if (!isScoringPaused()) finishScoringRun();
	        if (btn && !isScoringInProgress() && !isScoringPaused()) {
	            btn.disabled = false;
	            setScoringButtonLabel(btn, '批量评分');
	        }
	    }
}

function updateEvaluateAllButtonLabel() {
	    const btn = document.getElementById('evaluateAllBtn') || document.querySelector('button[onclick="evaluateAll()"]');
	    if (!btn || btn.disabled) return;
	    const useCache = document.getElementById('useCacheCb') ? document.getElementById('useCacheCb').checked : true;
	    setScoringButtonLabel(btn, useCache ? '评分未缓存项' : '全量评分');
}

async function evaluateAll() {
	    if (isScoringInProgress() || isScoringPaused()) {
	        alert('当前已有评分任务正在进行，请等待完成后再发起新的评分。');
	        return;
	    }
	    
	    // Get all filtered IDs from currentScoringData (which contains all loaded data)
	    // Re-apply current filter
	    const filters = getScoringFilterValues();
	    const useCache = document.getElementById('useCacheCb') ? document.getElementById('useCacheCb').checked : true;
	    
	    const filteredData = currentScoringData.filter(item => {
	        if (!scoringItemMatchesFilters(item, filters)) return false;
	        if (useCache && item.status === 'scored') return false;
	        return true;
	    });
    const actionLabel = useCache ? '评分未缓存项' : '全量评分';
    
    if (filteredData.length === 0) {
        alert(useCache ? "当前筛选条件下没有未缓存的可评分记录" : "当前筛选条件下没有可评分的记录");
        return;
    }

    if (!confirm(`确定要对符合筛选条件的 ${filteredData.length} 条记录进行${actionLabel}吗？\n注意：这将分批处理，请勿关闭页面。`)) return;

    const ids = filteredData.map(item => item.kb_id || item.id);
    const batchSize = 4; // Keep pause responsive; backend still uses configured concurrency.
    
    // Find button - assumes onclick="evaluateAll()"
    const btn = document.getElementById('evaluateAllBtn') || document.querySelector('button[onclick="evaluateAll()"]');
    const originalText = btn ? btn.innerText : (useCache ? '评分未缓存项' : '🚀 全量评分');
    
    // Override button text update in streamEvaluate to show batch progress
    // But streamEvaluate takes btn and updates it directly.
    // We can pass a proxy object or just let it update, then we overwrite?
    // Better: let streamEvaluate handle one batch, we update overall progress.
    
    try {
        startScoringRun(actionLabel, ids, { useCache, batchSize, kind: 'evaluateAll' });
        const result = await continueScoringRun();
        if (result && result.paused) {
            alert(`${actionLabel}已暂停。\n已处理: ${scoringRunState.processed}/${scoringRunState.total}\n成功: ${scoringRunState.success}\n失败: ${scoringRunState.errors}`);
            return;
        }
        alert(`${actionLabel}完成。\n成功: ${result?.success ?? 0}\n失败: ${result?.errors ?? 0}`);
        loadScoringData({ force: true });
        
    } catch (e) {
        alert('系统错误: ' + e.message);
    } finally {
        if (!isScoringPaused()) finishScoringRun();
        if (btn && !isScoringInProgress() && !isScoringPaused()) {
            btn.disabled = false;
            btn.innerText = originalText;
            updateEvaluateAllButtonLabel();
        }
    }
}
        

function updateScoringStats() {
    const statsEl = document.getElementById('scoringStats');
    if (!statsEl) return;
    
    const total = currentScoringData.length;
    const scoredItems = currentScoringData.filter(i => i.status === 'scored');
    const scored = scoredItems.length;
    const scoredTotal = scoredItems.reduce((acc, item) => acc + (getScoringItemTotalScore(item) || 0), 0);
    const avg = scored ? (scoredTotal / scored).toFixed(1) : '0.0';
    const selected = selectedScoringRows ? selectedScoringRows.size : 0;
    const progressText = getScoringProgressText();
    const progressHtml = progressText ? `<span class="scoring-progress-inline">${escapeHtml(progressText)}</span>` : '';
    const errorText = getScoringErrorSummaryText();
    const errorHtml = errorText ? `<span class="scoring-error-inline" title="${escapeHtml(errorText)}">最近错误: ${escapeHtml(errorText)}</span>` : '';
    
    statsEl.innerHTML = `
        <span class="scoring-stat-pill">总数 <b>${total}</b></span>
        <span class="scoring-stat-pill">已评 <b>${scored}</b></span>
        <span class="scoring-stat-pill is-accent">平均分 <b>${avg}</b></span>
        ${selected ? `<span class="scoring-stat-pill is-selected">已选 <b>${selected}</b></span>` : ''}
        ${progressHtml}
        ${errorHtml}
    `;
}


function sampleScoring(n) {
    selectedScoringRows.clear();
    // Reset all checkboxes visually
    document.querySelectorAll('.scoring-row-check').forEach(cb => cb.checked = false);
    
    // Filter out already scored items first, if none, use all
    const unscored = currentScoringData.filter(i => i.status !== 'scored');
    const pool = unscored.length > 0 ? unscored : currentScoringData;
    
    if (pool.length === 0) {
        alert('没有可供抽样的数据');
        return;
    }
    
    // Random sample
    const sample = [];
    const poolCopy = [...pool];
    
    for (let i = 0; i < n && poolCopy.length > 0; i++) {
        const idx = Math.floor(Math.random() * poolCopy.length);
        sample.push(poolCopy[idx]);
        poolCopy.splice(idx, 1);
    }
    
    // Add to selection
    sample.forEach(item => selectedScoringRows.add(item.kb_id || item.id));
    
    // Temporarily replace currentScoringData with sample to show only sampled items
    // Store original data to restore later if needed (though a refresh restores it)
    // Actually, renderScoringTable uses currentScoringData.
    // To show ONLY sampled data, we can filter currentScoringData in place or modify renderScoringTable.
    // A simpler approach is to set a global filter flag or just overwrite currentScoringData temporarily?
    // But overwriting loses the rest of the data. 
    // Better: let's modify renderScoringTable to support passing data directly OR
    // just filter currentScoringData to only include the sampled ones for display.
    
    // Let's filter currentScoringData to only the sampled items for display purpose.
    // But we need to keep the full dataset if user wants to cancel. 
    // Since this is a "sample view", maybe it's fine to just show these.
    // User can click "Sync" or refresh to get back all data.
    
    // To be safe, let's just backup if not backed up? No, simpler is to just filter.
    currentScoringData = sample;
    scoringPage = 1;
    
    // Re-render
    renderScoringTable(false); // No need to filter by inputs, just show the sample
    
    // Ensure checkboxes are checked for the visible rows
    // (renderScoringTable already checks selectedScoringRows)
    
    alert(`已随机抽取 ${sample.length} 条记录并展示。\n(如需查看全部数据，请刷新页面或重新同步)`);
}


function exportScores() {
    if(!confirm("确定要导出全量评分数据吗？")) return;
    window.location.href = '/api/scoring/export';
}

async function syncScoringData() {
    if (isScoringInProgress() || isScoringPaused()) {
        alert('当前有评分任务正在进行或已暂停，请结束后再同步此刻库。');
        return;
    }
    
    const btn = document.getElementById('syncScoringBtn');
    const originalText = btn ? btn.innerHTML : '';
    
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 同步中...';
    }
    
    try {
        const res = await api('/scoring/sync', 'POST');
        if (res.success) {
            alert(`同步成功！\n新增: ${res.added || 0} 条\n更新: ${res.updated || 0} 条\n删除: ${res.deleted || 0} 条`);
            loadScoringData();
        } else {
            alert('同步失败: ' + res.message);
        }
    } catch (e) {
        alert('同步异常: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

async function openApiConfigModal() {
    const modal = document.getElementById('apiConfigModal');
    if (!modal) return;
    const titleEl = modal.querySelector('.modal-header h3');
    if (titleEl) titleEl.textContent = 'API 配置';
    const apiFields = document.getElementById('apiConfigFields');
    const aiFields = document.getElementById('aiPromptFields');
    if (apiFields) apiFields.style.display = 'block';
    if (aiFields) aiFields.style.display = 'none';
    
    try {
        const config = await api('/scoring/config');
        if (config) {
            document.getElementById('apiKeyInput').value = config.api_key || '';
            document.getElementById('baseUrlInput').value = config.base_url || '';
            document.getElementById('modelNameInput').value = config.model || '';
            updateApiConfigStatus(config);
        }
        modal.style.display = 'block';
        const apiKey = document.getElementById('apiKeyInput');
        if (apiKey) apiKey.focus();
    } catch (e) {
        alert('加载配置失败: ' + e.message);
    }
}

function updateApiConfigStatus(config, savedAt = '') {
    const statusEl = document.getElementById('apiConfigStatus');
    if (!statusEl) return;
    const apiKey = config && config.api_key ? String(config.api_key) : '';
    const baseUrl = config && config.base_url ? String(config.base_url) : '';
    const model = config && config.model ? String(config.model) : '';
    const configured = !!apiKey.trim();
    const status = config && config.config_status ? config.config_status : (configured ? '已配置' : '未配置');
    const keyPrefix = config && config.api_key_prefix ? String(config.api_key_prefix) : apiKey.slice(0, 8);
    const keySuffix = config && config.api_key_suffix ? String(config.api_key_suffix) : (apiKey ? apiKey.slice(-6) : '');
    const suffix = savedAt ? ` | 保存时间: ${savedAt}` : '';
    const titleEl = document.querySelector('#apiConfigModal .modal-header h3');
    const title = titleEl && titleEl.textContent ? titleEl.textContent.trim() : '';
    const scope = title.includes('AI') ? 'AI配置' : '知识库评分配置';
    const keyHint = configured ? `${keyPrefix}...${keySuffix}` : '未填写';
    statusEl.textContent = `${scope}：${status} | Key: ${keyHint} | Key长度: ${apiKey.length} | Base URL: ${baseUrl || '未填写'} | Model: ${model || '未填写'}${suffix}`;
    statusEl.style.color = configured ? '#166534' : '#b45309';
}

async function openAiConfigModal() {
    const modal = document.getElementById('apiConfigModal');
    if (!modal) return;
    const titleEl = modal.querySelector('.modal-header h3');
    if (titleEl) titleEl.textContent = 'AI 配置';
    const apiFields = document.getElementById('apiConfigFields');
    const aiFields = document.getElementById('aiPromptFields');
    if (apiFields) apiFields.style.display = 'block';
    if (aiFields) aiFields.style.display = 'block';

    try {
        const config = await api('/ai/config');
        const defaultPrompts = {
            question:
                "你是一个企业知识库的“问题区 AI 润色助手”。请在严格保留原始含义的前提下，对输入的 question 做整体润色，" +
                "使其成为适合在线知识库与智能客服检索的标准问句。\n" +
                "输出必须为严格 JSON：\n" +
                "{\n" +
                "  \"question\": string|null,\n" +
                "  \"keywords\": null,\n" +
                "  \"difficulty\": null,\n" +
                "  \"notes\": string|null\n" +
                "}\n" +
                "变量：{{task}} {{question}}",
            answer_structure:
                "你是知识库内容结构化处理专家，聚焦结构化处理，不做标签化。\n" +
                "任务：对输入文本进行通用结构化处理，输出可直接录入的 Markdown。\n" +
                "规则：去噪精简；按顺序拆解模块（有则写，无则跳过）：接入范围→技术底座→服务能力→服务方式→核心优势；模块内用 - 列表；核心名词加粗；生成 ## 标题（≤20字）；扩写 3-5 组问答对；无多余解释。\n" +
                "输出必须为严格 JSON：{\"answer\": string, \"urls\": string[]|null, \"notes\": string|null}\n" +
                "结构要求（强约束 + 软容错）：\n" +
                "- answer 必须包含两部分，并按此顺序输出：### 结构化正文、### 扩写问答对。\n" +
                "- 结构化正文必须包含 ## 标题；模块顺序固定为：接入范围→技术底座→服务能力→服务方式→核心优势；允许缺失模块直接跳过（不要硬凑）。\n" +
                "- 扩写问答对目标 3-5 组；若信息不足无法覆盖 3 组，也必须输出已能生成的问答对，并在 notes 说明原因。\n" +
                "变量：{{task}} {{question}} {{answer}} {{urls}}",
            answer_fault:
                "你是知识库结构化处理专家，核心聚焦结构化处理，不进行任何标签化操作。\n" +
                "任务：将产品故障类客服文本结构化输出为可直接录入的 Markdown，且扩写 3-5 组故障相关问答对。\n" +
                "规则：去噪精简；按顺序拆解模块（有则写，无则跳过）：接入范围（适用型号/场景）→技术底座（涉及则写）→服务能力（可排查/解决的故障）→服务方式（排查/解决步骤）→核心优势（客观描述）。标题 ≤20 字，含产品+故障关键词；模块用 ###，条目用 -；核心名词加粗；无多余解释。\n" +
                "输出必须为严格 JSON：{\"answer\": string, \"urls\": string[]|null, \"notes\": string|null}。\n" +
                "结构要求（强约束 + 软容错）：answer 必须包含 ### 结构化正文 与 ### 扩写问答对；模块顺序固定但允许缺失跳过；问答对目标 3-5 组，若不足 3 组需在 notes 说明原因。\n" +
                "变量：{{task}} {{question}} {{answer}} {{urls}}",
            answer_usage:
                "你是知识库结构化处理专家，核心聚焦结构化处理，不进行任何标签化操作。\n" +
                "任务：将使用方法类客服文本结构化输出为可直接录入的 Markdown，且扩写 3-5 组操作相关问答对。\n" +
                "规则：去噪精简；按顺序拆解模块（有则写，无则跳过）：接入范围（适用型号/场景/渠道）→技术底座（涉及则写）→服务能力（可实现功能/需求）→服务方式（操作步骤+注意事项）→核心优势（客观描述）。标题 ≤20 字，含产品+使用功能关键词；模块用 ###，条目用 -；核心名词加粗；无多余解释。\n" +
                "输出必须为严格 JSON：{\"answer\": string, \"urls\": string[]|null, \"notes\": string|null}。\n" +
                "结构要求（强约束 + 软容错）：answer 必须包含 ### 结构化正文 与 ### 扩写问答对；模块顺序固定但允许缺失跳过；问答对目标 3-5 组，若不足 3 组需在 notes 说明原因。\n" +
                "变量：{{task}} {{question}} {{answer}} {{urls}}",
            answer_feature:
                "你是知识库结构化处理专家，核心聚焦结构化处理，不进行任何标签化操作。\n" +
                "任务：将功能介绍类客服文本结构化输出为可直接录入的 Markdown，且扩写 3-5 组功能相关问答对。\n" +
                "规则：去噪精简；按顺序拆解模块（有则写，无则跳过）：接入范围（适用型号/渠道/用户）→技术底座（核心技术/系统/模型）→服务能力（功能作用/效果/场景）→服务方式（开启/使用路径简述）→核心优势（客观描述）。标题 ≤20 字，含产品+功能关键词；模块用 ###，条目用 -；核心名词加粗；无多余解释。\n" +
                "输出必须为严格 JSON：{\"answer\": string, \"urls\": string[]|null, \"notes\": string|null}。\n" +
                "结构要求（强约束 + 软容错）：answer 必须包含 ### 结构化正文 与 ### 扩写问答对；模块顺序固定但允许缺失跳过；问答对目标 3-5 组，若不足 3 组需在 notes 说明原因。\n" +
                "变量：{{task}} {{question}} {{answer}} {{urls}}",
            // legacy fallback key, kept for older UI/server logic
            answer: "",
            similar:
                "你是一个企业知识库的编辑助手。请基于 question 生成 3-5 条相似问题，表述要多样。\n" +
                "输出必须为严格 JSON：\n" +
                "{\n" +
                "  \"items\": [\n" +
                "    {\"text\": string, \"difficulty\": number}\n" +
                "  ],\n" +
                "  \"notes\": string|null\n" +
                "}\n" +
                "变量：{{question}} {{target_min}} {{target_max}} {{count_min}} {{count_max}} {{difficulty}}"
        };

        if (config) {
            document.getElementById('apiKeyInput').value = config.api_key || '';
            document.getElementById('baseUrlInput').value = config.base_url || '';
            document.getElementById('modelNameInput').value = config.model || '';
            updateApiConfigStatus(config);

            const prompts = (config.ai_prompts && typeof config.ai_prompts === 'object') ? config.ai_prompts : {};
            const qEl = document.getElementById('aiPromptQuestionInput');
            const aLegacyEl = document.getElementById('aiPromptAnswerInput');
            const aStructureEl = document.getElementById('aiPromptAnswerStructureInput');
            const aFaultEl = document.getElementById('aiPromptAnswerFaultInput');
            const aUsageEl = document.getElementById('aiPromptAnswerUsageInput');
            const aFeatureEl = document.getElementById('aiPromptAnswerFeatureInput');
            const sEl = document.getElementById('aiPromptSimilarInput');
            if (qEl) qEl.value = (prompts.question || '').trim() || defaultPrompts.question;

            const legacy = (prompts.answer || '').trim();
            const savedStructure = (prompts.answer_structure || '').trim();
            const savedFault = (prompts.answer_fault || '').trim();
            const savedUsage = (prompts.answer_usage || '').trim();
            const savedFeature = (prompts.answer_feature || '').trim();
            const hasAnySavedAnswerPrompt = !!(savedStructure || savedFault || savedUsage || savedFeature || legacy);

            // 答案区：以“已保存/正在录入”为主，仅在从未配置过时才自动填充推荐模板
            if (aStructureEl) aStructureEl.value = hasAnySavedAnswerPrompt ? (savedStructure || legacy) : defaultPrompts.answer_structure;
            if (aFaultEl) aFaultEl.value = hasAnySavedAnswerPrompt ? (savedFault || legacy) : defaultPrompts.answer_fault;
            if (aUsageEl) aUsageEl.value = hasAnySavedAnswerPrompt ? (savedUsage || legacy) : defaultPrompts.answer_usage;
            if (aFeatureEl) aFeatureEl.value = hasAnySavedAnswerPrompt ? (savedFeature || legacy) : defaultPrompts.answer_feature;
            if (aLegacyEl) aLegacyEl.value = legacy;

            if (sEl) sEl.value = (prompts.similar || '').trim() || defaultPrompts.similar;

            const typeCfgEl = document.getElementById('aiQuestionTypeConfigJsonInput');
            if (typeCfgEl) typeCfgEl.value = (config.question_type_config_json || '').trim();
        }

        modal.style.display = 'block';
        const target = document.getElementById('aiPromptQuestionInput') || document.getElementById('aiPromptAnswerStructureInput');
        if (target && typeof target.scrollIntoView === 'function') {
            target.scrollIntoView({ block: 'center' });
            target.focus();
        }
    } catch (e) {
        alert('加载配置失败: ' + e.message);
    }
}

async function saveApiConfig() {
    const apiKey = document.getElementById('apiKeyInput').value.trim();
    const baseUrl = document.getElementById('baseUrlInput').value.trim();
    const model = document.getElementById('modelNameInput').value.trim();
    const aiPromptQuestion = (document.getElementById('aiPromptQuestionInput')?.value || '').trim();
    const aiPromptAnswerStructure = (document.getElementById('aiPromptAnswerStructureInput')?.value || '').trim();
    const aiPromptAnswerFault = (document.getElementById('aiPromptAnswerFaultInput')?.value || '').trim();
    const aiPromptAnswerUsage = (document.getElementById('aiPromptAnswerUsageInput')?.value || '').trim();
    const aiPromptAnswerFeature = (document.getElementById('aiPromptAnswerFeatureInput')?.value || '').trim();
    // legacy single template (compat): store as answer too
    const aiPromptAnswer = aiPromptAnswerStructure;
    const aiPromptSimilar = (document.getElementById('aiPromptSimilarInput')?.value || '').trim();
    const questionTypeConfigJson = (document.getElementById('aiQuestionTypeConfigJsonInput')?.value || '').trim();
    const titleEl = document.querySelector('#apiConfigModal .modal-header h3');
    const title = (titleEl && titleEl.textContent) ? titleEl.textContent.trim() : '';
    const isAiConfig = title.includes('AI');

    try {
        const payload = isAiConfig ? {
            api_key: apiKey,
            base_url: baseUrl,
            model: model,
            ai_prompts: {
                question: aiPromptQuestion,
                // legacy fallback
                answer: aiPromptAnswer,
                // split templates (faster & more stable)
                answer_structure: aiPromptAnswerStructure,
                answer_fault: aiPromptAnswerFault,
                answer_usage: aiPromptAnswerUsage,
                answer_feature: aiPromptAnswerFeature,
                similar: aiPromptSimilar
            },
            question_type_config_json: questionTypeConfigJson
        } : {
            api_key: apiKey,
            base_url: baseUrl,
            model: model
        };

        const endpoint = isAiConfig ? '/ai/config' : '/scoring/config';
        const res = await api(endpoint, 'POST', payload);

        if (res.success) {
            if (res.config) {
                document.getElementById('apiKeyInput').value = res.config.api_key || '';
                document.getElementById('baseUrlInput').value = res.config.base_url || '';
                document.getElementById('modelNameInput').value = res.config.model || '';
                updateApiConfigStatus(res.config, new Date().toLocaleTimeString());
            }
            openFeedbackModal('保存成功', '配置已保存并已回读确认');
            document.getElementById('apiConfigModal').style.display = 'none';
        } else {
            openFeedbackModal('保存失败', '保存失败：' + (res.message || '未知错误'));
        }
    } catch (e) {
        openFeedbackModal('保存异常', '保存异常：' + (e?.message || String(e)));
    }
}

async function testApiConfig() {
    const apiKey = document.getElementById('apiKeyInput').value.trim();
    const baseUrl = document.getElementById('baseUrlInput').value.trim();
    const model = document.getElementById('modelNameInput').value.trim();
    const titleEl = document.querySelector('#apiConfigModal .modal-header h3');
    const title = (titleEl && titleEl.textContent) ? titleEl.textContent.trim() : '';
    const isAiConfig = title.includes('AI');
    const endpoint = isAiConfig ? '/ai/test_config' : '/scoring/test_config';

    updateApiConfigStatus({ api_key: apiKey, base_url: baseUrl, model, config_status: '测试中' });
    try {
        const res = await api(endpoint, 'POST', { api_key: apiKey, base_url: baseUrl, model });
        if (res.config) updateApiConfigStatus({ ...res.config, config_status: res.success ? '测试通过' : '测试失败' });
        const preview = res.config && res.config.response_preview ? `\n返回预览: ${res.config.response_preview}` : '';
        if (res.success) {
            openFeedbackModal('测试成功', `${res.message || 'API 连接测试成功'}${preview}`);
        } else {
            openFeedbackModal('测试失败', res.message || 'API 连接测试失败');
        }
    } catch (e) {
        updateApiConfigStatus({ api_key: apiKey, base_url: baseUrl, model, config_status: '测试异常' });
        openFeedbackModal('测试异常', e?.message || String(e));
    }
}

async function openScoringCriteriaModal() {
    const modal = document.getElementById('scoringCriteriaModal');
    if (!modal) return;
    
    try {
        const res = await api('/scoring/prompt');
        if (res.prompt !== undefined) {
            document.getElementById('systemPromptInput').value = res.prompt;
        }
        modal.style.display = 'block';
    } catch (e) {
        alert('加载评分标准失败: ' + e.message);
    }
}

async function saveScoringCriteria() {
    const prompt = document.getElementById('systemPromptInput').value;
    
    try {
        const res = await api('/scoring/prompt', 'POST', { prompt: prompt });
        if (res.success) {
            alert('评分标准已保存');
            document.getElementById('scoringCriteriaModal').style.display = 'none';
        } else {
            alert('保存失败: ' + (res.message || '未知错误'));
        }
    } catch (e) {
        alert('保存异常: ' + e.message);
    }
}

// ==========================================
// Product Manager Logic
// ==========================================
let productCatalog = {};
let productCatalogBaseline = {};
let currentCategory = null;

async function openProductManager() {
    const modal = document.getElementById('productManagerModal');
    if (modal) {
        modal.style.display = 'block';
        await loadProductManagerData();
    }
}

function closeProductManager() {
    const modal = document.getElementById('productManagerModal');
    if (modal) {
        modal.style.display = 'none';
        // Refresh KB Edit Modal product list if open
        const kbEditModal = document.getElementById('kbEditModal');
        if (kbEditModal && kbEditModal.style.display !== 'none') {
            loadProductCatalogForModal();
        }
    }
}

async function loadProductManagerData() {
    try {
        const res = await api('/kb/product_catalog');
        productCatalog = res || {};
        productCatalogBaseline = JSON.parse(JSON.stringify(productCatalog));
        
        // Verify if currentCategory still exists in the new catalog
        if (currentCategory && !productCatalog.hasOwnProperty(currentCategory)) {
            currentCategory = null;
        }
        
        renderProductCategories();
        
        if (currentCategory) {
            selectProductCategory(currentCategory);
        } else {
            // Reset right side UI
            const title = document.getElementById('currentCategoryTitle');
            const deleteBtn = document.getElementById('deleteCategoryBtn');
            const addContainer = document.getElementById('addModelContainer');
            const list = document.getElementById('productModelList');
            
            if (title) title.textContent = '请选择分类';
            if (deleteBtn) deleteBtn.classList.add('d-none');
            if (addContainer) addContainer.classList.add('d-none');
            if (list) {
                list.innerHTML = `
                    <div class="pm-empty-state">
                        <i class="fas fa-arrow-left" style="font-size: 24px; margin-bottom: 10px; opacity: 0.5;"></i>
                        请先在左侧选择一个分类
                    </div>
                `;
            }
        }
    } catch (e) {
        showToast('加载产品目录失败: ' + e.message, 'error');
    }
}

function summarizeProductCatalogImpact(impact) {
    impact = impact || {};
    const removed = impact.removed_models || [];
    const orphans = impact.orphan_models || [];
    const removedText = removed.length ? removed.slice(0, 12).join('、') + (removed.length > 12 ? '...' : '') : '无';
    const orphanText = orphans.length ? orphans.slice(0, 12).join('、') + (orphans.length > 12 ? '...' : '') : '无';
    return [
        `删除型号：${impact.removed_model_count || 0} 个（${removedText}）`,
        `将删除矩阵列：${impact.matrix_column_count || 0} 个`,
        `将删除矩阵数据行：${impact.matrix_row_count || 0} 条`,
        `孤儿矩阵型号：${impact.orphan_model_count || 0} 个（${orphanText}），对应 ${impact.orphan_row_count || 0} 条数据`,
        '该操作会同步清理矩阵列与不在型号库中的矩阵数据，请确认差异无误。'
    ].join('\n');
}

function renderProductCategories() {
    const list = document.getElementById('productCategoryList');
    if (!list) return;
    
    list.innerHTML = '';
    Object.keys(productCatalog).forEach(cat => {
        const div = document.createElement('div');
        div.className = 'pm-category-item';
        if (cat === currentCategory) {
            div.classList.add('active');
        }
        
        const count = (productCatalog[cat] || []).length;
        
        div.innerHTML = `
            <span>${cat}</span>
            <span class="pm-category-count">${count}</span>
        `;
        div.onclick = () => selectProductCategory(cat);
        list.appendChild(div);
    });
}

function selectProductCategory(category) {
    currentCategory = category;
    renderProductCategories(); // Update active state
    
    const title = document.getElementById('currentCategoryTitle');
    const deleteBtn = document.getElementById('deleteCategoryBtn');
    const addContainer = document.getElementById('addModelContainer');
    
    if (title) title.textContent = category;
    if (deleteBtn) deleteBtn.classList.remove('d-none');
    if (addContainer) addContainer.classList.remove('d-none');
    
    renderProductModels(category);
}

function renderProductModels(category) {
    const list = document.getElementById('productModelList');
    if (!list) return;
    
    const models = productCatalog[category] || [];
    if (models.length === 0) {
        list.innerHTML = '<div class="pm-empty-state">暂无型号</div>';
        return;
    }
    
    list.innerHTML = '';
    models.forEach(model => {
        const div = document.createElement('div');
        div.className = 'pm-model-chip';
        
        const name = document.createElement('span');
        name.textContent = model;
        name.title = model;
        
        const del = document.createElement('i');
        del.className = 'fas fa-times pm-model-delete';
        del.title = '删除型号';
        del.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteProductModel(model);
        });
        
        div.appendChild(name);
        div.appendChild(del);
        list.appendChild(div);
    });
}

function showAddCategoryInput() {
    const div = document.getElementById('addCategoryInputDiv');
    const btn = document.getElementById('showAddCategoryBtn');
    if (div) div.classList.remove('d-none');
    if (btn) btn.classList.add('d-none');
}

function hideAddCategoryInput() {
    const div = document.getElementById('addCategoryInputDiv');
    const btn = document.getElementById('showAddCategoryBtn');
    if (div) div.classList.add('d-none');
    if (btn) btn.classList.remove('d-none');
    const input = document.getElementById('newCategoryName');
    if (input) input.value = '';
}

async function addProductCategory() {
    const input = document.getElementById('newCategoryName');
    if (!input) return;
    const name = input.value.trim();
    if (!name) return;
    
    if (productCatalog[name]) {
        showToast('分类已存在', 'warning');
        return;
    }
    
    productCatalog[name] = [];
    try {
        await saveProductCatalog();
        hideAddCategoryInput();
        renderProductCategories();
        selectProductCategory(name);
        showToast('分类添加成功', 'success');
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
        delete productCatalog[name]; // Revert
    }
}

async function deleteCurrentCategory() {
    if (!currentCategory) return;
    if (!confirm(`确定要删除分类 "${currentCategory}" 及其所有型号吗？`)) return;
    
    const oldCatalog = JSON.parse(JSON.stringify(productCatalog));
    delete productCatalog[currentCategory];
    
    try {
        await saveProductCatalog();
        currentCategory = null;
        document.getElementById('currentCategoryTitle').textContent = '请选择分类';
        document.getElementById('deleteCategoryBtn').classList.add('d-none');
        document.getElementById('addModelContainer').classList.add('d-none');
        document.getElementById('productModelList').innerHTML = '<div class="text-muted text-center mt-20">请先在左侧选择一个分类</div>';
        renderProductCategories();
        showToast('分类删除成功', 'success');
    } catch (e) {
        showToast('删除失败: ' + e.message, 'error');
        productCatalog = oldCatalog; // Revert
    }
}

async function addProductModel() {
    if (!currentCategory) return;
    const input = document.getElementById('newModelName');
    if (!input) return;
    const name = input.value.trim();
    if (!name) return;
    
    if (productCatalog[currentCategory].includes(name)) {
        showToast('型号已存在', 'warning');
        return;
    }
    
    productCatalog[currentCategory].push(name);
    
    try {
        await saveProductCatalog();
        input.value = '';
        renderProductModels(currentCategory);
        showToast('型号添加成功', 'success');
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
        productCatalog[currentCategory].pop(); // Revert
    }
}

async function deleteProductModel(model) {
    if (!currentCategory) return;
    if (!confirm(`确定要删除型号 "${model}" 吗？`)) return;
    
    const idx = productCatalog[currentCategory].indexOf(model);
    if (idx > -1) {
        productCatalog[currentCategory].splice(idx, 1);
        try {
            await saveProductCatalog();
            renderProductModels(currentCategory);
            showToast('型号删除成功', 'success');
        } catch (e) {
            showToast('删除失败: ' + e.message, 'error');
            productCatalog[currentCategory].splice(idx, 0, model); // Revert
        }
    }
}

/** 导出型号库为 xlsx（A列分类，B列型号逗号连接） */
async function exportProductCatalogXlsx() {
    try {
        const url = API_BASE + '/kb/product_catalog/export';
        const res = await fetch(url, { credentials: 'include' });
        if (!res.ok) throw new Error(res.statusText || '导出失败');
        const blob = await res.blob();
        const disposition = res.headers.get('Content-Disposition');
        let name = `型号库导出_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '')}.xlsx`;
        if (disposition) {
            const m = disposition.match(/filename[*]?=(?:UTF-8'')?["']?([^"'\s]+)/i);
            if (m && m[1]) {
                name = m[1].replace(/^.*[/\\]/, '');
                // 去掉可能跟在文件名后的分号等符号，并清理引号
                name = name.replace(/["']/g, '').replace(/;+$/g, '');
            }
        }
        // 确保扩展名为 .xlsx（防止服务器或浏览器处理异常）
        if (!/\.xlsx$/i.test(name)) {
            name = name.replace(/\.+$/, '');
            name = `${name}.xlsx`;
        }
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = name;
        a.click();
        URL.revokeObjectURL(a.href);
        showToast('型号库已导出', 'success');
    } catch (e) {
        showToast('导出失败: ' + e.message, 'error');
    }
}

/** 导出型号清单为 xlsx（A列型号，B列分类） */
async function exportProductCatalogModelListXlsx() {
    try {
        const url = API_BASE + '/kb/product_catalog/export_models';
        const res = await fetch(url, { credentials: 'include' });
        if (!res.ok) throw new Error(res.statusText || '导出失败');
        const blob = await res.blob();
        const disposition = res.headers.get('Content-Disposition');
        let name = `型号清单_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.xlsx`;
        if (disposition) {
            const m = disposition.match(/filename[*]?=(?:UTF-8'')?["']?([^"'\s]+)/i);
            if (m && m[1]) {
                name = m[1].replace(/^.*[/\\]/, '');
                name = name.replace(/["']/g, '').replace(/;+$/g, '');
            }
        }
        if (!/\.xlsx$/i.test(name)) {
            name = name.replace(/\.+$/, '');
            name = `${name}.xlsx`;
        }
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = name;
        a.click();
        URL.revokeObjectURL(a.href);
        showToast('型号清单已导出');
    } catch (e) {
        showToast('导出失败: ' + (e && e.message ? e.message : String(e)));
    }
}

async function saveProductCatalog() {
    const preview = await api('/kb/product_catalog/preview', 'POST', { catalog: productCatalog });
    if (!preview || !preview.success) {
        throw new Error(preview?.message || '型号库变更预览失败');
    }
    const impact = preview.impact || {};
    if (impact.requires_confirmation) {
        const ok = await showDangerConfirmModal(
            '型号库清理确认',
            summarizeProductCatalogImpact(impact),
            '确认保存并清理'
        );
        if (!ok) throw new Error('已取消保存');
    }

    const res = await api('/kb/product_catalog', 'POST', {
        catalog: productCatalog,
        confirm_cleanup: !!impact.requires_confirmation
    });
    if (!res.success) throw new Error(res.message || 'Unknown error');
    productCatalogBaseline = JSON.parse(JSON.stringify(productCatalog));
    
    matrixAllModels = [];

    // Refresh Matrix View if active
    const matrixView = document.getElementById('matrixView');
    if (matrixView && !matrixView.classList.contains('d-none')) {
        loadMatrixData(matrixCurrentPage);
    }
}

async function saveProductCatalogFromManager() {
    const btn = document.getElementById('productCatalogCleanupBtn');
    const originalText = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '处理中...';
    }
    try {
        await saveProductCatalog();
        await loadProductManagerData();
        showToast('清理完成', 'success');
    } catch (e) {
        showToast('清理失败: ' + e.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = originalText || '执行清理';
        }
    }
}

async function setupTagsDropdown() {
    const input = document.getElementById('tagsInput');
    const btn = document.getElementById('tagsDropdownBtn');
    const dropdown = document.getElementById('tagsDropdown');
    
    if (!input || !btn || !dropdown) return;

    // Function to render dropdown
    function renderDropdown() {
        dropdown.innerHTML = '';
        
        // Get current tags from input
        const currentVal = input.value;
        const currentTags = currentVal.split(/[,，]/).map(t => t.trim()).filter(Boolean);
        
        // Filter out existing tags
        const availableTags = allTags.filter(tag => !currentTags.includes(tag));

        if (availableTags.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'dropdown-item';
            empty.style.color = '#999';
            empty.style.cursor = 'default';
            empty.textContent = '没有更多标签可选';
            dropdown.appendChild(empty);
            return;
        }

        availableTags.forEach(tag => {
            const item = document.createElement('div');
            item.className = 'dropdown-item';
            item.textContent = tag;
            item.onclick = (e) => {
                e.stopPropagation();
                const currentVal = input.value;
                // Check if we need a comma separator
                const sep = currentVal.trim().length > 0 && !currentVal.trim().endsWith(',') && !currentVal.trim().endsWith('，') ? ', ' : '';
                
                input.value = currentVal + sep + tag;
                
                // Trigger input event to update any listeners (optional)
                input.dispatchEvent(new Event('input'));
                
                // Close dropdown after selection
                dropdown.classList.remove('show');
                input.focus();
            };
            dropdown.appendChild(item);
        });
    }

    // Toggle dropdown
    btn.onclick = async (e) => {
        e.stopPropagation();
        e.preventDefault();
        
        const isVisible = dropdown.classList.contains('show');
        
        if (isVisible) {
            dropdown.classList.remove('show');
        } else {
            await fetchGlobalTags(); // Refresh tags from server
            renderDropdown();
            dropdown.classList.add('show');
        }
    };
    
    // Update dropdown when input changes (if open)
    input.addEventListener('input', () => {
        if (dropdown.classList.contains('show')) {
            renderDropdown();
        }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
        if (!dropdown.contains(e.target) && e.target !== btn) {
            dropdown.classList.remove('show');
        }
    });
}

function setupRowTagInput(input, container, existingTags) {
    // Create dropdown container if not exists (though renderLinkRow creates input inside a div, we can append dropdown there)
    // The container passed here should be the 'add-tag-row' div which we will make relative
    container.style.position = 'relative';
    
    const dropdown = document.createElement('div');
    dropdown.className = 'dropdown-menu';
    dropdown.style.minWidth = '150px';
    dropdown.style.maxHeight = '150px';
    container.appendChild(dropdown);
    
    function render() {
        dropdown.innerHTML = '';
        const currentVal = input.value;
        const inputTags = currentVal.split(/[,，]/).map(t => t.trim()).filter(Boolean);
        
        // Filter: not in existing tags AND not in current input
        const available = allTags.filter(t => !existingTags.includes(t) && !inputTags.includes(t));
        
        if (available.length === 0) {
            dropdown.classList.remove('show');
            return;
        }
        
        // Limit to 10 suggestions for inline input
        const suggestions = available.slice(0, 10);

        suggestions.forEach(tag => {
            const item = document.createElement('div');
            item.className = 'dropdown-item';
            item.textContent = tag;
            item.style.padding = '4px 8px';
            item.style.fontSize = '12px';
            
            item.onclick = (e) => {
                e.stopPropagation();
                // For row input, we might just replace the current partial input or append
                // Simple logic: append if comma exists, or replace if empty/partial
                // But row input is usually for ONE tag or comma separated.
                // Let's use same logic as main input: append
                
                const currentVal = input.value;
                const sep = currentVal.trim().length > 0 && !currentVal.trim().endsWith(',') && !currentVal.trim().endsWith('，') ? ', ' : '';
                
                input.value = currentVal + sep + tag;
                input.dispatchEvent(new Event('input'));
                dropdown.classList.remove('show');
                input.focus();
            };
            dropdown.appendChild(item);
        });
        dropdown.classList.add('show');
    }
    
    input.addEventListener('focus', async () => {
         if (allTags.length === 0) await fetchGlobalTags();
         render();
     });
     
     input.addEventListener('click', () => {
         if (document.activeElement === input) {
             render();
         }
     });

     input.addEventListener('input', () => {
         render();
     });
    
    // Close on click outside
    document.addEventListener('click', (e) => {
        if (!container.contains(e.target)) {
            dropdown.classList.remove('show');
        }
    });
}

// ---------------------------------------------------------
// Model Mapping Configuration
// ---------------------------------------------------------

let modelMappings = {};
let currentMappingCategory = null; // For Model Selector
let allUniqueModels = [];

async function openModelMappingModal() {
    try {
        // 1. Load Mappings
        const res = await api('/model_mappings');
        modelMappings = (res && typeof res === 'object' && !Array.isArray(res)) ? res : {};
        
        // 2. Load Product Catalog to get all available models
        if (Object.keys(productCatalog).length === 0) {
            const catalogRes = await api('/kb/product_catalog');
            if (catalogRes) productCatalog = catalogRes;
        }
        
        // Flatten product catalog to get all unique models
        const modelSet = new Set();
        Object.values(productCatalog).forEach(models => {
            if (Array.isArray(models)) {
                models.forEach(m => modelSet.add(m));
            }
        });
        allUniqueModels = Array.from(modelSet).sort();

        const searchEl = document.getElementById('modelMappingSearch');
        if (searchEl) searchEl.value = '';
        renderModelMappingTable();
        document.getElementById('modelMappingModal').style.display = 'block';
    } catch (e) {
        showToast('加载配置失败: ' + e.message, 'error');
    }
}

function closeModelMappingModal() {
    document.getElementById('modelMappingModal').style.display = 'none';
}

function renderModelMappingTable() {
    const grid = document.getElementById('modelMappingGrid');
    const tbody = document.getElementById('modelMappingTableBody');
    
    const query = (document.getElementById('modelMappingSearch')?.value || '').trim().toLowerCase();
    
    if (grid) grid.innerHTML = '';
    if (tbody) tbody.innerHTML = '';
    
    // Sort categories alphabetically or keep order? 
    // Objects are unordered, but we can sort keys.
    if (!modelMappings || typeof modelMappings !== 'object' || Array.isArray(modelMappings)) {
        modelMappings = {};
    }
    const categories = Object.keys(modelMappings).sort();
    if (categories.length === 0) {
        if (grid) {
            grid.innerHTML = `
                <div style="grid-column: 1 / -1; padding: 40px 16px; text-align: center; color: #777;">
                    暂无映射数据，请点击左上角“新增映射分类”
                </div>
            `;
        } else if (tbody) {
            tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; color:#777; padding: 24px;">暂无映射数据</td></tr>`;
        }
        return;
    }
    
    const matchesQuery = (category, models) => {
        if (!query) return true;
        if (String(category).toLowerCase().includes(query)) return true;
        const list = Array.isArray(models) ? models : [];
        return list.some(m => String(m).toLowerCase().includes(query));
    };
    
    categories.forEach(category => {
        const models = Array.isArray(modelMappings[category]) ? modelMappings[category] : [];
        if (!matchesQuery(category, models)) return;
        
        if (grid) {
            const card = document.createElement('div');
            card.className = 'mm-card';
            
            const header = document.createElement('div');
            header.className = 'mm-card-header';
            
            const nameInput = document.createElement('input');
            nameInput.type = 'text';
            nameInput.className = 'mm-category-input';
            nameInput.value = category;
            nameInput.onchange = (e) => renameMappingCategory(category, e.target.value);
            
            const count = document.createElement('span');
            count.className = 'mm-count-badge';
            count.innerText = String(models.length);
            
            const delBtn = document.createElement('button');
            delBtn.className = 'mm-card-delete';
            delBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
            delBtn.onclick = () => deleteMappingCategory(category);
            delBtn.title = '删除此分类映射';
            
            header.appendChild(nameInput);
            header.appendChild(count);
            header.appendChild(delBtn);
            
            const modelsDiv = document.createElement('div');
            modelsDiv.className = 'mm-models-container';
            
            models.forEach(model => {
                const chip = document.createElement('span');
                chip.className = 'mm-model-chip';
                chip.innerText = model;
                
                const x = document.createElement('i');
                x.className = 'fas fa-times mm-model-delete';
                x.title = '移除型号';
                x.onclick = () => removeModelFromMapping(category, model);
                
                chip.appendChild(x);
                modelsDiv.appendChild(chip);
            });
            
            const footer = document.createElement('div');
            footer.className = 'mm-card-footer';
            
            const addBtn = document.createElement('button');
            addBtn.className = 'mm-add-model-btn';
            addBtn.innerHTML = '<i class="fas fa-plus"></i> 添加机型';
            addBtn.onclick = () => openModelSelector(category);
            addBtn.title = '添加/管理机型';
            
            footer.appendChild(addBtn);
            
            card.appendChild(header);
            card.appendChild(modelsDiv);
            card.appendChild(footer);
            grid.appendChild(card);
            return;
        }
        
        if (tbody) {
            const tr = document.createElement('tr');
            
            const tdName = document.createElement('td');
            const nameInput = document.createElement('input');
            nameInput.type = 'text';
            nameInput.className = 'pm-input';
            nameInput.value = category;
            nameInput.style.width = '100%';
            nameInput.onchange = (e) => renameMappingCategory(category, e.target.value);
            tdName.appendChild(nameInput);
            
            const tdModels = document.createElement('td');
            const modelsDiv = document.createElement('div');
            modelsDiv.className = 'mm-models-container';
            
            models.forEach(model => {
                const chip = document.createElement('span');
                chip.className = 'mm-model-chip';
                chip.innerHTML = `
                    ${model}
                    <i class="fas fa-times mm-model-delete" onclick="removeModelFromMapping('${category}', '${model}')" title="移除型号"></i>
                `;
                modelsDiv.appendChild(chip);
            });
            
            const addBtn = document.createElement('button');
            addBtn.className = 'mm-add-model-btn';
            addBtn.innerHTML = '<i class="fas fa-plus"></i>';
            addBtn.onclick = () => openModelSelector(category);
            addBtn.title = '添加/管理机型';
            modelsDiv.appendChild(addBtn);
            
            tdModels.appendChild(modelsDiv);
            
            const tdActions = document.createElement('td');
            const delBtn = document.createElement('button');
            delBtn.className = 'icon-btn delete-btn';
            delBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
            delBtn.onclick = () => deleteMappingCategory(category);
            delBtn.title = '删除此分类映射';
            tdActions.appendChild(delBtn);
            
            tr.appendChild(tdName);
            tr.appendChild(tdModels);
            tr.appendChild(tdActions);
            tbody.appendChild(tr);
        }
    });
}

function addMappingCategory() {
    let newName = '新分类';
    let counter = 1;
    while (modelMappings[newName]) {
        newName = `新分类 ${counter++}`;
    }
    modelMappings[newName] = [];
    renderModelMappingTable();
}

function renameMappingCategory(oldName, newName) {
    newName = newName.trim();
    if (!newName || newName === oldName) {
        renderModelMappingTable(); // Reset input if invalid
        return;
    }
    
    if (modelMappings[newName]) {
        showToast('分类名称已存在', 'warning');
        renderModelMappingTable();
        return;
    }
    
    // Create new object with new key
    const newMappings = {};
    Object.keys(modelMappings).forEach(key => {
        if (key === oldName) {
            newMappings[newName] = modelMappings[oldName];
        } else {
            newMappings[key] = modelMappings[key];
        }
    });
    modelMappings = newMappings;
    renderModelMappingTable();
}

function deleteMappingCategory(category) {
    if (!confirm(`确定要删除分类映射 "${category}" 吗？`)) return;
    delete modelMappings[category];
    renderModelMappingTable();
}

function removeModelFromMapping(category, model) {
    if (modelMappings[category]) {
        modelMappings[category] = modelMappings[category].filter(m => m !== model);
        renderModelMappingTable();
    }
}

// ---------------------------------------------------------
// Model Selector Logic
// ---------------------------------------------------------

let modelSelectorTempSelected = new Set();

function compactModelKey(v) {
    return String(v || '').trim().replace(/\s+/g, '').toLowerCase();
}

function buildCatalogModelIndex() {
    const index = new Map();
    Object.keys(productCatalog || {}).forEach(cat => {
        const models = productCatalog[cat];
        if (!Array.isArray(models)) return;
        models.forEach(m => {
            if (!m) return;
            const key = compactModelKey(m);
            if (!key) return;
            if (!index.has(key)) index.set(key, String(m));
        });
    });
    return index;
}

function canonicalizeModelName(name, catalogIndex) {
    const raw = String(name || '').trim();
    if (!raw) return '';
    const key = compactModelKey(raw);
    return (catalogIndex && catalogIndex.get(key)) || raw;
}

function enableWheelScrollInElement(el) {
    if (!el) return;
    if (el.dataset.wheelScrollEnabled === '1') return;
    el.dataset.wheelScrollEnabled = '1';
    
    let pendingDelta = 0;
    let rafId = 0;
    const flush = () => {
        rafId = 0;
        if (pendingDelta === 0) return;
        el.scrollTop += pendingDelta;
        pendingDelta = 0;
    };
    
    el.addEventListener('wheel', (e) => {
        const canScroll = el.scrollHeight > el.clientHeight;
        if (!canScroll) return;
        
        let deltaY = e.deltaY || 0;
        let deltaX = e.deltaX || 0;
        let delta = Math.abs(deltaY) >= Math.abs(deltaX) ? deltaY : deltaX;
        if (e.deltaMode === 1) delta *= 16;
        if (e.deltaMode === 2) delta *= el.clientHeight;
        if (!delta) return;

        const atTop = el.scrollTop <= 0;
        const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
        
        if ((delta < 0 && atTop) || (delta > 0 && atBottom)) {
            return;
        }
        
        pendingDelta += delta;
        if (!rafId) rafId = requestAnimationFrame(flush);
        e.preventDefault();
        e.stopPropagation();
    }, { passive: false });
}

function enableDragScrollInElement(el) {
    if (!el) return;
    if (el.dataset.dragScrollEnabled === '1') return;
    el.dataset.dragScrollEnabled = '1';
    
    let isDown = false;
    let isDragging = false;
    let startY = 0;
    let startScrollTop = 0;
    let activePointerId = null;
    let suppressClickUntil = 0;
    
    el.addEventListener('pointerdown', (e) => {
        if (e.target && e.target.closest && e.target.closest('input, label, button, a, textarea, select, option')) return;
        if (e.button !== 0) return;
        isDown = true;
        isDragging = false;
        startY = e.clientY;
        startScrollTop = el.scrollTop;
        activePointerId = e.pointerId;
        el.setPointerCapture?.(e.pointerId);
    });
    
    el.addEventListener('pointermove', (e) => {
        if (!isDown) return;
        if (activePointerId !== null && e.pointerId !== activePointerId) return;
        const dy = e.clientY - startY;
        if (!isDragging && Math.abs(dy) > 6) {
            isDragging = true;
            suppressClickUntil = performance.now() + 250;
        }
        if (!isDragging) return;
        el.scrollTop = startScrollTop - dy;
        e.preventDefault();
    }, { passive: false });
    
    const end = (e) => {
        if (e && activePointerId !== null && e.pointerId !== activePointerId) return;
        isDown = false;
        activePointerId = null;
        setTimeout(() => { isDragging = false; }, 0);
    };
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
    
    el.addEventListener('click', (e) => {
        if (performance.now() >= suppressClickUntil) return;
        e.preventDefault();
        e.stopPropagation();
    }, true);
}

function openModelSelector(category) {
    currentMappingCategory = category;
    const modal = document.getElementById('modelSelectorModal');
    if (modal) modal.style.display = 'block';
    
    // Reset search
    const searchInput = document.getElementById('modelSelectorSearch');
    if (searchInput) {
        searchInput.value = '';
        searchInput.focus();
    }

    const catalogIndex = buildCatalogModelIndex();
    const rawSelected = modelMappings[currentMappingCategory] || [];
    modelSelectorTempSelected = new Set(
        (Array.isArray(rawSelected) ? rawSelected : [])
            .map(m => canonicalizeModelName(m, catalogIndex))
            .filter(Boolean)
    );
    renderModelSelectorSelected();
    
    renderModelSelectorList();
    
    enableWheelScrollInElement(document.getElementById('modelSelectorSelected'));
    enableWheelScrollInElement(document.getElementById('modelSelectorList'));
    enableDragScrollInElement(document.getElementById('modelSelectorList'));
}

function closeModelSelector() {
    document.getElementById('modelSelectorModal').style.display = 'none';
    currentMappingCategory = null;
    modelSelectorTempSelected = new Set();
}

function renderModelSelectorSelected() {
    const wrap = document.getElementById('modelSelectorSelected');
    if (!wrap) return;
    wrap.innerHTML = '';
    
    const header = document.createElement('div');
    header.className = 'mm-selected-header';
    
    const title = document.createElement('div');
    title.className = 'mm-selected-title';
    title.innerText = `已选 ${modelSelectorTempSelected.size}`;
    
    const clearBtn = document.createElement('button');
    clearBtn.className = 'mm-selected-clear';
    clearBtn.type = 'button';
    clearBtn.innerText = '清空';
    clearBtn.onclick = () => {
        modelSelectorTempSelected = new Set();
        renderModelSelectorSelected();
        const q = document.getElementById('modelSelectorSearch')?.value?.trim() || '';
        renderModelSelectorList(q);
    };
    
    header.appendChild(title);
    header.appendChild(clearBtn);
    wrap.appendChild(header);
    
    const list = document.createElement('div');
    list.className = 'mm-selected-chips';
    
    const selected = Array.from(modelSelectorTempSelected).sort((a, b) => String(a).localeCompare(String(b), 'zh'));
    selected.forEach(model => {
        const chip = document.createElement('span');
        chip.className = 'mm-selected-chip';
        chip.innerText = model;
        
        const x = document.createElement('i');
        x.className = 'fas fa-times mm-selected-remove';
        x.title = '移除';
        x.onclick = () => {
            modelSelectorTempSelected.delete(model);
            renderModelSelectorSelected();
            const q = document.getElementById('modelSelectorSearch')?.value?.trim() || '';
            renderModelSelectorList(q);
        };
        
        chip.appendChild(x);
        list.appendChild(chip);
    });
    
    wrap.appendChild(list);
}

function renderModelSelectorList(filter = '') {
    const list = document.getElementById('modelSelectorList');
    if (!list) return;
    list.innerHTML = '';

    const q = String(filter || '').trim().toLowerCase();
    const catalogIndex = buildCatalogModelIndex();
    const addSection = (title, models) => {
        const filtered = (models || []).filter(m => {
            if (!m) return false;
            if (!q) return true;
            return String(m).toLowerCase().includes(q);
        });
        if (filtered.length === 0) return;
        
        const section = document.createElement('div');
        section.className = 'mm-ms-section';
        
        const header = document.createElement('div');
        header.className = 'mm-ms-header';
        
        const hTitle = document.createElement('div');
        hTitle.className = 'mm-ms-title';
        hTitle.innerText = title;
        
        const hCount = document.createElement('div');
        hCount.className = 'mm-ms-count';
        hCount.innerText = String(filtered.length);
        
        header.appendChild(hTitle);
        header.appendChild(hCount);
        
        const grid = document.createElement('div');
        grid.className = 'mm-ms-grid';
        
        filtered.forEach(model => {
            const label = document.createElement('label');
            label.className = 'mm-ms-item';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = model;
            checkbox.checked = modelSelectorTempSelected.has(model);
            checkbox.onchange = (e) => {
                if (e.target.checked) {
                    modelSelectorTempSelected.add(model);
                } else {
                    modelSelectorTempSelected.delete(model);
                }
                renderModelSelectorSelected();
            };
            
            const span = document.createElement('span');
            span.textContent = model;
            
            label.appendChild(checkbox);
            label.appendChild(span);
            grid.appendChild(label);
        });
        
        section.appendChild(header);
        section.appendChild(grid);
        list.appendChild(section);
    };
    
    const modelToCategory = new Map();
    Object.keys(productCatalog || {}).forEach(cat => {
        const models = productCatalog[cat];
        if (!Array.isArray(models)) return;
        models.forEach(m => {
            if (!m) return;
            const canonical = canonicalizeModelName(m, catalogIndex);
            if (!canonical) return;
            if (!modelToCategory.has(canonical)) modelToCategory.set(canonical, cat);
        });
    });
    
    const mappingModelSet = new Set();
    Object.keys(productCatalog || {}).forEach(cat => {
        const models = productCatalog[cat];
        if (!Array.isArray(models)) return;
        models.forEach(m => {
            const canonical = canonicalizeModelName(m, catalogIndex);
            if (canonical) mappingModelSet.add(canonical);
        });
    });
    modelSelectorTempSelected.forEach(m => {
        const canonical = canonicalizeModelName(m, catalogIndex);
        if (canonical) mappingModelSet.add(canonical);
    });
    
    const grouped = {};
    Array.from(mappingModelSet).forEach(model => {
        const canonical = canonicalizeModelName(model, catalogIndex);
        const cat = modelToCategory.get(canonical) || '未归类';
        if (!grouped[cat]) grouped[cat] = [];
        grouped[cat].push(canonical);
    });
    
    const cats = Object.keys(grouped).sort((a, b) => {
        if (a === '未归类') return 1;
        if (b === '未归类') return -1;
        return a.localeCompare(b, 'zh');
    });
    
    cats.forEach(cat => {
        const models = Array.from(new Set(grouped[cat])).sort((a, b) => String(a).localeCompare(String(b), 'zh'));
        addSection(cat, models);
    });
}

function filterModelSelector() {
    const input = document.getElementById('modelSelectorSearch');
    renderModelSelectorList(input.value.trim());
    renderModelSelectorSelected();
}

function confirmModelSelection() {
    if (!currentMappingCategory) return;

    const catalogIndex = buildCatalogModelIndex();
    const normalized = Array.from(modelSelectorTempSelected)
        .map(m => canonicalizeModelName(m, catalogIndex))
        .filter(Boolean);
    modelMappings[currentMappingCategory] = Array.from(new Set(normalized));
    closeModelSelector();
    renderModelMappingTable();
}

// 导出当前机型分类映射配置为 Excel（xlsx）
function exportModelMappingsJson() {
    try {
        const items =
            modelMappings && typeof modelMappings === 'object' && !Array.isArray(modelMappings)
                ? modelMappings
                : {};

        // 用后端生成 xlsx：确保导出包含弹窗内当前未保存的改动
        fetch(API_BASE + '/model_mappings/export_excel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(items),
        })
            .then(async (res) => {
                if (!res.ok) {
                    const extra =
                        res.status === 405
                            ? '（疑似：后端未重启或接口方法不匹配。请重启 KnowledgeBaseTool 服务后再试）'
                            : '';
                    throw new Error(`HTTP ${res.status} ${res.statusText || ''}${extra}`.trim());
                }
                const blob = await res.blob();
                const disposition = res.headers.get('Content-Disposition');
                let name = `model-mappings_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.xlsx`;
                if (disposition) {
                    const m = disposition.match(/filename[*]?=(?:UTF-8'')?["']?([^"'\s]+)/i);
                    if (m && m[1]) name = m[1].replace(/^.*[/\\]/, '').replace(/["']/g, '').trim();
                }
                if (!/\.xlsx$/i.test(name)) name = name.replace(/\.+$/, '') + '.xlsx';
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = name;
                a.click();
                URL.revokeObjectURL(a.href);
                showToast('机型分类映射已导出（xlsx）');
            })
            .catch((e) => {
                showToast('导出失败: ' + (e && e.message ? e.message : String(e)));
            });
    } catch (e) {
        showToast('导出失败: ' + (e && e.message ? e.message : String(e)));
    }
}

async function saveModelMappings() {
    try {
        const res = await api('/model_mappings', 'POST', modelMappings);
        if (res.error) {
            showToast('保存失败: ' + res.error, 'error');
        } else {
            showToast('配置保存成功', 'success');
            if (typeof matrixMappingCategoryFilter === 'string' && matrixMappingCategoryFilter) {
                if (!Object.prototype.hasOwnProperty.call(modelMappings || {}, matrixMappingCategoryFilter)) {
                    matrixMappingCategoryFilter = '';
                }
            }
            if (currentTab === 'matrixView' && typeof loadMatrixData === 'function') {
                loadMatrixData(1);
            }
        }
    } catch (e) {
        showToast('保存异常: ' + e.message, 'error');
    }
}

function openModelMappingImportModal() {
    document.getElementById('modelMappingImportText').value = '';
    document.getElementById('modelMappingImportModal').style.display = 'block';
}

function closeModelMappingImportModal() {
    document.getElementById('modelMappingImportModal').style.display = 'none';
}

function importModelMappings() {
    const text = document.getElementById('modelMappingImportText').value;
    if (!text.trim()) {
        showToast('请输入内容', 'warning');
        return;
    }

    const catalogIndex = buildCatalogModelIndex();
    const lines = text.split(/\r?\n/);
    let successCount = 0;
    let skipCount = 0;

    lines.forEach(line => {
        line = line.trim();
        if (!line) return;

        // Split by first colon or tab
        // Use a regex to find the first occurrence of : or \t
        // But simply split by regex might split on multiple colons.
        // Let's find index.
        let separatorIndex = -1;
        let separatorType = '';
        
        const colonIndex = line.indexOf(':');
        const tabIndex = line.indexOf('\t');
        const chineseColonIndex = line.indexOf('：');

        // Find the earliest valid separator
        const indices = [colonIndex, tabIndex, chineseColonIndex].filter(i => i !== -1);
        if (indices.length === 0) {
            skipCount++;
            return;
        }
        separatorIndex = Math.min(...indices);

        const category = line.substring(0, separatorIndex).trim();
        const modelsStr = line.substring(separatorIndex + 1).trim();

        if (!category) {
            skipCount++;
            return;
        }

        const models = modelsStr
            .split(/[,，、|\t]/)
            .map(m => canonicalizeModelName(m, catalogIndex))
            .map(m => String(m || '').trim())
            .filter(Boolean);
        
        if (models.length > 0) {
            // Merge logic: if category exists, add unique models
            if (!modelMappings[category]) {
                modelMappings[category] = [];
            }
            
            const existing = new Set(
                (Array.isArray(modelMappings[category]) ? modelMappings[category] : [])
                    .map(m => canonicalizeModelName(m, catalogIndex))
                    .filter(Boolean)
            );
            models.forEach(m => existing.add(m));
            modelMappings[category] = Array.from(existing);
            successCount++;
        } else {
            // If just category provided, create it if not exists
            if (!modelMappings[category]) {
                modelMappings[category] = [];
                successCount++;
            }
        }
    });

    renderModelMappingTable();
    closeModelMappingImportModal();
    showToast(`导入完成: 成功 ${successCount} 条，跳过 ${skipCount} 条 (格式错误)`, 'success');
}

function enableHorizontalDragScroll(container) {
    if (!container || (container.dataset && container.dataset.dragScrollBound)) return;
    if (container.dataset) container.dataset.dragScrollBound = '1';

    let isDown = false;
    let startX = 0;
    let startLeft = 0;
    let moved = 0;
    let suppressClick = false;

    const onDown = (e) => {
        if (e.button !== 0) return;
        const t = e.target;
        if (t && t.closest && t.closest('textarea, input, select, button, a, label, summary, details, .col-resizer')) return;
        isDown = true;
        moved = 0;
        suppressClick = false;
        startX = e.clientX;
        startLeft = container.scrollLeft;
        container.style.cursor = 'grabbing';
        container.style.userSelect = 'none';
    };

    const onMove = (e) => {
        if (!isDown) return;
        const dx = e.clientX - startX;
        moved = Math.max(moved, Math.abs(dx));
        if (moved > 3) suppressClick = true;
        container.scrollLeft = startLeft - dx;
        e.preventDefault();
    };

    const end = () => {
        if (!isDown) return;
        isDown = false;
        container.style.cursor = '';
        container.style.userSelect = '';
        if (suppressClick) setTimeout(() => { suppressClick = false; }, 0);
    };

    container.addEventListener('mousedown', onDown);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', end);
    container.addEventListener('mouseleave', end);
    container.addEventListener('click', (e) => {
        if (!suppressClick) return;
        e.preventDefault();
        e.stopPropagation();
    }, true);
}

function enableAllTableDragScroll() {
    document.querySelectorAll('.table-container').forEach(el => enableHorizontalDragScroll(el));
}

function enableTableColumnResize(table) {
    if (!table || (table.dataset && table.dataset.colResizeBound)) return;
    if (table.dataset) table.dataset.colResizeBound = '1';

    const head = table.tHead;
    if (!head || !head.rows || head.rows.length === 0) return;
    const headerRow = head.rows[head.rows.length - 1];
    const ths = Array.from(headerRow.cells || []).filter(el => el && el.tagName === 'TH');
    if (ths.length <= 1) return;

    const colgroup = table.querySelector('colgroup');
    const cols = colgroup ? Array.from(colgroup.querySelectorAll('col')) : [];

    ths.forEach((th, idx) => {
        if (!th || (th.dataset && th.dataset.resizerReady)) return;
        if (th.dataset) th.dataset.resizerReady = '1';
        if (idx === ths.length - 1) return;
        const resizer = document.createElement('div');
        resizer.className = 'col-resizer';
        resizer.addEventListener('mousedown', (e) => {
            e.preventDefault();
            e.stopPropagation();

            const startX = e.clientX;
            const startWidth = th.getBoundingClientRect().width;
            const minWidth = 60;
            const maxWidth = 1200;

            document.documentElement.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';

            const onMove = (ev) => {
                const dx = ev.clientX - startX;
                const w = Math.max(minWidth, Math.min(maxWidth, startWidth + dx));
                if (cols && cols[idx]) cols[idx].style.width = `${w}px`;
                th.style.width = `${w}px`;
            };

            const onUp = () => {
                window.removeEventListener('mousemove', onMove);
                window.removeEventListener('mouseup', onUp);
                document.documentElement.style.cursor = '';
                document.body.style.userSelect = '';
            };

            window.addEventListener('mousemove', onMove);
            window.addEventListener('mouseup', onUp);
        });
        th.appendChild(resizer);
    });
}

function enableAllTableColumnResize() {
    document.querySelectorAll('table.kb-table').forEach(t => enableTableColumnResize(t));
}

// ==========================================
// Initialization
// ==========================================
window.addEventListener('DOMContentLoaded', async () => {
  // Check Login
  try {
      const status = await api('/status');
      if (status.logged_in) {
        currentUser = status.username;
        const userEl = document.getElementById('currentUser');
        if (userEl) userEl.textContent = currentUser;
        showLogin(false);
        
        // Initial load (main app page)
        switchTab('kbView');
        await loadKBProductCategoryChips();
      } else {
        showLogin(true);
      }
  } catch {
      showLogin(true);
  }

  // Bind Login Events
  const loginBtn = document.getElementById('loginBtn');
  if (loginBtn) loginBtn.addEventListener('click', handleLogin);
  
  const pwdInput = document.getElementById('password');
  if (pwdInput) {
      pwdInput.addEventListener('keypress', (e) => {
          if (e.key === 'Enter') handleLogin();
      });
  }
  
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) logoutBtn.addEventListener('click', logout);

  const useCacheCb = document.getElementById('useCacheCb');
  if (useCacheCb) {
      updateEvaluateAllButtonLabel();
      useCacheCb.addEventListener('change', updateEvaluateAllButtonLabel);
  }

  initWorkbenchSidebarState();

  window.addEventListener('resize', scheduleWorkbenchSidebarHeightUpdate);
  window.addEventListener('resize', applyWorkbenchLayoutHotfix);

  enableAllTableDragScroll();
  enableAllTableColumnResize();
  scheduleWorkbenchSidebarHeightUpdate();
  applyWorkbenchLayoutHotfix();

  // Tab buttons already call switchTab inline in the HTML.

  // 初始化修改记录表头排序（问题编号 / 问题）
  initModSortHeaders();

  // ==========================================
  // 为搜索输入框添加防抖 - 性能优化
  // ==========================================
  const searchInputIds = [
    'idSearch',
    'productNameSearch', 
    'questionSearch',
    'similarQuestionSearch',
    'answerSearch',
    'urlSearch',
    'matrixSearchId',
    'matrixSearchQuestion',
    'matrixSearchAnswer',
	    'scoreSearchId',
	    'scoreSearchProduct',
	    'scoreSearchQuestion',
	    'scoreSearchMinTotal',
	    'scoreSearchMaxTotal',
	    // Mod search
    'modSearchId',
    'modSearchProduct',
    'modSearchQuestion',
    'modSearchAnswer'
  ];

  searchInputIds.forEach(inputId => {
    const input = document.getElementById(inputId);
    if (input) {
      // 移除可能存在的旧事件监听
      const newInput = input.cloneNode(true);
      input.parentNode.replaceChild(newInput, input);
      
      // 添加防抖的input事件
      newInput.addEventListener('input', debounce(() => {
        // 根据不同的输入框触发不同的搜索
        if (inputId.startsWith('matrix')) {
          // 矩阵搜索
          if (typeof loadMatrixData === 'function') {
            loadMatrixData();
          }
        } else if (inputId.startsWith('score')) {
          // 评分搜索
          if (typeof renderScoringTable === 'function') {
            scoringPage = 1;
            renderScoringTable(true);
          }
        } else if (inputId.startsWith('mod')) {
          // 修改记录搜索
          if (typeof loadModifications === 'function') {
            loadModifications(1);
          }
        } else {
          // 知识库搜索
          searchKBDebounced();
        }
      }, 500));
      
      // Enter键立即搜索（不防抖）
      newInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
          if (inputId.startsWith('matrix')) {
            if (typeof loadMatrixData === 'function') loadMatrixData();
          } else if (inputId.startsWith('score')) {
            if (typeof renderScoringTable === 'function') {
              scoringPage = 1;
              renderScoringTable(true);
            }
          } else if (inputId.startsWith('mod')) {
            if (typeof loadModifications === 'function') loadModifications(1);
          } else {
            searchKB();
          }
        }
      });
    }
  });

  console.log('✅ 搜索防抖已启用 (500ms延迟)');

  // ==========================================
  // 滚动性能优化 - 轻量版（移除过度优化）
  // ==========================================
  
  // 只保留最基础的优化
  try {
    // 1. 使用Passive事件监听器（不阻塞滚动）
    const tables = document.querySelectorAll('.table-container, #kbTableContainer, #matrixTableContainer');
    tables.forEach(table => {
      if (table) {
        table.addEventListener('scroll', () => {
          // 滚动处理（如果需要）
        }, { passive: true });
      }
    });
    
    console.log('✅ 滚动优化已启用（轻量版）');
  } catch (e) {
    console.warn('滚动优化失败:', e);
  }

  // Bind Link View Events
  setupTagsDropdown(); // Initialize tags dropdown
  setupKBTagDropdown(); // Initialize KB tag multi-select
  
  const addBtn = document.getElementById('addBtn');
  if (addBtn) addBtn.addEventListener('click', async () => {
    const urlEl = document.getElementById('urlInput');
    const tagsEl = document.getElementById('tagsInput');
    const url = urlEl ? urlEl.value : '';
    const tags = tagsEl ? tagsEl.value.split(',').map(s => s.trim()).filter(Boolean) : [];
    const added = await addSingleWithDuplicateCheck(url, tags);
    if (added) {
      if (urlEl) urlEl.value = '';
      if (tagsEl) tagsEl.value = '';
      closeLinkImportModal();
    }
  });

  const bulkBtn = document.getElementById('bulkBtn');
  if (bulkBtn) bulkBtn.addEventListener('click', async () => {
    const bulkEl = document.getElementById('bulkInput');
    const tagsEl = document.getElementById('tagsInput');
    const lines = parseUrlsFromText(bulkEl ? bulkEl.value : '');
    const tags = tagsEl ? tagsEl.value.split(',').map(s => s.trim()).filter(Boolean) : [];
    const added = await prepareBulkAdd(lines, tags);
    if (added) {
      if (bulkEl) bulkEl.value = '';
      closeLinkImportModal();
    }
  });

  const openLinkImportModalBtn = document.getElementById('openLinkImportModalBtn');
  if (openLinkImportModalBtn) openLinkImportModalBtn.addEventListener('click', openLinkImportModal);

  const linkTagSelectorBtn = document.getElementById('linkTagSelectorBtn');
  if (linkTagSelectorBtn) linkTagSelectorBtn.addEventListener('click', (e) => {
    e.preventDefault();
    const wrap = document.getElementById('linkTagSelectorWrap');
    const isOpen = !!wrap && wrap.classList.contains('open');
    setLinkTagDropdownOpen(!isOpen);
  });

  document.addEventListener('click', (e) => {
    const wrap = document.getElementById('linkTagSelectorWrap');
    if (!wrap) return;
    if (wrap.contains(e.target)) return;
    setLinkTagDropdownOpen(false);
  });

  const openImportFileLinkBtn = document.getElementById('openImportFileLinkBtn');
  if (openImportFileLinkBtn) openImportFileLinkBtn.addEventListener('click', () => {
    const importFileLink = document.getElementById('importFileLink');
    if (importFileLink) importFileLink.click();
  });

  const linkImportCloseBtn = document.querySelector('#linkImportModal .link-import-close-btn');
  if (linkImportCloseBtn) linkImportCloseBtn.addEventListener('click', closeLinkImportModal);

  const importFileLink = document.getElementById('importFileLink');
  if (importFileLink) importFileLink.addEventListener('change', async (e) => {
    const file = e?.target?.files?.[0];
    if (!file) return;
    let text = '';
    try {
      text = typeof file.text === 'function' ? await file.text() : '';
    } catch {}
    if (!text) {
      showLinkAddError('导入失败：无法读取文件内容');
      return;
    }
    let json = null;
    try {
      json = JSON.parse(text);
    } catch {
      showLinkAddError('导入失败：JSON格式不正确');
      return;
    }
    const urls = extractUrlsFromJson(json);
    const tagsEl = document.getElementById('tagsInput');
    const tags = tagsEl ? tagsEl.value.split(',').map(s => s.trim()).filter(Boolean) : [];
    const added = await prepareBulkAdd(urls, tags);
    if (added) {
      importFileLink.value = '';
      closeLinkImportModal();
    }
  });
  
  const clearFilterBtn = document.getElementById('clearFilter');
  if (clearFilterBtn) clearFilterBtn.addEventListener('click', () => {
    activeFilterTags = [];
    linkShowDuplicateUrlsOnly = false;
    const statusFilter = document.getElementById('linkFilterStatus');
    if (statusFilter) statusFilter.value = 'all';
    const typeFilter = document.getElementById('linkFilterType');
    if (typeFilter) typeFilter.value = 'all';
    const kbidInput = document.getElementById('linkSearchKBID');
    if (kbidInput) kbidInput.value = '';
    const urlInput = document.getElementById('linkSearchURL');
    if (urlInput) urlInput.value = '';
    setLinkTagDropdownOpen(false);
    linkCurrentPage = 1;
    renderLinkTable();
  });

  const filterDupUrlBtn = document.getElementById('filterDupUrlBtn');
  if (filterDupUrlBtn) filterDupUrlBtn.addEventListener('click', openDuplicateUrlModal);

  const duplicateUrlDedupBtn = document.getElementById('duplicateUrlDedupBtn');
  if (duplicateUrlDedupBtn) duplicateUrlDedupBtn.addEventListener('click', deduplicateUrls);

  const bulkDuplicateCancelBtn = document.getElementById('bulkDuplicateCancelBtn');
  if (bulkDuplicateCancelBtn) bulkDuplicateCancelBtn.addEventListener('click', closeBulkDuplicateModal);

  const bulkDuplicateProceedBtn = document.getElementById('bulkDuplicateProceedBtn');
  if (bulkDuplicateProceedBtn) bulkDuplicateProceedBtn.addEventListener('click', async () => {
    const urls = bulkPendingUrls || [];
    const tags = bulkPendingTags || [];
    closeBulkDuplicateModal();
    if (urls.length === 0) {
      showLinkAddError('没有可添加的新URL');
      return;
    }
    try {
      await addLinksBatch(urls, tags);
      const bulkEl = document.getElementById('bulkInput');
      if (bulkEl) bulkEl.value = '';
      const importEl = document.getElementById('importFileLink');
      if (importEl) importEl.value = '';
      closeLinkImportModal();
    } catch (e) {
      showLinkAddError((e && e.message) ? e.message : '批量添加失败');
    }
  });

  const showLastManualUrlBtn = document.getElementById('showLastManualUrlBtn');
  if (showLastManualUrlBtn) showLastManualUrlBtn.addEventListener('click', showLatestManualUrl);

  const exportDataBtn = document.getElementById('exportData');
  if (exportDataBtn) exportDataBtn.addEventListener('click', exportLinkData);

  const selectAllLinks = document.getElementById('selectAll');
  if (selectAllLinks) selectAllLinks.addEventListener('change', toggleSelectAllLinks);
  
  const batchDeleteBtn = document.getElementById('batchDeleteBtn');
  if (batchDeleteBtn) batchDeleteBtn.addEventListener('click', batchDeleteLinks);
  
  const batchCopyBtn = document.getElementById('batchCopyBtn');
  if (batchCopyBtn) batchCopyBtn.addEventListener('click', batchCopyPreviews);
  
  const kbPreviewSelectedBtn = document.getElementById('kbPreviewSelectedBtn');
  if (kbPreviewSelectedBtn) kbPreviewSelectedBtn.addEventListener('click', toggleKBPreviewSelectedOnly);
  updateKBPreviewSelectedButton();

  // KB filters support Enter to search.
  ['idSearch', 'productNameSearch', 'questionSearch', 'similarQuestionSearch', 'answerSearch', 'urlSearch'].forEach((inputId) => {
    const el = document.getElementById(inputId);
    if (!el) return;
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        searchKB();
      }
    });
  });

  // Modifications filters support Enter to search.
  ['modSearchId', 'modSearchProduct', 'modSearchQuestion', 'modSearchAnswer'].forEach((inputId) => {
    const el = document.getElementById(inputId);
    if (!el) return;
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        loadModifications(1);
      }
    });
  });
  const draftFilterEl = document.getElementById('kbDraftStatusFilter');
  if (draftFilterEl) {
    draftFilterEl.addEventListener('change', () => loadKBTable(1));
  }
  
  // Close Modals on outside click
  window.onclick = (e) => {
      if (e.target && e.target.id === 'dangerConfirmModal') {
          closeDangerConfirmModal(false);
          return;
      }
      if (e.target && e.target.id === 'kbEditCloseConfirmModal') {
          closeKbEditUnsavedCloseModal('cancel');
          return;
      }
      if (e.target.classList.contains('modal')) {
          if (e.target.id === 'kbEditModal') {
              closeKBEditModal();
              return;
          }
      if (e.target.id === 'linkImportModal') {
          closeLinkImportModal();
          return;
      }
          if (e.target.id === 'bulkDuplicateModal') closeBulkDuplicateModal();
          else e.target.style.display = 'none';
      }
  };
  
  // Close buttons
  document.querySelectorAll('.close-modal, .close-modal-btn').forEach(btn => {
      btn.onclick = () => {
          const modal = btn.closest('.modal');
          if (!modal) return;
          if (modal.id === 'kbEditModal') {
              closeKBEditModal();
              return;
          }
          if (modal.id === 'bulkDuplicateModal') closeBulkDuplicateModal();
          else modal.style.display = 'none';
      };
  });
  window.addEventListener('beforeunload', (e) => {
      if (typeof isScoringInProgress === 'function' && (isScoringInProgress() || isScoringPaused())) {
          e.preventDefault();
          e.returnValue = '';
          return;
      }
      const modal = document.getElementById('kbEditModal');
      if (!modal || modal.style.display === 'none') return;
      if (!__kbEditHasUnsavedChanges()) return;
      e.preventDefault();
      e.returnValue = '';
  });
});

// Markdown Editor (Answer) - ToastUI Editor + textarea compatibility
let __kbAnswerTui = null;
let __kbAnswerTuiSyncTimer = null;

function __kbAnswerGetTextarea() {
    return document.getElementById('answerEditor');
}

function __kbAnswerGetTuiWrap() {
    return document.getElementById('answerTuiEditorWrap');
}

function __kbAnswerGetTuiEl() {
    return document.getElementById('answerTuiEditor');
}

function __kbAnswerRefreshLayout() {
    const wrap = __kbAnswerGetTuiWrap();
    const el = __kbAnswerGetTuiEl();
    if (wrap) {
        wrap.style.minHeight = '0';
        wrap.style.height = '';
    }
    if (el) {
        el.style.minHeight = '0';
        el.style.height = '';
    }
    if (__kbAnswerTui && typeof __kbAnswerTui.setHeight === 'function') {
        try { __kbAnswerTui.setHeight('100%'); } catch {}
    }
}

function __kbAnswerScheduleLayoutRefresh() {
    __kbAnswerRefreshLayout();
    try { requestAnimationFrame(__kbAnswerRefreshLayout); } catch {}
    try { requestAnimationFrame(() => requestAnimationFrame(__kbAnswerRefreshLayout)); } catch {}
    setTimeout(__kbAnswerRefreshLayout, 80);
}

function __kbAnswerEnsureTui() {
    if (__kbAnswerTui) return __kbAnswerTui;
    const el = __kbAnswerGetTuiEl();
    if (!el) return null;
    const EditorCtor = (window.toastui && window.toastui.Editor) ? window.toastui.Editor : null;
    if (!EditorCtor) return null;
    const ta = __kbAnswerGetTextarea();
    const initial = ta ? String(ta.value || '') : '';
    __kbAnswerTui = new EditorCtor({
        el,
        height: '360px',
        initialEditType: 'markdown',
        previewStyle: 'vertical',
        initialValue: initial,
        usageStatistics: false
    });
    __kbAnswerTui.on('change', () => {
        if (__kbAnswerTuiSyncTimer) clearTimeout(__kbAnswerTuiSyncTimer);
        __kbAnswerTuiSyncTimer = setTimeout(() => {
            __kbAnswerTuiSyncTimer = null;
            __kbAnswerSyncToTextarea({ emit: true });
        }, 120);
    });
    try { __kbAnswerScheduleLayoutRefresh(); } catch {}
    return __kbAnswerTui;
}

function __kbAnswerSyncToTextarea(opts = {}) {
    const ta = __kbAnswerGetTextarea();
    if (!ta || !__kbAnswerTui) return;
    const md = __kbAnswerTui.getMarkdown();
    if (ta.value !== md) ta.value = md;
    if (opts.emit) {
        try { ta.dispatchEvent(new Event('input', { bubbles: true })); } catch {}
        try { ta.dispatchEvent(new Event('change', { bubbles: true })); } catch {}
    }
}

function __kbAnswerSetMarkdown(md, _opts = {}) {
    const ta = __kbAnswerGetTextarea();
    const text = String(md ?? '');
    if (ta) {
        ta.value = text;
        try { ta.dispatchEvent(new Event('input', { bubbles: true })); } catch {}
        try { ta.dispatchEvent(new Event('change', { bubbles: true })); } catch {}
    }
    const tui = __kbAnswerEnsureTui();
    if (tui) {
        try { tui.setMarkdown(text); } catch {}
    }
    try { __kbAnswerScheduleLayoutRefresh(); } catch {}
}

function __kbAnswerInsertText(text) {
    const tui = __kbAnswerEnsureTui();
    if (!tui) return;
    tui.focus();
    tui.replaceSelection(String(text ?? ''));
    __kbAnswerSyncToTextarea({ emit: true });
}

function insertMarkdown(prefix, suffix) {
    const tui = __kbAnswerEnsureTui();
    if (!tui) return;
    const p = String(prefix ?? '');
    const s = String(suffix ?? '');
    const selected = String(tui.getSelectedText() ?? '');
    tui.focus();
    tui.replaceSelection(p + selected + s);
    __kbAnswerSyncToTextarea({ emit: true });
}

function insertTextAtCursor(text) {
    __kbAnswerInsertText(text);
}

function insertLineBreak(kind) {
    const k = String(kind || '').trim().toLowerCase();
    if (k === 'soft') return __kbAnswerInsertText('  \n');
    if (k === 'paragraph') return __kbAnswerInsertText('\n\n');
    return __kbAnswerInsertText('\n');
}
window.insertLineBreak = insertLineBreak;

function toggleToolbarDropdown(id) {
    const root = document.getElementById(id);
    if (!root) return;
    const isOpen = root.classList.contains('open');
    closeAllToolbarDropdowns();
    if (!isOpen) {
        root.classList.add('open');
        // lazy load ops when opening quick insert
        if (id === 'quickInsertDropdown') {
            loadOpsLibrariesForToolbar().catch(() => {});
        }
    }
}
window.toggleToolbarDropdown = toggleToolbarDropdown;

function closeAllToolbarDropdowns() {
    document.querySelectorAll('.kb-toolbar-dropdown.open').forEach(el => el.classList.remove('open'));
}
window.closeAllToolbarDropdowns = closeAllToolbarDropdowns;

document.addEventListener('click', (e) => {
    const t = e.target;
    if (!t) return;
    if (t.closest && t.closest('.kb-toolbar-dropdown')) return;
    closeAllToolbarDropdowns();
});

// 三级菜单已改为弹窗（opsPickerModal），不再需要自动翻转 submenu

let __opsLibCache = { app: null, product: null, ts: 0 };

async function fetchOpsLibrary(kind) {
    const res = await fetch(API_BASE + `/ops/${kind}`, { method: 'GET' });
    const j = await res.json();
    if (!j || !j.success) throw new Error(j?.message || '加载操作库失败');
    return Array.isArray(j.data) ? j.data : [];
}

function renderOpsSubmenu(kind, items) {
    // Legacy: submenu UI removed; keep no-op for compatibility
    return;
}

function insertOpsStepsFromEl(el) {
    try {
        const steps = el?.getAttribute('data-steps') ?? '';
        if (!steps) return;
        insertTextAtCursor(steps);
        closeAllToolbarDropdowns();
    } catch {}
}
window.insertOpsStepsFromEl = insertOpsStepsFromEl;

async function loadOpsLibrariesForToolbar(force = false) {
    const now = Date.now();
    if (!force && __opsLibCache.ts && (now - __opsLibCache.ts) < 30_000 && __opsLibCache.app && __opsLibCache.product) {
        return;
    }
    const [appItems, productItems] = await Promise.all([fetchOpsLibrary('app'), fetchOpsLibrary('product')]);
    __opsLibCache = { app: appItems, product: productItems, ts: now };
}
window.loadOpsLibrariesForToolbar = loadOpsLibrariesForToolbar;

let __opsPickerKind = 'app';
let __opsPickerItems = [];

function openOpsPicker(kind) {
    const k = String(kind || '').trim().toLowerCase();
    __opsPickerKind = (k === 'product') ? 'product' : 'app';
    const modal = document.getElementById('opsPickerModal');
    const title = document.getElementById('opsPickerTitle');
    const search = document.getElementById('opsPickerSearch');
    if (title) title.textContent = __opsPickerKind === 'app' ? 'APP操作' : '产品操作';
    if (modal) modal.style.display = 'block';
    if (search) {
        search.value = '';
        search.oninput = () => renderOpsPickerList();
        setTimeout(() => search.focus(), 0);
    }
    loadOpsLibrariesForToolbar().then(() => {
        const items = (__opsLibCache && __opsLibCache[__opsPickerKind]) ? __opsLibCache[__opsPickerKind] : [];
        __opsPickerItems = Array.isArray(items) ? items : [];
        renderOpsPickerList();
    }).catch(e => {
        __opsPickerItems = [];
        renderOpsPickerList(e?.message || '加载失败');
    });
}
window.openOpsPicker = openOpsPicker;

function closeOpsPicker() {
    const modal = document.getElementById('opsPickerModal');
    if (modal) modal.style.display = 'none';
}
window.closeOpsPicker = closeOpsPicker;

function renderOpsPickerList(errorText = null) {
    const listEl = document.getElementById('opsPickerList');
    const q = (document.getElementById('opsPickerSearch')?.value || '').trim().toLowerCase();
    if (!listEl) return;
    if (errorText) {
        listEl.innerHTML = `<div class="text-muted" style="padding:10px;">${_escapeHtml(String(errorText))}</div>`;
        return;
    }
    const items = (__opsPickerItems || []).filter(it => {
        const name = String(it.name || '').toLowerCase();
        return !q || name.includes(q);
    });
    if (!items.length) {
        listEl.innerHTML = `<div class="text-muted" style="padding:10px;">暂无操作项</div>`;
        return;
    }
    listEl.innerHTML = items.map(it => {
        const name = String(it.name || '').trim() || '(未命名)';
        const models = String(it.compatible_models || '');
        return `
          <div style="display:flex; gap:8px; align-items:center; padding: 4px 0;">
            <button type="button" class="kb-toolbar-item" style="flex:1 1 auto;" onclick="pickOpsItem(${it.id})" title="${_escapeAttr(name)}">
              <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${_escapeHtml(name)}</span>
            </button>
            <button type="button" class="action-btn btn-sm" onclick="editOpsItemFromPicker(${it.id})">修改</button>
            <button type="button" class="danger-btn btn-sm" onclick="deleteOpsItemFromPicker(${it.id})">删除</button>
          </div>
        `;
    }).join('');
}

function pickOpsItem(id) {
    const it = (__opsPickerItems || []).find(x => String(x.id) === String(id));
    if (!it) return;
    const steps = String(it.steps || '');
    if (!steps.trim()) return;
    insertTextAtCursor(steps);
    closeOpsPicker();
}
window.pickOpsItem = pickOpsItem;

function openOpsItemEditorFromPicker() {
    openOpsItemModal(__opsPickerKind, null);
}
window.openOpsItemEditorFromPicker = openOpsItemEditorFromPicker;

function editOpsItemFromPicker(id) {
    openOpsItemModal(__opsPickerKind, id);
}
window.editOpsItemFromPicker = editOpsItemFromPicker;

async function deleteOpsItemFromPicker(id) {
    const prevKind = __opsLibraryActiveTab;
    __opsLibraryActiveTab = __opsPickerKind;
    try {
        await deleteOpsItem(id);
        await reloadOpsLibraryList();
        // refresh picker list
        __opsPickerItems = (__opsLibCache && __opsLibCache[__opsPickerKind]) ? __opsLibCache[__opsPickerKind] : [];
        renderOpsPickerList();
    } finally {
        __opsLibraryActiveTab = prevKind;
    }
}
window.deleteOpsItemFromPicker = deleteOpsItemFromPicker;

function openOpsItemEditorFromKind(kind, id) {
    const prevKind = __opsLibraryActiveTab;
    __opsLibraryActiveTab = (String(kind || '').toLowerCase() === 'product') ? 'product' : 'app';
    try {
        openOpsItemEditor(id);
    } finally {
        __opsLibraryActiveTab = prevKind;
    }
}

let __opsItemEditing = { kind: 'app', id: null };

function openOpsItemModal(kind, id) {
    const k = (String(kind || '').toLowerCase() === 'product') ? 'product' : 'app';
    __opsItemEditing = { kind: k, id: id || null };
    const modal = document.getElementById('opsItemModal');
    const titleEl = document.getElementById('opsItemTitle');
    const nameEl = document.getElementById('opsItemName');
    const stepsEl = document.getElementById('opsItemSteps');
    const modelsEl = document.getElementById('opsItemModels');
    const errEl = document.getElementById('opsItemError');
    if (errEl) { errEl.classList.add('d-none'); errEl.textContent = ''; }

    const items = (__opsLibCache && __opsLibCache[k]) ? __opsLibCache[k] : [];
    const cur = id ? (items || []).find(x => String(x.id) === String(id)) : null;
    if (titleEl) titleEl.textContent = (id ? '编辑操作项' : '新增操作项') + `（${k === 'app' ? 'APP' : '产品'}）`;
    if (nameEl) nameEl.value = cur ? String(cur.name || '') : '';
    if (stepsEl) stepsEl.value = cur ? String(cur.steps || '') : '';
    if (modelsEl) modelsEl.value = cur ? String(cur.compatible_models || '') : '';
    if (modal) modal.style.display = 'block';
    setTimeout(() => nameEl && nameEl.focus(), 0);
}
window.openOpsItemModal = openOpsItemModal;

function closeOpsItemModal() {
    const modal = document.getElementById('opsItemModal');
    if (modal) modal.style.display = 'none';
}
window.closeOpsItemModal = closeOpsItemModal;

async function submitOpsItemModal() {
    const nameEl = document.getElementById('opsItemName');
    const stepsEl = document.getElementById('opsItemSteps');
    const modelsEl = document.getElementById('opsItemModels');
    const errEl = document.getElementById('opsItemError');
    const name = (nameEl?.value || '').trim();
    const steps = (stepsEl?.value || '');
    const models = (modelsEl?.value || '').trim();
    if (!name || !String(steps).trim()) {
        if (errEl) {
            errEl.textContent = '保存失败：操作名称、操作步骤为必填项';
            errEl.classList.remove('d-none');
        }
        return;
    }
    if (errEl) { errEl.classList.add('d-none'); errEl.textContent = ''; }
    const prevKind = __opsLibraryActiveTab;
    __opsLibraryActiveTab = __opsItemEditing.kind;
    try {
        await saveOpsItem(__opsItemEditing.id, { name, steps, compatible_models: models });
        await reloadOpsLibraryList();
        __opsPickerItems = (__opsLibCache && __opsLibCache[__opsPickerKind]) ? __opsLibCache[__opsPickerKind] : [];
        renderOpsPickerList();
        closeOpsItemModal();
    } catch (e) {
        if (errEl) {
            errEl.textContent = '保存失败：' + (e?.message || String(e));
            errEl.classList.remove('d-none');
        } else {
            alert('保存失败: ' + (e?.message || String(e)));
        }
    } finally {
        __opsLibraryActiveTab = prevKind;
    }
}
window.submitOpsItemModal = submitOpsItemModal;


function triggerOpsImport() {
    const el = document.getElementById('opsImportInput');
    if (el) el.click();
}
window.triggerOpsImport = triggerOpsImport;

async function downloadOpsImportTemplate() {
    const templateUrl = API_BASE + `/ops/${__opsPickerKind}/template.xlsx`;
    const fallbackUrl = API_BASE + `/ops/${__opsPickerKind}/export.xlsx`;
    try {
        const resp = await fetch(templateUrl, { method: 'GET', credentials: 'same-origin' });
        if (resp.status === 404) {
            alert('模板接口未生效，已回退为导出现有数据。请重启后端后再试模板下载。');
            window.location = fallbackUrl;
            return;
        }
        if (resp.status === 401) {
            showLogin(true);
            throw new Error('Unauthorized');
        }
        if (!resp.ok) {
            const t = await resp.text();
            throw new Error(t || `HTTP ${resp.status}`);
        }
        const blob = await resp.blob();
        const href = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = href;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            try { URL.revokeObjectURL(href); } catch (e) {}
            try { a.remove(); } catch (e) {}
        }, 1000);
    } catch (e) {
        alert('模板下载失败: ' + (e && e.message ? e.message : String(e)));
    }
}
window.downloadOpsImportTemplate = downloadOpsImportTemplate;

async function handleOpsImportFile(file) {
    if (!file) return;
    try {
        const fd = new FormData();
        fd.append('file', file);
        const res = await fetch(API_BASE + `/ops/${__opsPickerKind}/import`, { method: 'POST', body: fd, credentials: 'same-origin' });
        if (res.status === 401) {
            showLogin(true);
            throw new Error('Unauthorized');
        }
        const text = await res.text();
        let j = null;
        try { j = text ? JSON.parse(text) : {}; } catch { throw new Error('响应不是 JSON'); }
        if (!j || !j.success) throw new Error(j?.message || '导入失败');
        await reloadOpsLibraryList();
        __opsPickerItems = (__opsLibCache && __opsLibCache[__opsPickerKind]) ? __opsLibCache[__opsPickerKind] : [];
        renderOpsPickerList();
        alert(`导入成功：新增 ${j.inserted || 0} 条，更新 ${j.updated || 0} 条`);
    } catch (e) {
        alert('导入失败: ' + e.message);
    } finally {
        const el = document.getElementById('opsImportInput');
        if (el) el.value = '';
    }
}
window.handleOpsImportFile = handleOpsImportFile;

function exportOpsExcel() {
    // direct download
    window.location = API_BASE + `/ops/${__opsPickerKind}/export.xlsx`;
}
window.exportOpsExcel = exportOpsExcel;

let __opsLibraryActiveTab = 'app';
let __opsLibraryItems = { app: [], product: [] };

function openOpsLibraryModal() {
    const modal = document.getElementById('opsLibraryModal');
    if (!modal) return;
    modal.style.display = 'block';
    switchOpsLibraryTab(__opsLibraryActiveTab || 'app');
    reloadOpsLibraryList().catch(e => alert('加载操作库失败: ' + e.message));
}
window.openOpsLibraryModal = openOpsLibraryModal;

function closeOpsLibraryModal() {
    const modal = document.getElementById('opsLibraryModal');
    if (modal) modal.style.display = 'none';
}
window.closeOpsLibraryModal = closeOpsLibraryModal;

function switchOpsLibraryTab(kind) {
    const k = String(kind || '').trim().toLowerCase();
    __opsLibraryActiveTab = (k === 'product') ? 'product' : 'app';
    const a = document.getElementById('opsTabApp');
    const p = document.getElementById('opsTabProduct');
    if (a) a.classList.toggle('active', __opsLibraryActiveTab === 'app');
    if (p) p.classList.toggle('active', __opsLibraryActiveTab === 'product');
    renderOpsLibraryTable();
}
window.switchOpsLibraryTab = switchOpsLibraryTab;

async function reloadOpsLibraryList() {
    const [appItems, productItems] = await Promise.all([fetchOpsLibrary('app'), fetchOpsLibrary('product')]);
    __opsLibraryItems = { app: appItems, product: productItems };
    // refresh toolbar cache too
    __opsLibCache = { app: appItems, product: productItems, ts: Date.now() };
    renderOpsSubmenu('app', appItems);
    renderOpsSubmenu('product', productItems);
    renderOpsLibraryTable();
}
window.reloadOpsLibraryList = reloadOpsLibraryList;

function renderOpsLibraryTable() {
    const tbody = document.getElementById('opsLibraryTbody');
    if (!tbody) return;
    const items = (__opsLibraryItems && __opsLibraryItems[__opsLibraryActiveTab]) ? __opsLibraryItems[__opsLibraryActiveTab] : [];
    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-message">暂无数据</td></tr>';
        return;
    }
    tbody.innerHTML = items.map((it, idx) => {
        const id = it.id;
        const name = _escapeHtml(String(it.name || ''));
        const steps = _escapeHtml(String(it.steps || ''));
        const models = _escapeHtml(String(it.compatible_models || ''));
        const upDisabled = idx === 0 ? 'disabled' : '';
        const downDisabled = idx === items.length - 1 ? 'disabled' : '';
        return `
          <tr>
            <td style="text-align:center;">
              <button class="action-btn btn-sm" ${upDisabled} onclick="moveOpsItem(${id}, -1)">↑</button>
              <button class="action-btn btn-sm" ${downDisabled} onclick="moveOpsItem(${id}, 1)">↓</button>
            </td>
            <td><div class="text-truncate" title="${_escapeAttr(name)}">${name}</div></td>
            <td><div class="text-truncate" title="${_escapeAttr(steps)}">${steps}</div></td>
            <td><div class="text-truncate" title="${_escapeAttr(models)}">${models}</div></td>
            <td style="text-align:center;">
              <button class="action-btn btn-sm" onclick="openOpsItemEditor(${id})">编辑</button>
              <button class="danger-btn btn-sm" onclick="deleteOpsItem(${id})">删除</button>
            </td>
          </tr>
        `;
    }).join('');
}

async function moveOpsItem(id, delta) {
    const items = (__opsLibraryItems && __opsLibraryItems[__opsLibraryActiveTab]) ? [...__opsLibraryItems[__opsLibraryActiveTab]] : [];
    const idx = items.findIndex(x => String(x.id) === String(id));
    if (idx < 0) return;
    const j = idx + delta;
    if (j < 0 || j >= items.length) return;
    const tmp = items[idx];
    items[idx] = items[j];
    items[j] = tmp;
    __opsLibraryItems[__opsLibraryActiveTab] = items;
    renderOpsLibraryTable();
    const ids = items.map(x => x.id);
    const res = await fetch(API_BASE + `/ops/${__opsLibraryActiveTab}/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids })
    });
    const jres = await res.json();
    if (!jres || !jres.success) {
        alert('排序保存失败: ' + (jres?.message || 'error'));
        await reloadOpsLibraryList();
    }
}
window.moveOpsItem = moveOpsItem;

async function deleteOpsItem(id) {
    if (!confirm('确认删除该操作项？')) return;
    const res = await fetch(API_BASE + `/ops/${__opsLibraryActiveTab}/${id}`, { method: 'DELETE' });
    const j = await res.json();
    if (!j || !j.success) {
        alert('删除失败: ' + (j?.message || 'error'));
        return;
    }
    await reloadOpsLibraryList();
}
window.deleteOpsItem = deleteOpsItem;

function openOpsItemEditor(id) {
    openOpsItemModal(__opsLibraryActiveTab, id);
}
window.openOpsItemEditor = openOpsItemEditor;

async function saveOpsItem(id, payload) {
    const kind = __opsLibraryActiveTab;
    const url = id ? (API_BASE + `/ops/${kind}/${id}`) : (API_BASE + `/ops/${kind}`);
    const method = id ? 'PUT' : 'POST';
    const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload || {}) });
    const j = await res.json();
    if (!j || !j.success) throw new Error(j?.message || 'error');
    await reloadOpsLibraryList();
}

function insertHeading(level) {
    if (!level) return;
    const numLevel = parseInt(level, 10);
    if (isNaN(numLevel)) return;
    
    const prefix = '#'.repeat(numLevel) + ' ';
    insertMarkdown(prefix, '');
}

function insertList(isOrdered) {
    const tui = __kbAnswerEnsureTui();
    if (!tui) return;
    const selected = String(tui.getSelectedText() ?? '');
    const hasSelection = !!selected;
    const raw = hasSelection ? selected : '';
    const lines = raw ? raw.split('\n') : [''];
    const newLines = lines.map((line, index) => {
        if (isOrdered) return `${index + 1}. ${line}`;
        return `- ${line}`;
    });
    tui.focus();
    tui.replaceSelection(newLines.join('\n'));
    __kbAnswerSyncToTextarea({ emit: true });
}

function insertCode() {
    insertMarkdown('```\n', '\n```');
}

// Export to global scope
window.insertMarkdown = insertMarkdown;
window.insertHeading = insertHeading;
window.insertList = insertList;
window.insertCode = insertCode;

function copyToClipboard(text) {
    if (!text) return;
    
    // Create a temporary textarea to handle the copy
    const textarea = document.createElement('textarea');
    textarea.value = text;
    
    // Make it invisible but part of the document
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '0';
    document.body.appendChild(textarea);
    
    // Select and copy
    textarea.focus();
    textarea.select();
    
    try {
        const successful = document.execCommand('copy');
        if (successful) {
            kbPushClipboardSession(text);
            showToast('复制成功');
        } else {
            console.error('Copy failed');
            alert('复制失败，请手动复制');
        }
    } catch (err) {
        console.error('Copy error', err);
        alert('复制出错');
    }
    
    document.body.removeChild(textarea);
}

document.addEventListener('copy', () => {
    try {
        const selected = String(window.getSelection ? window.getSelection().toString() : '').trim();
        if (selected) kbPushClipboardSession(selected);
    } catch {}
});

function searchKBById(id) {
    if (!id) return;
    
    // Switch to KB view
    switchTab('kbView');
    
    // Set ID search input
    const idInput = document.getElementById('idSearch');
    if (idInput) {
        idInput.value = id;
    }
    
    // Clear other inputs to ensure precise search
    if (document.getElementById('productNameSearch')) document.getElementById('productNameSearch').value = '';
    if (document.getElementById('questionSearch')) document.getElementById('questionSearch').value = '';
    if (document.getElementById('similarQuestionSearch')) document.getElementById('similarQuestionSearch').value = '';
    if (document.getElementById('answerSearch')) document.getElementById('answerSearch').value = '';
    if (document.getElementById('urlSearch')) document.getElementById('urlSearch').value = '';
    
    // Trigger search
    // Adding a small delay to ensure UI updates and tab switch completes
    setTimeout(() => {
        searchKB();
    }, 100);
}

function searchKBByUrl(url) {
    if (!url) return;
    
    // Switch to KB view
    switchTab('kbView');
    
    // Ensure we are scrolled to top or search area is visible
    window.scrollTo(0, 0);

    // Set URL search input
    const urlInput = document.getElementById('urlSearch');
    if (urlInput) {
        urlInput.value = url;
        urlInput.focus(); // Focus the input
    } else {
        console.warn('URL search input not found');
        return;
    }
    
    // Clear other inputs
    if (document.getElementById('idSearch')) document.getElementById('idSearch').value = '';
    if (document.getElementById('productNameSearch')) document.getElementById('productNameSearch').value = '';
    if (document.getElementById('questionSearch')) document.getElementById('questionSearch').value = '';
    if (document.getElementById('similarQuestionSearch')) document.getElementById('similarQuestionSearch').value = '';
    if (document.getElementById('answerSearch')) document.getElementById('answerSearch').value = '';
    
    // Trigger search
    searchKB();
}

// Export to global scope
window.copyToClipboard = copyToClipboard;
window.searchKBById = searchKBById;
window.searchKBByUrl = searchKBByUrl;
window.kbReadClipboardToBuffer = kbReadClipboardToBuffer;
window.kbClearClipboardBuffer = kbClearClipboardBuffer;
window.copyKBCellText = copyKBCellText;
