import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./app_v8.js', import.meta.url), 'utf8');
const helpers = source.slice(source.indexOf('let kbMappingTagsConfig ='), source.indexOf('let kbSortBy ='));
const editor = source.slice(source.indexOf('let modelMappings ='), source.indexOf('// 一键复制某分类下的全部型号'));

class Element {
  constructor() {
    this.children = []; this.dataset = {}; this.value = ''; this.options = [];
    this.classList = { toggle() {}, add() {} };
  }
  set innerHTML(value) { this.html = value; this.children = []; }
  get innerHTML() { return this.html || ''; }
  appendChild(element) { this.children.push(element); return element; }
  append(element) { this.children.push(element); }
  replaceChildren(element) { this.options = [element]; }
  add(element) { this.options.push(element); }
  setAttribute() {}
  querySelector() { return null; }
  scrollIntoView() {}
}

function setup() {
  const elements = new Map(['modelMappingTableBody', 'modelMappingSearch', 'kbMappingTagFilter',
    'matrixMappingCategorySelect'].map(id => [id, new Element()]));
  const state = { mappings: { A系列: ['A10'], Z系列: ['A10'], 中间: ['A20'] },
    category_order: ['Z系列', '中间', 'A系列'], clears: 0 };
  const context = vm.createContext({
    document: { getElementById: id => elements.get(id), createElement: () => new Element(),
      createTextNode: text => ({ textContent: text }), querySelectorAll: () => [] },
    Option: class { constructor(text, value) { this.text = text; this.value = value; } },
    api: async () => ({ mappings: structuredClone(state.mappings), category_order: [...state.category_order] }),
    clearKBCache: () => state.clears++, confirm: () => true,
  });
  vm.runInContext(helpers + '\n' + editor, context);
  vm.runInContext(source.slice(source.indexOf('function renderMatrixMappingCategorySelect('),
    source.indexOf('let matrixProductMatchMode =')), context);
  vm.runInContext('modelMappings = ' + JSON.stringify(state.mappings) + '; modelMappingCategoryOrder = ' + JSON.stringify(state.category_order), context);
  const names = () => elements.get('modelMappingTableBody').children.map(row => row.dataset.mappingCategory);
  return { context, elements, state, names };
}

test('move buttons reorder rows and disable moves at the boundaries', () => {
  const { context, elements, names } = setup();
  context.renderModelMappingTable();
  assert.deepEqual(names(), ['Z系列', '中间', 'A系列']);
  const rows = elements.get('modelMappingTableBody').children;
  assert.equal(rows[0].children[2].children[0].disabled, true);
  assert.equal(rows[2].children[2].children[1].disabled, true);
  rows[0].children[2].children[1].onclick();
  assert.deepEqual(names(), ['中间', 'Z系列', 'A系列']);
  context.moveMappingCategory('A系列', 1);
  assert.deepEqual(names(), ['中间', 'Z系列', 'A系列']);
});

test('search moves within full order; rename, delete, and add preserve order', () => {
  const { context, elements, names } = setup();
  elements.get('modelMappingSearch').value = 'Z系列';
  context.moveMappingCategory('Z系列', 1);
  assert.deepEqual(names(), ['Z系列']);
  elements.get('modelMappingSearch').value = '';
  context.renameMappingCategory('Z系列', '新名称');
  assert.deepEqual(names(), ['中间', '新名称', 'A系列']);
  context.deleteMappingCategory('中间');
  context.addMappingCategory();
  assert.deepEqual(names(), ['新名称', 'A系列', '新分类']);
});

test('mapping filters, tags, and matrix select respect order; order-only changes invalidate cache', async () => {
  const { context, elements, state } = setup();
  await context.refreshKBMappingTagsConfig();
  assert.deepEqual(elements.get('kbMappingTagFilter').options.map(option => option.value), ['', 'Z系列', '中间', 'A系列']);
  assert.deepEqual(Array.from(context.getKBMappingTags('A10')), ['Z系列', 'A系列']);
  context.renderMatrixMappingCategorySelect(state.category_order, 'A系列');
  assert.deepEqual(elements.get('matrixMappingCategorySelect').children.map(option => option.value), ['', 'Z系列', '中间', 'A系列']);
  assert.equal(elements.get('matrixMappingCategorySelect').value, 'A系列');
  await context.refreshKBMappingTagsConfig();
  assert.equal(state.clears, 1);
  state.category_order = ['A系列', 'Z系列', '中间'];
  await context.refreshKBMappingTagsConfig();
  assert.equal(state.clears, 2);
  assert.deepEqual(Array.from(context.getKBMappingTags('A10')), ['A系列', 'Z系列']);
});

test('legacy response falls back to name order and new categories append', () => {
  const { context } = setup();
  assert.deepEqual(Array.from(context.orderedMappingCategories({ Z: [], A: [], B: [] }, ['Z', 'missing', 'Z'])), ['Z', 'A', 'B']);
  assert.deepEqual(Array.from(context.orderedMappingCategories({ Z: [], A: [] })), ['A', 'Z']);
});
