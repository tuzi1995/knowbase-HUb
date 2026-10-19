import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./app_v8.js', import.meta.url), 'utf8');
const helpers = source.slice(source.indexOf('let kbMappingTagsConfig ='), source.indexOf('let kbSortBy ='));

function setup() {
  const elements = new Map([
    ['kbEditMappingTags', { innerHTML: '' }],
    ['kbEditPreviewMappingTags', { innerHTML: '' }],
    ['kbEditTagsInput', { value: '普通标签' }],
    ['kbMappingTagFilter', {
      value: '', options: [],
      replaceChildren(option) { this.options = [option]; },
      add(option) { this.options.push(option); },
    }],
  ]);
  const state = { config: { 双型号: ['A10', 'A20'], 单型号: ['A10'] }, clears: 0 };
  const context = vm.createContext({
    document: { getElementById: id => elements.get(id) },
    Option: class { constructor(text, value) { this.text = text; this.value = value; } },
    api: async () => structuredClone(state.config),
    clearKBCache: () => state.clears++,
    escapeHtml: value => String(value).replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[char]),
  });
  vm.runInContext(helpers, context);
  return { context, elements, state };
}

test('model sets must match exactly, independent of model order and formatting', async () => {
  const { context } = setup();
  await context.refreshKBMappingTagsConfig();
  for (const value of ['A20,A10', 'a 10，a20', 'A10\nA20', '["A20","A10"]', ['A10', 'A20', 'A10']]) {
    assert.deepEqual(Array.from(context.getKBMappingTags(value)), ['双型号']);
  }
  assert.deepEqual(Array.from(context.getKBMappingTags('A10')), ['单型号']);
  for (const value of ['', null, 'A20', 'A10,A20,A30', 'A10,A200']) {
    assert.deepEqual(Array.from(context.getKBMappingTags(value)), []);
  }
});

test('editor preview follows model changes without modifying manual tags', async () => {
  const { context, elements } = setup();
  await context.refreshKBMappingTagsConfig();
  context.renderKBEditMappingTags('A10,A20');
  for (const id of ['kbEditMappingTags', 'kbEditPreviewMappingTags']) {
    assert.match(elements.get(id).innerHTML, /映射 · 双型号/);
    assert.match(elements.get(id).innerHTML, /kb-mapping-tag/);
  }
  context.renderKBEditMappingTags('A10,A20,A30');
  assert.match(elements.get('kbEditMappingTags').innerHTML, /无完全匹配/);
  assert.equal(elements.get('kbEditTagsInput').value, '普通标签');
});

test('mapping changes invalidate cached pages and remove stale tags', async () => {
  const { context, state } = setup();
  await context.refreshKBMappingTagsConfig();
  assert.equal(state.clears, 1);
  await context.refreshKBMappingTagsConfig();
  assert.equal(state.clears, 1);
  state.config = { 新名称: ['A10', 'A20', 'A30'] };
  await context.refreshKBMappingTagsConfig();
  assert.equal(state.clears, 2);
  assert.deepEqual(Array.from(context.getKBMappingTags('A10,A20')), []);
  assert.deepEqual(Array.from(context.getKBMappingTags('A10,A20,A30')), ['新名称']);
});

test('deleted mapping filter remains selected until reset and never silently widens results', async () => {
  const { context, elements, state } = setup();
  await context.refreshKBMappingTagsConfig();
  elements.get('kbMappingTagFilter').value = '双型号';
  state.config = {};
  await context.refreshKBMappingTagsConfig();
  assert.equal(elements.get('kbMappingTagFilter').value, '双型号');
  assert.equal(elements.get('kbMappingTagFilter').options.at(-1).text, '双型号（已删除）');
});

test('mapping category text is escaped in tags and tooltips', () => {
  const { context } = setup();
  const html = context.kbMappingTagHtml('<img src=x onerror="alert(1)">');
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
  assert.match(html, /&quot;/);
});
