import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
const source = readFileSync(new URL('./app_v8.js', import.meta.url), 'utf8');
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const sectionToEnd = start => source.slice(source.indexOf(start), source.indexOf('\n// ', source.indexOf(start)));
function setup() {
  function element() {
    const node = {value:'', textContent:'', hidden:true, children:[], checked:false,
      style:{}, classList:{toggle(){}, add(){}, remove(){}}, setAttribute(){}, focus(){},
      replaceChildren(){this.children=[];}, append(...nodes){this.children.push(...nodes);},
      appendChild(node){this.children.push(node);}, addEventListener(name, handler){this[name]=handler;},
    getBoundingClientRect(){return {left:100,top:100,bottom:140};}, dispatchEvent(){}};
    Object.defineProperty(node, 'innerHTML', {set(){node.children=[];}});
    return node;
  }
  const nodes = Object.fromEntries(['tagFilter','linkTagSelectorBtn','linkTagDropdown','linkTagFilterSearch',
    'linkTagFilterSelectionCount','linkTagSelectorValue','linkTagFilterCount','linkFilterType'].map(id=>[id,element()]));
  nodes.linkFilterType.value='all';
  const modes=[{value:'any',checked:true},{value:'all',checked:false}];
  const drafts=[{value:'any',checked:true},{value:'all',checked:false}];
  const context=vm.createContext({Event:class Event { constructor(type){this.type=type;} },window:{innerWidth:1200,innerHeight:900},document:{
    getElementById:id=>nodes[id]||null, createElement:element,
    addEventListener(){},
    querySelector:selector=>(selector.includes('linkTagFilterModeDraft')?drafts:modes).find(input=>input.checked),
    querySelectorAll:selector=>selector.includes('linkTagFilterModeDraft')?drafts:modes}});
  vm.runInContext(`let currentLinks=[], activeFilterTags=[], linkCurrentPage=5, linkShowDuplicateUrlsOnly=false,
    linkSortBy='',linkSortDir='desc',allTags=[]; const LINK_EMPTY_TAG_FILTER=''; let renders=0;
    function renderLinkTable(){renders++; updateLinkTagSelectorSummary();}
    function normalizeKnowledgeBaseTags(tags){return [...new Set(tags)].sort();}
    ${section('function _isSysLinkTag(', 'function _getLinkSysMeta(')}
    ${sectionToEnd('function setupRowTagInput(')}
    ${section('let tempLinkSelectedTags =', 'function parseCreatedAtSeconds(')}
    ${section('function getFilteredLinkItems(', 'function renderLinkRow(')}
    ${section('function syncLinkManagedTag(', 'async function submitLinkTagManagerAction(')}
    currentLinks=[{id:1,tags:[],type:'image'},{id:2,tags:null,type:'image'},
      {id:3,tags:['来源:图片链接'],type:'image'},{id:4,tags:['外链类型:url'],type:'link'},
      {id:5,tags:['来源:图片链接','尺寸图'],type:'image'},{id:6,tags:['尺寸图','开箱图'],type:'image'},
      {id:7,tags:['   '],type:'image'},{id:8,tags:['空标签'],type:'image'}];`,context);
  const run=code=>vm.runInContext(code,context);
  const ids=()=>Array.from(context.getFilteredLinkItems(),item=>item.id);
  return {context,nodes,modes,drafts,run,ids};
}

test('empty business tags include provenance-only records and combine with type and any/all',()=>{
  const {run,ids,nodes,modes}=setup();
  run("activeFilterTags=['']"); assert.deepEqual(ids(),[1,2,3,4,7]);
  nodes.linkFilterType.value='image'; assert.deepEqual(ids(),[1,2,3,7]);
  nodes.linkFilterType.value='all'; run("activeFilterTags=['','尺寸图']");
  assert.deepEqual(ids(),[1,2,3,4,5,6,7]);
  modes[0].checked=false;modes[1].checked=true;assert.deepEqual(ids(),[]);
  run("activeFilterTags=['尺寸图','开箱图']");assert.deepEqual(ids(),[6]);
  run("activeFilterTags=['空标签']");assert.deepEqual(ids(),[8]);
  run('activeFilterTags=[]');assert.equal(ids().length,8);
});

test('search preserves draft checks; cancel discards; confirm applies',()=>{
  const {context,nodes,run,ids}=setup();
  context.setLinkTagDropdownOpen(true);
  assert.equal(nodes.tagFilter.children[0].children[1].textContent,'空标签');
  nodes.tagFilter.children[0].children[0].checked=true;
  nodes.tagFilter.children[0].children[0].change();
  nodes.linkTagFilterSearch.value='尺寸';context.renderLinkTagFilterList();
  assert.equal(nodes.tagFilter.children.length,1);
  assert.equal(run('tempLinkSelectedTags.has("")'),true);
  context.setLinkTagDropdownOpen(false);assert.equal(ids().length,8);
  context.setLinkTagDropdownOpen(true);assert.equal(run('tempLinkSelectedTags.size'),0);
  nodes.tagFilter.children[0].children[0].checked=true;
  nodes.tagFilter.children[0].children[0].change();context.applyLinkTagFilterDropdown();
  assert.deepEqual(ids(),[1,2,3,4,7]);assert.equal(nodes.linkTagSelectorValue.textContent,'空标签');
  context.setLinkTagDropdownOpen(true);context.clearLinkTagFilterDropdown();
  context.applyLinkTagFilterDropdown();assert.equal(ids().length,8);
});

test('rename/delete sync selected filters and affected records without touching provenance',()=>{
  const {context,run,ids}=setup();
  run("activeFilterTags=['尺寸图'];tempLinkSelectedTags=new Set(['尺寸图'])");
  context.syncLinkManagedTag({old_name:'尺寸图',name:'新标签',items:[
    {id:5,tags:['来源:图片链接','新标签']},{id:6,tags:['新标签','开箱图']}]});
  assert.deepEqual(ids(),[5,6]);assert.equal(run('activeFilterTags[0]'),'新标签');
  assert.equal(run('currentLinks[4].tags[0]'),'来源:图片链接');
  context.syncLinkManagedTag({old_name:'新标签',name:null,items:[
    {id:5,tags:['来源:图片链接']},{id:6,tags:['开箱图']}]});
  assert.equal(run('activeFilterTags.length'),0);
  run("activeFilterTags=['']");assert.deepEqual(ids(),[1,2,3,4,5,7]);
});

test('row tag input searches the shared full tag set and replaces the current fragment',()=>{
  const {context,run}=setup();
  run("allTags=['开箱图','尺寸图','说明书','长标签4','长标签5','长标签6','长标签7','长标签8','长标签9','长标签10','长标签11']");
  const input={value:'',addEventListener(name,handler){this[name]=handler;},focus(){},dispatchEvent(){}};
  const container={style:{},children:[],appendChild(node){this.children.push(node);},contains(){return true;}};
  context.setupRowTagInput(input,container,['开箱图']);
  input.value='说明';input.input();
  const dropdown=container.children[0];
  assert.deepEqual(dropdown.children.map(item=>item.textContent),['说明书']);
  input.value='已有, 尺';input.input();
  assert.deepEqual(dropdown.children.map(item=>item.textContent),['尺寸图']);
  dropdown.children[0].onclick({stopPropagation(){}});
  assert.equal(input.value,'已有, 尺寸图');
  input.value='新标签';input.input();
  assert.equal(dropdown.textContent,'无匹配标签，可直接添加');
});
