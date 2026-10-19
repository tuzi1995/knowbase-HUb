import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./app_v8.js', import.meta.url), 'utf8');
const start = source.indexOf('const PENDING_MODIFICATION_FIELD_LABELS =');
const end = source.indexOf('function renderPendingModificationRecords()', start);
assert.notEqual(start, -1, 'pending modification render helpers must exist');
assert.notEqual(end, -1, 'pending modification renderer boundary must exist');

const context = {
  escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, character => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[character]);
  },
};
const detailStart = source.indexOf('function _openModDetailsByItem(item) {');
const modelHelperStart = source.indexOf('function parseModDetailsObject(value) {');
assert.notEqual(modelHelperStart, -1, 'formal modification metadata parser must exist');
const modelHelperSource = source.slice(modelHelperStart, detailStart);
vm.runInNewContext(`${source.slice(start, end)}\nglobalThis.renderChange = renderPendingModificationChange;`, context);
vm.runInNewContext(`${modelHelperSource}\nglobalThis.getModelLabel = getModDetailsModelLabel; globalThis.getAssociationSummary = getModAssociationSummary;`, context);

test('pending-version snapshots render readable field changes and escaped full values', () => {
  const html = context.renderChange({
    baseline_snapshot: { question: '旧问题', answer: '旧答案' },
    pending_snapshot: { question: '新问题', answer: '<新答案>' },
  });

  assert.match(html, /2 项/);
  assert.match(html, /问题：新问题/);
  assert.match(html, /答案：&lt;新答案&gt;/);
  assert.match(html, /<em>原<\/em>旧问题/);
  assert.match(html, /<em>新<\/em>&lt;新答案&gt;/);
});

test('records with no field-level delta retain a useful change label', () => {
  const html = context.renderChange({
    before: { question: '相同内容' },
    after: { question: '相同内容' },
    change_type: 'kb_association',
  });

  assert.match(html, /内容变更（kb_association）/);
});

test('formal detail model falls back to nested change metadata', () => {
  assert.equal(context.getModelLabel({ change_meta: { model_id: 'P30 Member' } }), 'P30 Member');
  assert.equal(context.getModelLabel({ change_meta: JSON.stringify({ after: { products: 'P30 Member' } }) }), 'P30 Member');
});

test('association detail describes an added model without implying replacement', () => {
  assert.equal(context.getAssociationSummary({
    action_kind: 'association',
    before: { products: ['G10S Pro', 'G20S'] },
    after: { products: ['G10S Pro', 'G20S', 'P30 Member'] },
  }), '新增关联型号：P30 Member');
});
