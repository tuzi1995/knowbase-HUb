#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv, json, sqlite3, os, itertools, re, collections
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter

ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','..'))
DB=os.path.join(ROOT,'KnowledgeBaseTool_Local','instance','data.db')
CSV='/Users/tuzi/Downloads/20261023_s01_kb8085_kb_export_v1.csv'
OUT=os.path.join(os.path.dirname(__file__),'产品对比图片执行核对_20261023.xlsx')
RULE='/Volumes/ORICO/个人笔记记录/电子脑洞仓库/55_KnowBaseHub_8085/知识库内容管理/20261023_产品对比图录入规则.md'
READ_AT=datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')

def parse_imgs(s):
    if not s or not str(s).strip(): return []
    try: v=json.loads(s)
    except Exception: return [x.strip() for x in str(s).split(',') if x.strip()]
    if isinstance(v,list): return [str(x).strip() for x in v if str(x).strip()]
    return [str(v)]
def ordered(models, order): return sorted(models,key=lambda x:(order.get(x,10**9),x))
def csv_url(value):
    xs=parse_imgs(value)
    return xs

def main():
    con=sqlite3.connect(f'file:{DB}?mode=ro',uri=True); con.row_factory=sqlite3.Row
    order={r['product_name']:r['sort_order'] for r in con.execute('select product_name,sort_order from matrix_column order by sort_order')}
    # Read alias/group map as a cross-check. CSV KB tokens are already canonical model keys.
    mm=json.load(open(os.path.join(ROOT,'KnowledgeBaseTool_Local','model_mappings.json'),encoding='utf-8'))
    canonical=set(order)
    modelcat={}
    for r in con.execute("select business_key,properties_json from kg_nodes where node_type='product_model' and status='active'"):
        try:modelcat[r['business_key']]=json.loads(r['properties_json'] or '{}').get('product_category','')
        except:modelcat[r['business_key']] = ''
    assets=[]
    for r in con.execute('select * from comparison_image_asset'):
        a=dict(r); a['models']=set(json.loads(a['models_json'] or '[]')); a['count']=len(a['models'])
        known=[order[m] for m in a['models'] if m in order]; a['newest_order']=max(known) if known else -1
        a['newest_models']=[m for m in a['models'] if order.get(m)==a['newest_order']]
        a['selected']=False
        assets.append(a)
    # comparison cell decisions: actual decision/selection state, not inferred from draft assets
    decisions=list(con.execute('select d.*,c.category,c.pair_json from comparison_image_decision d left join comparison_image_cell c on c.id=d.cell_id'))
    selected_asset_ids={r['asset_id'] for r in decisions if r['asset_id'] and r['status'] in ('selected','completed','执行成功','已完成')}
    for a in assets: a['selected']=a['id'] in selected_asset_ids
    # current full KB index aggregated by wiki id
    current=collections.defaultdict(lambda:{'models':set(),'question':'','category':''})
    for r in con.execute('select question_wiki_id,product_name,question_content,product_category from product_matrix'):
        x=current[r['question_wiki_id']]; x['question']=r['question_content'] or x['question']; x['category']=r['product_category'] or x['category']
        if r['product_name']: x['models'].add(r['product_name'].strip())
    # Retrieval index contains full-library questions and aggregated product_names, used as second duplicate cross-check.
    retrieval={r['question_wiki_id']:r for r in con.execute("select question_wiki_id,question,product_names_json,product_category_name from kb_retrieval_index where library_type='knowledge_base_v1'")}
    rows=list(csv.DictReader(open(CSV,encoding='utf-8-sig')))
    assert len(rows)==133 and len({r['question_wiki_id'] for r in rows})==133
    kbs=[]
    for r in rows:
        raw=[x.strip() for x in (r['product_name'] or '').split(',') if x.strip()]
        std=set(raw); unknown=std-canonical
        im=csv_url(r.get('image_urls',''))
        cur=current.get(r['question_wiki_id'])
        current_models=cur['models'] if cur else set()
        kbs.append({**r,'models':std,'models_ordered':ordered(std,order),'unknown':unknown,'images':im,'current':cur,'current_models':current_models})
    # Proposed per-KB image: coverage/category only; platform unavailable, candidate ordering exactly business priorities.
    processed=[]
    for kb in kbs:
        cand=[a for a in assets if a['category']==kb['product_category_name'] and kb['models']<=a['models']]
        cand.sort(key=lambda a:(-a['newest_order'],-a['count']))
        chosen=None; unresolved=False
        if cand:
            top=(cand[0]['newest_order'],cand[0]['count'])
            topcand=[a for a in cand if (a['newest_order'],a['count'])==top]
            sets={frozenset(a['models']) for a in topcand}
            # If exact same eligible set, use established selected link if present; otherwise only a unique link is unambiguous.
            if len(sets)==1:
                sel=[a for a in topcand if a['selected']]
                urls={a['url'] for a in topcand}
                if len(sel)==1: chosen=sel[0]
                elif len(urls)==1: chosen=topcand[0]
                else: unresolved=True
            elif len(topcand)==1: chosen=topcand[0]
            else: unresolved=True
        old=kb['images']; old_primary=old[0] if old else ''
        old_asset=next((a for a in assets if a['url']==old_primary),None)
        old_coverage=bool(old_asset and kb['models']<=old_asset['models'] and old_asset['category']==kb['product_category_name'])
        partial=bool(old_asset and not old_coverage)
        if unresolved:
            conclusion='待人工确认选图'
        elif chosen:
            conclusion=('保留' if old_primary and old_primary==chosen['url'] else ('修改' if old_primary else '补充'))
        elif old_asset and partial:
            conclusion='保留旧图并登记缺口'
        else:
            conclusion='待补图'
        reasons=[]
        if not unknown: reasons.append('CSV关联型号均精确命中型号库标准名；未做版本合并')
        else: reasons.append('存在型号库未命中型号，需核实别名/版本：'+','.join(sorted(unknown)))
        if chosen:
            reasons.append(f"完整覆盖{len(kb['models'])}个所问标准型号；候选{len(cand)}张；最新型号{','.join(ordered(chosen['newest_models'],order))}(录入序{chosen['newest_order']})；覆盖{chosen['count']}型号")
        elif unresolved:
            reasons.append('最高优先级候选并列且型号集合不同/标准链接未定；不得按文件名或ID猜选')
        else: reasons.append('当前资产中无品类匹配且完整覆盖全部所问型号的候选')
        if partial: reasons.append('CSV原图在资产库中存在但未完整覆盖；保留旧图供人工处理，不判为可用完整覆盖')
        if old_primary and not old_asset: reasons.append('CSV原图链接未在当前图片资产清单中匹配；当前实际引用无法从DB验证')
        if len(old)>1: reasons.append(f'CSV原图含{len(old)}个URL；违反单KB最多一个图片链接建议，逐条人工核对')
        if kb['product_category_name'] and any(a['category']==kb['product_category_name'] for a in assets): reasons.append('资产记录有品类且已确认；平台字段在当前源中缺失，平台适用仍需核实')
        else: reasons.append('平台/品类适用信息不足，需人工确认')
        if not kb['current']: match='当前product_matrix未找到该KB编号'
        else:
            match='当前KB型号：'+','.join(ordered(kb['current_models'],order))
            if kb['current_models']!=kb['models']: match+='；与CSV原型号不同'
            else: match+='；与CSV原型号一致'
        if not kb['current']: match+='；完整库核对来自当前retrieval index（若存在）'
        # question and exact model set duplicate提示
        duplicates=[]
        for qid,x in current.items():
            if qid==kb['question_wiki_id'] or x['category']!=kb['product_category_name']: continue
            if x['models']==kb['models'] and kb['models']:
                duplicates.append(qid)
        dup='完全相同关联型号集合KB：'+','.join(duplicates[:30]) if duplicates else ''
        # similarities exact normalized question
        qnorm=re.sub(r'[\s？?，,。！!]','',kb['question'])
        sameq=[qid for qid,x in current.items() if qid!=kb['question_wiki_id'] and re.sub(r'[\s？?，,。！!]','',x['question'])==qnorm]
        if sameq: dup+=(('；' if dup else '')+'同问题KB：'+','.join(sameq[:20]))
        confirm=[]
        if unresolved: confirm.append('选图同优先级并列，人工选定并记录标准链接')
        if kb['unknown']: confirm.append('型号标准化')
        if kb['product_category_name'] in ('扫地机','洗地机','洗衣机','吸尘器'): confirm.append('平台字段缺失，确认图片平台适用范围')
        if old and not old_asset: confirm.append('原图不在当前资产清单，刷新核对实际下发链接')
        if len(old)>1: confirm.append('CSV原值含多链接，检查图片字段/答案嵌图/其他下发位置')
        if conclusion in ('保留旧图并登记缺口','待补图'): confirm.append('确定缺图范围/补图后再调整，勿误删仍适用旧图')
        processed.append({'kb':kb,'candidate':chosen,'cand':cand,'unresolved':unresolved,'old_asset':old_asset,'old_coverage':old_coverage,'partial':partial,'conclusion':conclusion,'reason':'；'.join(reasons),'match':match,'dup':dup,'confirm':'；'.join(confirm)})
    # Image pair universe, use unordered canonical pairs and deduplicate across links.
    pairassets=collections.defaultdict(list)
    for a in assets:
        for pair in itertools.combinations(sorted(a['models']),2): pairassets[(a['category'],frozenset(pair))].append(a)
    # Existing full KB comparison records: model sets exactly 2 and comparison-like question, plus exact-pair query.
    cmp_re=re.compile(r'对比|区别|比较|差异|哪款|哪个好|全系列|系列')
    existing_pairs=collections.defaultdict(list)
    for qid,x in current.items():
        if len(x['models'])==2 and cmp_re.search(x['question'] or ''):
            existing_pairs[(x['category'],frozenset(x['models']))].append(qid)
    for qid,r in retrieval.items():
        try: ms=set(json.loads(r['product_names_json'] or '[]'))
        except: ms=set()
        if len(ms)==2 and cmp_re.search(r['question'] or ''):
            existing_pairs[(r['product_category_name'],frozenset(ms))].append(qid)
    candidates=[]
    for (cat,pair),als in pairassets.items():
        # only one item per unordered model pair across categories, if duplicate categories flag confirmation
        current_ids=sorted(set(existing_pairs.get((cat,pair),[])))
        if current_ids: continue
        als.sort(key=lambda a:(-a['newest_order'],-a['count']))
        top=(als[0]['newest_order'],als[0]['count']); ties=[a for a in als if (a['newest_order'],a['count'])==top]
        sets={frozenset(a['models']) for a in ties}
        chosen=None; status='候选，范围待确认'
        if len(sets)==1:
            sel=[a for a in ties if a['selected']]
            if len(sel)==1: chosen=sel[0];status='可选图明确；答案文字待补；平台待确认'
            elif len({a['url'] for a in ties})==1: chosen=ties[0];status='可选图明确；答案文字待补；平台待确认'
            else:status='同集合多链接无既有标准选择，人工确认标准URL；答案文字待补'
        elif len(ties)==1: chosen=ties[0];status='可选图明确；答案文字待补；平台待确认'
        else:status='选图优先级并列且覆盖集合不同，人工确认；答案文字待补'
        p=sorted(pair,key=lambda m:(order.get(m,10**9),m)); links=sorted({a['url'] for a in als})
        candidates.append({'cat':cat,'pair':p,'assets':als,'chosen':chosen,'status':status,'links':links})
    # Deduplicate model pair globally if it appears in multiple categories; keep as separate review rows to prevent wrong category assumptions.
    # Gap list: KBs that have no full covering candidate, including partial old images; no-image/no-KB models checked against whole matrix + every asset.
    gaps=[]
    for p in processed:
        if p['candidate'] and not p['unresolved']: continue
        kb=p['kb']; assets_for=[a for a in assets if a['category']==kb['product_category_name'] and (kb['models'] & a['models'])]
        miss=set(kb['models'])-set.union(*(a['models'] for a in assets_for)) if assets_for else set(kb['models'])
        if p['unresolved']:
            gaps.append({'type':'存量KB选图待确认（非缺图）','kb':kb['question_wiki_id'],'models':ordered(kb['models'],order),'reason':'已有完整覆盖候选，但最高优先级候选无既有确认的唯一标准链接；不能据此登记缺图或猜选','scope':ordered(kb['models'],order),'status':'信息待确认'})
            continue
        reason='无单张图片完整覆盖全部关联型号'
        if p['partial']: reason='原图片为局部覆盖；当前无完整覆盖候选，不移除旧图'
        scope=ordered(miss,order) if miss else ordered(kb['models'],order)
        gaps.append({'type':'存量KB缺图','kb':kb['question_wiki_id'],'models':ordered(kb['models'],order),'reason':reason,'scope':scope,'status':'信息待确认（平台/实际引用尚未验证）'})
    all_kb_models=set().union(*(x['models'] for x in current.values())) if current else set()
    all_asset_models=set().union(*(a['models'] for a in assets)) if assets else set()
    for m in ordered(canonical-all_kb_models-all_asset_models,order):
        gaps.append({'type':'型号库型号无KB且无可用图','kb':'','models':[m],'reason':'当前完整product_matrix无该型号关联KB；247张图片覆盖中也未发现','scope':[m],'status':'信息待确认（型号有效性/业务范围待核实）'})
    # Current full KB model sets, plus CSV scope. Pair candidates excluded when exact pair already exists, not merely embedded in a multi-model KB.
    # Mother URL groups by identical model set+category; standard link only if unique URL or exactly one selected decision exists.
    bygroup=collections.defaultdict(list)
    for a in assets: bygroup[(a['category'],frozenset(a['models']))].append(a)
    mothers=[]
    for (cat,ms),als in sorted(bygroup.items(),key=lambda z:(z[0][0],-len(z[0][1]),tuple(sorted(z[0][1])))):
        als.sort(key=lambda a:(not a['selected'],-a['newest_order'],-a['count'],a['url']))
        selected=[a for a in als if a['selected']]
        std=selected[0] if len(selected)==1 else (als[0] if len(als)==1 else None)
        urls=[a['url'] for a in als]
        newest=max((a['newest_order'] for a in als),default=-1)
        latest=ordered(set().union(*(a['newest_models'] for a in als if a['newest_order']==newest)),order) if als else []
        mothers.append({'cat':cat,'models':ordered(ms,order),'count':len(ms),'std':std,'alts':[u for u in urls if std is None or u!=std['url']], 'urls':urls,'newest':latest,'newest_order':newest,'status':('已选定' if std and std['selected'] else ('单链接可作标准' if std else '多链接无已确认标准URL'))})
    # Per-link reference/suggestion rows.
    csv_refs=collections.defaultdict(list)
    for kb in kbs:
        for u in kb['images']: csv_refs[u].append(kb['question_wiki_id'])
    proposed=collections.defaultdict(list)
    for p in processed:
        if p['candidate'] and not p['unresolved']: proposed[p['candidate']['url']].append(p['kb']['question_wiki_id'])
    newpairs=collections.defaultdict(list)
    for c in candidates:
        if c['chosen']: newpairs[c['chosen']['url']].append('、'.join(c['pair']))
    # workbook
    wb=Workbook(); wb.remove(wb.active)
    sheets=[
      ('存量 KB 处理',['KB编号','问题','原关联型号（CSV原值）','标准目标型号（建议）','原图片链接（CSV原值）','主处理结论','目标母图标准链接（建议）','选择理由','关联机型核对（当前值）','重复KB／重复问题提示','执行状态','待确认项']),
      ('新增对比问题候选',['问题文案','品类','平台','关联型号（标准）','母图链接（标准建议）','选图依据','答案文字（留空）','候选状态／导入限制']),
      ('待补图清单',['对象类型','相关KB','相关型号','缺图原因','需补充的型号或合集范围','缺口状态']),
      ('母图标准 URL 对照',['品类','平台适用范围','标准链接','备选链接','覆盖型号','覆盖数量','所含最新型号','录入顺序','链接分组依据','KB最终选图说明']),
      ('图片链接维度汇总',['图片链接','覆盖型号','品类','实际引用KB（CSV原图引用）','引用KB数','建议保留KB','建议转入KB','可新增问题数量','可新增问题','建议角色／使用状态'])]
    srcnotes={
      '存量 KB 处理':f"输入：{CSV}（133条，原行一条）；当前库：{DB} product_matrix / kb_retrieval_index；规则：{RULE}；只读读取时间：{READ_AT}。原图列仅为CSV原值，当前DB未存KB实际图片配置，不能称为线上当前值。",
      '新增对比问题候选':f"图片覆盖来源：当前DB comparison_image_asset；型号顺序：matrix_column.sort_order；全库重复核对：product_matrix 与 kb_retrieval_index。平台字段缺失。按标准型号无序对生成；已有全库精确双型号比较KB排除。答案留空，导入程序若要求非空答案不可直接导入。",
      '待补图清单':f"范围由当前完整型号库、全库product_matrix和当前全部comparison_image_asset计算；不是仅按133条输入。选图并列另列为“选图待确认（非缺图）”。确认“无图无KB型号”须同时不在全库关联且不在任何可用图片覆盖中。", 
      '母图标准 URL 对照':f"分组口径：品类+标准型号集合完全相同（顺序不影响）；一行一组，不等同于某KB最终选图。标准URL仅在唯一链接/存在明确选定时填写；无已选decision时不猜标准链接。当前所有cell.active_asset_id为空。",
      '图片链接维度汇总':f"口径：当前247条asset URL一条一行；CSV原图引用明确标为输入快照，不是当前实际引用。建议保留/轉入基于可完整覆盖的存量KB目标建议；不得视为写库或线上执行。"
    }
    for name,headers in sheets:
        ws=wb.create_sheet(name); ws.append(headers); ws.freeze_panes='A2'; ws.auto_filter.ref=f"A1:{get_column_letter(len(headers))}1"
        for c in ws[1]:
            c.font=Font(name='Arial',bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='176B63');c.alignment=Alignment(vertical='center',wrap_text=True)
            c.comment=Comment(srcnotes[name],'OpenAI')
        ws.row_dimensions[1].height=36
    ws=wb['存量 KB 处理']
    for p in processed:
        kb=p['kb']; a=p['candidate'] if not p['unresolved'] else None
        old=kb['images']; target=a['url'] if a else ''
        status='仅分析建议；未写库/未导入'
        ws.append([kb['question_wiki_id'],kb['question'],kb['product_name'], '、'.join(kb['models_ordered']), '；'.join(old),p['conclusion'],target,p['reason'],p['match'],p['dup'],status,p['confirm']])
        for col in (5,7):
            cell=ws.cell(ws.max_row,col)
            urls=old if col==5 else ([target] if target else [])
            if len(urls)==1 and urls[0].startswith('http'):cell.hyperlink=urls[0];cell.style='Hyperlink'
        if kb['unknown'] or p['unresolved'] or p['partial'] or len(old)>1: ws.cell(ws.max_row,12).fill=PatternFill('solid',fgColor='FCE4D6')
    ws=wb['新增对比问题候选']
    for c in candidates:
        pair=c['pair']; q=f"{'和'.join(pair)}有什么区别？"; a=c['chosen']; link=a['url'] if a else ''
        newest=ordered(a['newest_models'],order) if a else []
        basis=(f"覆盖{len(pair)}个所问型号；图含最新型号{','.join(newest)}(录入序{a['newest_order']})，覆盖{a['count']}型号；同对候选{len(c['assets'])}张" if a else '最高优先级候选并列，待人工确认；不按ID猜选')
        ws.append([q,c['cat'],'未提供/待确认','、'.join(pair),link,basis,'',c['status']+'；平台适用待确认'])
        if link: ws.cell(ws.max_row,5).hyperlink=link;ws.cell(ws.max_row,5).style='Hyperlink'
    ws=wb['待补图清单']
    for g in gaps: ws.append([g['type'],g['kb'],'、'.join(g['models']),g['reason'],'、'.join(g['scope']),g['status']])
    ws=wb['母图标准 URL 对照']
    for g in mothers:
        std=g['std']; url=std['url'] if std else ''
        newest=g['newest']; ordervals=[order[m] for m in newest if m in order]
        ws.append([g['cat'],'未提供/需确认',url,'；'.join(g['alts']),'、'.join(g['models']),g['count'],'、'.join(newest),'、'.join(map(str,ordervals)),f"覆盖型号集合+品类；同集合链接数{len(g['urls'])}；{g['status']}", '按每个KB完整覆盖后比较图最新型号，再比较覆盖数量；无decision时不能把该分组链接直接视为KB最终选图'])
        if url: ws.cell(ws.max_row,3).hyperlink=url;ws.cell(ws.max_row,3).style='Hyperlink'
        for j,u in enumerate(g['alts'],start=1): pass
    ws=wb['图片链接维度汇总']
    for a in assets:
        refs=csv_refs.get(a['url'],[]); keep=proposed.get(a['url'],[]); adds=newpairs.get(a['url'],[])
        # current runtime has no actual KB image-ref table; list CSV refs, disclose this in cell value
        role='历史/现有图片资产；' + ('历史标记' if a['historical'] else '非历史标记')
        if keep: role+='；建议供完整覆盖KB使用'
        if not keep and not refs: role+='；当前无CSV引用/无推荐挂载，不能据此下线'
        if a['selected']: role+='；DB存在明确已选decision'
        ws.append([a['url'],'、'.join(ordered(a['models'],order)),a['category'],'、'.join(refs),len(refs),'、'.join(keep),'','%d'%len(adds),'；'.join(adds),role])
        ws.cell(ws.max_row,1).hyperlink=a['url'];ws.cell(ws.max_row,1).style='Hyperlink'
    # format widths, wrapping, borders, tab colors, row heights
    widths={
      '存量 KB 处理':[22,40,38,38,48,24,48,72,60,42,28,56],
      '新增对比问题候选':[38,14,18,36,48,72,22,60],
      '待补图清单':[28,28,48,60,52,40],
      '母图标准 URL 对照':[16,22,50,55,60,12,32,22,52,72],
      '图片链接维度汇总':[50,60,16,52,14,52,38,18,60,56]}
    thin=Side(style='hair',color='D9E2E1')
    for ws in wb.worksheets:
        for i,w in enumerate(widths[ws.title],1): ws.column_dimensions[get_column_letter(i)].width=w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment=Alignment(vertical='top',wrap_text=True)
                c.border=Border(bottom=thin)
                if c.hyperlink: c.font=Font(color='0563C1',underline='single')
            ws.row_dimensions[row[0].row].height=42
        ws.sheet_view.showGridLines=False
        ws.auto_filter.ref=f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
    wb.properties.title='产品对比图片执行核对（只读分析）'
    wb.properties.subject='按2026-10-23产品对比图录入规则生成；仅核对建议，不执行线上变更'
    wb.properties.description=f"读取时间 {READ_AT}; source DB {DB}; input CSV {CSV}; rule {RULE}"
    wb.save(OUT)
    # Reopen and verify sheet names/counts/input IDs and hyperlinks
    check=load_workbook(OUT,read_only=False,data_only=True)
    assert check.sheetnames==[x[0] for x in sheets]
    counts={s.title:s.max_row-1 for s in check.worksheets}
    assert counts['存量 KB 处理']==133
    ids=[check['存量 KB 处理'].cell(i,1).value for i in range(2,135)]
    assert ids==[r['question_wiki_id'] for r in rows]
    assert counts['图片链接维度汇总']==len(assets)
    # pair uniqueness and blank answers
    pairvals=[tuple(check['新增对比问题候选'].cell(i,4).value.split('、')) for i in range(2,check['新增对比问题候选'].max_row+1)]
    assert len(pairvals)==len(set(pairvals))
    assert all(check['新增对比问题候选'].cell(i,7).value in (None,'') for i in range(2,check['新增对比问题候选'].max_row+1))
    print(json.dumps({'path':OUT,'data_rows':counts,'csv_rows':len(rows),'assets':len(assets),'unique_asset_pairs':len(pairassets),'existing_pair_groups_excluded':sum(1 for k in pairassets if k in existing_pairs),'candidate_pairs':len(candidates),'gap_rows':len(gaps),'mother_groups':len(mothers),'current_kb_ids':len(current),'decision_rows':len(decisions),'active_selected_assets':len(selected_asset_ids),'read_at':READ_AT},ensure_ascii=False,indent=2))
    con.close()
if __name__=='__main__': main()
