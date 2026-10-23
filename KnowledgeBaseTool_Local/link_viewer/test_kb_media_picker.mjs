import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const source = readFileSync(new URL('./app_v8.js', import.meta.url), 'utf8');
const picker = source.slice(source.indexOf('const kbImageLinkPickerState ='), source.indexOf('window.newProductReleaseContext ='));
function setup() {
  const nodes = new Map();
  const element = () => ({ value: '', textContent: '', disabled: false, hidden: false, open: true,
    classList: {toggle(){},remove(){}},setAttribute(){},focus(){},dispatchEvent(){},close(){this.open=false;} });
  const get = id => { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); };
  const fields = {image_urls: element(), video_urls: element()};
  const calls = [], rendered = [], feedback = [];
  const context = vm.createContext({URL, URLSearchParams, Map, clearTimeout, setTimeout,
    Event: class {}, document: {getElementById:get, querySelectorAll:()=>[],
      querySelector:s=>fields[s.includes('video_urls')?'video_urls':'image_urls']},
    api:path=>new Promise((resolve,reject)=>calls.push({path,resolve,reject}))});
  vm.runInContext(picker, context);
  context.renderKBImageLinkPickerItems = items => rendered.push(items);
  context.renderKBImageLinkPickerFeedback = (...args) => feedback.push(args);
  get('kbImageLinkType').value='media'; get('kbImageLinkSort').value='desc';
  const run = code => vm.runInContext(code, context);
  const respond = (index, data, total=60, page=1) => calls[index].resolve({success:true,data,total,page});
  return {context,get,calls,rendered,feedback,fields,run,respond};
}

test('rapid filter changes discard old responses and keep the combined query', async()=>{
  const {context,get,calls,rendered,respond,run}=setup();
  const first = context.loadKBImageLinkPickerPage(2);
  get('kbImageLinkSearch').value='sample'; get('kbImageLinkType').value='video';
  run("kbImageLinkPickerState.mediaType='video'");
  get('kbImageLinkTag').value='产品对比图'; get('kbImageLinkSort').value='asc';
  const second = context.loadKBImageLinkPickerPage(1);
  const query=new URL(calls[1].path,'https://example.com').searchParams;
  assert.equal(query.get('tags'),'产品对比图'); assert.equal(query.get('search'),'sample');
  assert.equal(query.get('linkType'),'video'); assert.equal(query.get('sortDir'),'asc');
  respond(1,[{url:'new.mp4'}],3); respond(2,[],60); await second;
  respond(0,[{url:'old.jpg'}],60,2); await first;
  assert.equal(rendered.length,1); assert.equal(rendered[0][0].url,'new.mp4');
  assert.equal(get('kbImageLinkPickerStatus').textContent,'筛选出 3 个素材 · 共 60 个');
});

test('cross-page choices deduplicate; reset clears selections and keeps filters', async()=>{
  const {context,get,respond,run}=setup();
  context.toggleKBImageLinkPickerSelection({url:'a.jpg',type:'image'},true);
  context.toggleKBImageLinkPickerSelection({url:'a.jpg',type:'image'},true);
  const next=context.loadKBImageLinkPickerPage(2); respond(0,[],60,2); await next;
  assert.equal(get('kbImageLinkPickerSelectedCount').textContent,'已选 1 项');
  assert.equal(get('kbImageLinkPickerConfirm').disabled,false);
  get('kbImageLinkSearch').value='retained'; get('kbImageLinkTag').value='manual';
  context.resetKBImageLinkPickerSelection();
  assert.equal(run('kbImageLinkPickerState.selected.size'),0);
  assert.equal(get('kbImageLinkSearch').value,'retained'); assert.equal(get('kbImageLinkTag').value,'manual');
  assert.equal(get('kbImageLinkPickerConfirm').textContent,'插入所选素材 (0)');
  assert.equal(get('kbImageLinkPickerReset').disabled,true);
});

test('pagination respects boundaries and recovers after a failed request', async()=>{
  const {context,get,calls,respond,feedback}=setup();
  const load=context.loadKBImageLinkPickerPage(); calls[0].reject(new Error('offline')); await load;
  assert.equal(feedback.at(-1)[0],'error');
  const retry=context.loadKBImageLinkPickerPage(); respond(1,[],0); await retry;
  assert.equal(get('kbImageLinkPickerPrev').disabled,true); assert.equal(get('kbImageLinkPickerNext').disabled,true);
  context.changeKBImageLinkPickerPage(1); assert.equal(calls.length,2);
});

