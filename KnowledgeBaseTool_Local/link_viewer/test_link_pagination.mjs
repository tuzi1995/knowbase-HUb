import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./app_v8.js', import.meta.url), 'utf8');
const block = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const rows = count => Array.from({ length: count }, (_, id) => ({ id: String(id), tags: [], url: `https://example.com/${id}` }));

function setup(api) {
  const elements = new Map();
  for (const id of ['tableBody', 'linkPageInfo', 'linkPageJumpInput', 'linkPageJumpBtn', 'prevLinkPageBtn', 'nextLinkPageBtn', 'firstLinkPageBtn', 'lastLinkPageBtn', 'linkPageSizeSelect', 'linkSearchURL', 'linkSearchKBID', 'linkFilterStatus', 'linkFilterType', 'linkLoadStatus', 'linkLoadStatusText', 'retryLoadLinksBtn']) {
    elements.set(id, { value: '', children: [], classList: { toggle() {} }, appendChild(child) { this.children.push(child); }, set innerHTML(value) { this.children = []; this.html = value; } });
  }
  const table = { scrollTop: 150 };
  const context = vm.createContext({
    api, table, elements,
    document: {
      getElementById: id => elements.get(id),
      querySelector: selector => selector.includes('tagFilterMode') ? { value: 'any' } : table,
      querySelectorAll: () => [],
    },
    fetchGlobalTags: async () => {}, loadLinkTableWidths: () => ({}),
    applyLinkTableWidths() {}, updateLinkTagSelectorSummary() {}, updateBatchUI() {}, makeTableResizable() {},
    renderLinkRow: item => item,
  });
  vm.runInContext(`let currentLinks = [], linksLoaded = false, linksLoadPromise = null, linkFilterKey = '';
    let activeFilterTags = [], selectedIds = new Set(), linkCurrentPage = 1, linkPageSize = 20, linkShowDuplicateUrlsOnly = false, linkTableWidths = {};
    function getFilteredLinkItems() { return elements.get('linkSearchURL').value ? currentLinks.filter(item => item.url.includes(elements.get('linkSearchURL').value)) : currentLinks; }
    ${block('async function fetchAllLinkItems()', 'async function addLink(')}
    ${block('function changeLinkPage(offset)', 'function handleLinkSort(')}
    ${block('function renderLinkTable()', '// ==========================================\n// Governance View Logic')}`, context);
  return { elements, table, run: expression => vm.runInContext(expression, context), context };
}

test('loads records after the first 1000 with stable ordering, for search and export', async () => {
  const all = rows(1025);
  const calls = [];
  const app = setup(async path => {
    const params = new URL(`https://example.com${path}`).searchParams;
    calls.push(path);
    assert.equal(params.get('sortBy'), 'id');
    assert.equal(params.get('sortDir'), 'asc');
    const start = (Number(params.get('page')) - 1) * 1000;
    return { success: true, data: all.slice(start, start + 1000), total: all.length };
  });
  await app.run('loadLinks()');
  assert.equal(calls.length, 2);
  assert.equal(app.run('currentLinks.length'), 1025);
  app.run('jumpLinkPage(52)');
  assert.equal(app.elements.get('tableBody').children.length, 5);
  assert.match(app.elements.get('linkPageInfo').textContent, /52 \/ 52 页 · 显示 1021–1025 条/);
  app.elements.get('linkSearchURL').value = '/1024';
  app.run('renderLinkTable()');
  assert.equal(app.run('linkCurrentPage'), 1);
  assert.equal(app.elements.get('tableBody').children[0].id, '1024');
});

test('a later fetch failure preserves the previous complete list and exposes retry', async () => {
  const app = setup(async path => path.includes('page=1&')
    ? { success: true, data: rows(1000), total: 1025 }
    : { success: false, message: '服务暂不可用', data: [] });
  app.context.oldRows = rows(3);
  app.run('currentLinks = oldRows; linksLoaded = true;');
  await app.run('loadLinks()');
  assert.equal(app.run('currentLinks.length'), 3);
  assert.equal(app.run('linksLoaded'), false);
  assert.equal(app.elements.get('retryLoadLinksBtn').hidden, false);
  assert.match(app.elements.get('linkLoadStatusText').textContent, /服务暂不可用.*上次加载/);
});

test('concurrent loads reuse one fetch instead of racing to replace the collection', async () => {
  let finish;
  let calls = 0;
  const app = setup(() => { calls += 1; return new Promise(resolve => { finish = resolve; }); });
  const first = app.run('loadLinks()');
  const second = app.run('loadLinks()');
  finish({ success: true, data: rows(1), total: 1 });
  await Promise.all([first, second]);
  assert.equal(calls, 1);
});

test('page boundaries, invalid jumps, page size and a shrinking last page stay valid', () => {
  const app = setup();
  app.context.sample = rows(41);
  app.run('currentLinks = sample; renderLinkTable(); changeLinkPage(999);');
  assert.equal(app.run('linkCurrentPage'), 3);
  assert.equal(app.elements.get('lastLinkPageBtn').disabled, true);
  assert.equal(app.elements.get('nextLinkPageBtn').disabled, true);
  assert.equal(app.table.scrollTop, 0);
  app.run('jumpLinkPage(0); jumpLinkPage(1.5);');
  assert.equal(app.run('linkCurrentPage'), 3);
  app.run('currentLinks = currentLinks.slice(0, 40); renderLinkTable();');
  assert.equal(app.run('linkCurrentPage'), 2);
  assert.equal(app.elements.get('tableBody').children.length, 20);
  app.elements.get('linkPageSizeSelect').value = '50';
  app.run('changeLinkPageSize()');
  assert.equal(app.run('linkCurrentPage'), 1);
  assert.equal(app.elements.get('tableBody').children.length, 40);
});

test('empty filters reset paging and disable navigation and jump controls', () => {
  const app = setup();
  app.context.sample = rows(41);
  app.run('currentLinks = sample; renderLinkTable(); changeLinkPage(1);');
  app.elements.get('linkSearchURL').value = 'no-match';
  app.run('renderLinkTable()');
  assert.equal(app.run('linkCurrentPage'), 1);
  assert.match(app.elements.get('linkPageInfo').textContent, /共 0 条/);
  for (const id of ['firstLinkPageBtn', 'prevLinkPageBtn', 'nextLinkPageBtn', 'lastLinkPageBtn', 'linkPageJumpInput', 'linkPageJumpBtn']) {
    assert.equal(app.elements.get(id).disabled, true, id);
  }
});
