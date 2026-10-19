import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./app_v8.js', import.meta.url), 'utf8');
const functionStart = source.indexOf('function getNewProductReleaseWorkspaceModelId(');
const bodyStart = source.indexOf('{', functionStart);
let depth = 0;
let functionEnd = -1;
for (let index = bodyStart; index < source.length; index += 1) {
  if (source[index] === '{') depth += 1;
  if (source[index] === '}') depth -= 1;
  if (depth === 0) {
    functionEnd = index + 1;
    break;
  }
}
assert.notEqual(functionStart, -1, 'workspace model selector must exist');
assert.notEqual(functionEnd, -1, 'workspace model selector must be complete');
const selectWorkspaceModel = vm.runInNewContext(`(${source.slice(functionStart, functionEnd)})`);

test('selects a listed pending model even when a pending request exists', () => {
  const state = {
    pending_models: [{ model_id: 'P30 Member' }],
    pending_requests: [{ model_id: 'P30 Member', status: 'pending_release' }],
  };
  assert.equal(selectWorkspaceModel(state, 'A-100'), 'P30 Member');
});

test('preserves the current model while it remains pending', () => {
  const state = { pending_models: [{ model_id: 'P30 Member' }, { model_id: 'P40' }] };
  assert.equal(selectWorkspaceModel(state, 'P40'), 'P40');
});

test('falls back to a pending request when the catalog list is empty', () => {
  const state = { pending_requests: [{ model_id: 'P30 Member', status: 'pending_release' }] };
  assert.equal(selectWorkspaceModel(state, 'A-100'), 'P30 Member');
});