test('metadata decodes names, uses real dimensions, and reports missing size',()=>{
  const {context,run}=setup();
  const item={url:'https://example.com/%E5%B0%BA%E5%AF%B8%E5%9B%BE.PNG?token=foo',type:'image'};
  const meta=context.getKBImageLinkPickerMetadata(item);
  assert.equal(meta.name,'尺寸图.PNG'); assert.equal(meta.description,'PNG · 尺寸未提供 · 计算中…');
  assert.deepEqual(Array.from(meta.tags),[]);
  run("kbImageLinkPickerState.dimensions.set('https://example.com/x.mp4',{width:1920,height:1080})");
  const withTags=context.getKBImageLinkPickerMetadata({url:'https://example.com/x.mp4',type:'video',file_size:2097152,tags:['新品',' 评测 ']});
  assert.equal(withTags.description,'MP4 · 1920×1080 · 2.0 MB');
  assert.deepEqual(Array.from(withTags.tags),['新品','评测']);
});

test('file size is read from HEAD response and cached; unavailable size degrades gracefully',async()=>{
  const {context,run}=setup();
  context.normalizeSafeHttpUrl=url=>url;
  const requests=[];
  context.fetch=async(url,options)=>{requests.push({url,options}); return {ok:true,headers:{get:name=>name==='content-length'?'1536':null}};};
  const item={url:'https://cdn.example/a.jpg',type:'image'};
  const meta={textContent:'',title:''},row={isConnected:true};
  context.queueKBImageLinkPickerFileSize(item,meta,row);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requests.length,1); assert.equal(requests[0].options.method,'HEAD');
  assert.equal(meta.textContent,'JPG · 尺寸未提供 · 2 KB');
  assert.equal(context.getKBImageLinkPickerMetadata(item).description,'JPG · 尺寸未提供 · 2 KB');
  context.fetch=async()=>{throw new Error('CORS blocked');};
  context.queueKBImageLinkPickerFileSize({url:'https://cdn.example/b.mp4',type:'video'},{textContent:'',title:''},row);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(context.getKBImageLinkPickerMetadata({url:'https://cdn.example/b.mp4',type:'video'}).description,'MP4 · 尺寸未提供 · 大小未提供');
});

test('insertion separates image/video fields and avoids duplicate URLs',()=>{
  const {context,fields}=setup(); fields.image_urls.value='https://example.com/a.jpg';
  context.appendKBMediaLink('https://example.com/a.jpg','image');
  context.appendKBMediaLink('https://example.com/b.jpg','image');
  context.appendKBMediaLink('https://example.com/c.mp4','video');
  assert.equal(fields.image_urls.value,'https://example.com/a.jpg\nhttps://example.com/b.jpg');
  assert.equal(fields.video_urls.value,'https://example.com/c.mp4');
});

for (const mediaType of ['image', 'video']) {
  test(`${mediaType} entry keeps its type through search, reset and pagination`, async()=>{
    const {context,get,calls,respond,run}=setup();
    run(`kbImageLinkPickerState.mediaType='${mediaType}'`);
    get('kbImageLinkType').value=mediaType==='image'?'video':'image';
    get('kbImageLinkSearch').value='sample';
    const search=context.loadKBImageLinkPickerPage(1);
    for (const call of calls) assert.equal(new URL(call.path,'https://example.com').searchParams.get('linkType'),mediaType);
    respond(0,[],60); respond(1,[],60); await search;
    context.clearKBImageLinkPickerFilters();
    assert.equal(get('kbImageLinkType').value,mediaType);
    assert.equal(new URL(calls[2].path,'https://example.com').searchParams.get('linkType'),mediaType);
    respond(2,[],60); await new Promise(resolve=>setImmediate(resolve));
    context.changeKBImageLinkPickerPage(1);
    const pageQuery=new URL(calls[3].path,'https://example.com').searchParams;
    assert.equal(pageQuery.get('linkType'),mediaType); assert.equal(pageQuery.get('page'),'2');
    respond(3,[],60,2);
  });

  test(`${mediaType} entry rejects other types when selecting and confirming`,()=>{
    const {context,fields,run}=setup();
    run(`kbImageLinkPickerState.mediaType='${mediaType}'`);
    const image={url:'https://example.com/a.jpg',type:'image'};
    const video={url:'https://example.com/b.mp4',type:'video'};
    context.toggleKBImageLinkPickerSelection(image,true);
    context.toggleKBImageLinkPickerSelection(video,true);
    assert.equal(run('kbImageLinkPickerState.selected.size'),1);
    run("kbImageLinkPickerState.selected.set('stale',{url:'https://example.com/stale',type:'"+(mediaType==='image'?'video':'image')+"'})");
    context.confirmKBImageLinkPickerSelection();
    assert.equal(fields.image_urls.value,mediaType==='image'?image.url:'');
    assert.equal(fields.video_urls.value,mediaType==='video'?video.url:'');
  });
}
