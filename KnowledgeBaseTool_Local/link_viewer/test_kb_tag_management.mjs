import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./app_v8.js', import.meta.url), 'utf8');
const sync = source.slice(source.indexOf('function syncKbManagedTag('), source.indexOf('async function submitKbTagManagerAction('));

function setup() {
  const context = vm.createContext({});
  vm.runInContext(`
    let kbSelectedTags = new Set(['old','other']);
    let tempKbSelectedTags = new Set(['old']);
    let kbAllTags = ['old','other'];
    const copyConfigState = {selectedExcludeTags:new Set(['old']),availableExcludeTags:['old','other']};
    let clears = 0, summaries = 0, renders = 0;
    function clearKBCache(){clears++;}
    function updateKbTagFilterButton(){summaries++;}
    function renderCopyExcludeTags(){renders++;}
    function normalizeKnowledgeBaseTags(tags){return Array.from(new Set(tags)).sort();}
    ${sync}
    function snapshot(){return {selected:Array.from(kbSelectedTags),draft:Array.from(tempKbSelectedTags),
      all:kbAllTags,excluded:Array.from(copyConfigState.selectedExcludeTags),
      options:copyConfigState.availableExcludeTags,clears,summaries,renders};}
  `, context);
  return context;
}

test('rename updates active and draft filters, global options and clone exclusions', () => {
  const context = setup();
  context.syncKbManagedTag('old', 'renamed');
  assert.deepEqual(JSON.parse(JSON.stringify(context.snapshot())), {
    selected:['renamed','other'],draft:['renamed'],all:['other','renamed'],
    excluded:['renamed'],options:['other','renamed'],clears:1,summaries:1,renders:1,
  });
});

test('delete removes stale selected names from every in-memory tag consumer', () => {
  const context = setup();
  context.syncKbManagedTag('old', null);
  assert.deepEqual(JSON.parse(JSON.stringify(context.snapshot())), {
    selected:['other'],draft:[],all:['other'],excluded:[],options:['other'],
    clears:1,summaries:1,renders:1,
  });
});

test('unrelated tag changes preserve existing selections', () => {
  const context = setup();
  context.syncKbManagedTag('unused', null);
  const state = JSON.parse(JSON.stringify(context.snapshot()));
  assert.deepEqual(state.selected, ['old','other']);
  assert.deepEqual(state.excluded, ['old']);
});
