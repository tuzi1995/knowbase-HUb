import pandas as pd
import json
import os
import time
import datetime
import csv
import argparse
import sys
import requests

# ================= 配置区 =================
# 默认配置
DEFAULT_INPUT_FILE = r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Excel_Data\KB1知识库-0206.xlsx"
DEFAULT_OUTPUT_DIR = r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Output"
SHEET_NAME = "KB1-自动同步（勿动）"

API_KEY = os.getenv("MOONSHOT_API_KEY") or os.getenv("LLM_API_KEY") or ""
BASE_URL = "https://api.moonshot.cn/v1"
MODEL_NAME = "kimi-k2-turbo-preview"

# ================= 产品型号定义 (用户补充) =================
PRODUCT_CATALOG_TEXT = """
### 附录：官方产品型号列表
(供评分参考，用于辅助判断产品名称准确性及分类)

1. **扫地机**：P5, T6, T7, T7 Pro, T7S, T7S Plus, T8, T8 Plus, G10, G10 Plus, G10S, G10S Auto, G10S Pro, G10S Pure, G20, G20S, P10, P10 Pro, P10S, P10S Pure, P10S Pro 系列, P10S Pro 系列超薄嵌入式, P20 Pro, G20S Ultra, V20, 石头星耀Pro, G30, P20 Plus, P20 Ultra, G30 Space探索版, G30 U, P20, P20极光, P20 Ultra Plus, P20活水版, P20极光 增强版, G30曜石, G30S Pro, P20 Ultra活水版
2. **洗地机**：U10, A10, A10 Plus, A10 Ultra, A10 UltraE, A20, A20 Air, A20 Pro, A30 Pro, A30, A30 CE, A30 ProCE, A30 Pro Steam, A30 Lite, A30 SE, A30 Muse, A30 U, A30 Combo, A30 Pro Turbo, A30 Pure, A30 Pro Combo, A30 Pro Ultra, 拓界 Mist, 拓界 Aura, A30 Pro Steam 5合1版, 拓界 Pro, A30 CE 畅享版, A30 CE 悦享版, A30 Pro Steam 智享版, A30 Pro CE 悦享版, A30 2.0
3. **吸尘器**：H5, H6, H7, H50 Ultra, H50, H50 Pro
4. **洗衣机**：H1, H1 Air, H1 Neo, M1, M1 Pure, 洗烘一体机 Z1, 洗烘一体机 Z1 Pro, Q1, Q1M, 洗烘一体机 Z1 Plus, 洗衣机 Z1, M1S, M1S Pure, 洗衣机 Z1 Max, 洗衣机 Z1 Max 银盾版, 洗衣机 Z1 Max 智控版, 热泵干衣机 Z1 Max, 分子筛干衣机 Z1 Max, 套装 Z1 Max, Z1 Max Pro, Z1 Max Ultra, Q1 Hello Kitty
"""

# ================= Prompt 设计 (V7 - 精细化指代不明判定) =================
SYSTEM_PROMPT = """你是一个专家级的企业知识库审计员。你的目标是确保QA对（问题与答案）能够直接用于智能客服检索和用户自助服务。

请按照以下步骤进行思维链（Chain-of-Thought）分析，并输出 JSON 结果：

### 评分标准（总分 100 分）

1. **问题质量 (10分)**
   - 评估：问题是否清晰、自包含、关键词明确。
   - **特殊豁免**：对于**指向性明确**的故障/功能描述（如“烘干时间跳动”、“无法建图”），即使省略主语，视为关键词明确，**不扣分**。
   - **不予豁免**：
     1. **指向性模糊**的通用症状（如“声音大”、“有异响”、“不动了”），若未指明具体部件或场景，判为**指代不明**，**扣10分**。
     2. **纯名词/参数堆砌**：对于非故障类的参数/属性询问（如“滚筒拖布贴边距离”、“水箱容量”），若无疑问词（如“是多少”、“多大”）或动词，视为**语意不完整**，**扣5分**。
   - 扣分：
     - **指代不明**（扣10分）：使用“它、这个”等悬空指代且无具体场景。
     - **语意不完整/关键词堆砌**（扣5分）：仅有名词短语且非故障描述。
     - 过于宽泛（扣5分）：如“使用说明”、“介绍一下”。

2. **答案合规与准确性 (30分)**
   - 评估：事实是否准确，是否包含敏感承诺，语气是否亲切专业。
   - 扣分：
     - **事实错误**（扣30分）：答案事实有误。若存在机型重叠，且关键参数与其他QA冲突（如尺寸数值不一致），视为事实错误/误导用户。
     - **敏感承诺/违规**（扣20分）：包含绝对化保证（如“100%修好”、“永远不坏”）、违规售后（如“无条件退款”超规则、私下补偿）、隐私引导、违法或低俗内容。
     - 语气生硬/推诿（扣10分）。

3. **时效性 (20分)**
   - **规则**（直接使用元数据中的 `距基准月数` 进行判定）：
     - **≤ 6 个月**：得 20 分
     - **6 < 月数 ≤ 12**：得 15 分
     - **12 < 月数 ≤ 24**：得 10 分
     - **24 < 月数**：得 5 分
     - **内容过期**：如果答案中包含的具体活动/时间已过（如“活动截止2025.12”），得 0 分。

4. **实际解决力 (30分)**
   - **故障/操作设置类**：必须包含**明确操作动作**（如点击、设置、查询、复位、清洁路径等），否则视为无步骤，扣15-20分。
   - **确认/参数类**（如“是否支持”、“尺寸/功率”、“有无功能”）：只需给出准确结论/数值即可，**不强制要求操作步骤**，不因此扣分。
   - 扣分：步骤逻辑混乱（扣10分）。

5. **非冗余与相关性 (10分)**
   - **核心规则**：
     1. **机型覆盖重叠**：如果`机型重叠计数` > 0（判定标准：覆盖机型完全一致或完全包含），说明存在冗余，**扣10分**。
     2. **内容无效冗余**：如果答案答非所问、与问题意图不符、或仅包含无关废话，视为无效信息，**扣10分**。
     3. **唯一且相关**：机型无重叠且内容紧扣问题，得10分。

""" + PRODUCT_CATALOG_TEXT + """
### 输出格式（JSON）
必须严格遵守此顺序，先分析后打分：
{
    "分析过程": "请在此处简要分析各维度的优缺点...",
    "维度得分": {
        "问题质量": int,
        "答案合规与准确性": int,
        "时效性": int,
        "实际解决力": int,
        "非冗余与相关性": int
    },
    "总分": int,
    "处理建议": "直接保留" | "优化后保留" | "建议删除"
}
"""

USER_PROMPT_TEMPLATE = """
请对以下QA对进行评分：

【元数据】
- 问题ID：{qid}
- 产品：{product}
- 更新时间：{update_time} (当前基准日期: 2026-02-01)
- 距基准月数：{months_diff} 个月 (请直接使用此数值判断时效性)
- 机型重叠计数：{overlap_count} (如果>0，说明库中存在针对相同机型的相同问题，属冗余)

【内容】
- 问题：{question}
- 答案：{answer}

请返回 JSON 结果。
"""

# ================= 核心功能函数 =================

def calculate_product_overlap(df):
    """
    计算机型重叠冗余。
    规则 (V4)：对于具有相同 'question' 的记录，检查 'product_name' 是否构成包含关系。
    即：SetA == SetB 或 SetA ⊂ SetB 或 SetB ⊂ SetA 时，判定为重叠。
    仅部分交集（如 {A,B} 与 {B,C}）不算重叠。
    """
    # 预处理：将 product_name 拆分为集合，处理空值
    df['product_set'] = df['product_name'].fillna('').apply(lambda x: set([p.strip() for p in str(x).split(',') if p.strip()]))
    
    # 结果字典：index -> overlap_count
    overlap_counts = {}
    
    # 按问题分组处理
    grouped = df.groupby('question')
    
    for question, group in grouped:
        indices = group.index.tolist()
        n = len(indices)
        
        # 如果只有一条记录，无冗余
        if n < 2:
            for idx in indices:
                overlap_counts[idx] = 0
            continue
            
        # 两两比较
        for i in range(n):
            current_idx = indices[i]
            current_products = group.loc[current_idx, 'product_set']
            overlap_found = 0
            
            for j in range(n):
                if i == j:
                    continue
                other_idx = indices[j]
                other_products = group.loc[other_idx, 'product_set']
                
                # V4 规则：覆盖机型完全一致 / 完全包含 才算重叠
                # 即 A 是 B 的子集 或 B 是 A 的子集 (含相等情况)
                if current_products.issubset(other_products) or other_products.issubset(current_products):
                    overlap_found += 1
            
            overlap_counts[current_idx] = overlap_found
            
    return overlap_counts

def calculate_months_diff(update_time_str, baseline_str="2026-02-01"):
    """
    计算更新时间距离基准日期的月数差（向下取整）。
    例如：
    2025-04-28 vs 2026-02-01
    (2026-2025)*12 + (2-4) = 12 - 2 = 10 个月
    """
    try:
        if not update_time_str or update_time_str == "未知":
            return 999 # 视为极老
            
        # 尝试解析
        update_date = pd.to_datetime(update_time_str)
        baseline_date = pd.to_datetime(baseline_str)
        
        diff = (baseline_date.year - update_date.year) * 12 + (baseline_date.month - update_date.month)
        
        # 如果 update_date 的日 > baseline_date 的日，可能还需要减1？
        # 比如 2026-01-30 vs 2026-02-01，差1个月
        # 2026-01-01 vs 2026-02-01，差1个月
        # 简单起见，只按年月差计算即可，业务上通常足够
        
        return max(0, diff) # 避免未来时间出现负数
    except:
        return 999

def _chat_completions(api_key, base_url, model, messages, temperature=0.1, response_format=None, timeout=60):
    base = (base_url or "").strip().rstrip("/")
    base_v1 = base if base.endswith("/v1") else (base + "/v1")
    url = base_v1 + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    return (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()


def _parse_urls_value(val):
    if val is None:
        return []
    if isinstance(val, list):
        out = []
        for x in val:
            if x is None:
                continue
            s = str(x).strip()
            if s:
                out.append(s)
        return out
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return []
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return _parse_urls_value(parsed)
        if isinstance(parsed, str):
            return _parse_urls_value([parsed])
    except Exception:
        pass
    parts = re.split(r"[,，\n\r]+", s)
    return [p.strip() for p in parts if p and p.strip()]


def _aggregate_urls_from_row(row):
    urls = []
    for k in ("image_urls", "video_urls", "file_urls"):
        if k in row:
            urls.extend(_parse_urls_value(row.get(k)))
    link_url = row.get("link_url") if isinstance(row, dict) else None
    if pd.notnull(link_url) and str(link_url).strip():
        urls.append(str(link_url).strip())
    if not urls:
        urls.extend(_parse_urls_value(row.get("urls", "")))
    dedup = []
    seen = set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            dedup.append(u)
    return "\n".join(dedup)


def get_llm_score(row, api_key, base_url, model_name):
    """
    调用 LLM 进行评分，包含重试机制。
    """
    max_retries = 5
    retry_delay = 2 # 初始等待时间
    
    for attempt in range(max_retries + 1):
        try:
            update_time = row['update_time'] if 'update_time' in row else "未知"
            update_str = str(update_time) if pd.notnull(update_time) else "未知"
            
            # 计算月数差
            months_diff = calculate_months_diff(update_str)
            
            # 使用计算出的机型重叠计数
            overlap_count = row.get('overlap_count', 0)

            user_content = USER_PROMPT_TEMPLATE.format(
                qid=row['question_wiki_id'],
                product=row['product_name'],
                update_time=update_str,
                months_diff=months_diff,
                overlap_count=overlap_count,
                question=row['question'],
                answer=row['answer']
            )

            content = _chat_completions(
                api_key=api_key,
                base_url=base_url,
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                timeout=90,
            )
            # 清理可能的 markdown 标记
            content = content.replace("```json", "").replace("```", "").strip()
            
            result = json.loads(content)
            
            # 计算多媒体加分 (独立列，不计入总分)
            urls = _aggregate_urls_from_row(row)
            media_bonus = 0
            if pd.notnull(urls) and str(urls).strip():
                media_bonus = 3

            # 扁平化结果
            flat_result = {
                "问题ID": row['question_wiki_id'], # 确保ID在最前
                "问题内容": row['question'],
                "answer": row.get('answer', ''),
                "产品": row['product_name'],
                "update_time": update_str,
                "urls": urls,
                "分析过程": result.get("分析过程", ""),
                "总分": result.get("总分", 0),
                "多媒体加分": media_bonus,
                "处理建议": result.get("处理建议", "需人工复核")
            }
            
            # 提取维度得分
            scores = result.get("维度得分", {})
            flat_result["问题质量（10）"] = scores.get("问题质量", 0)
            flat_result["答案合规与准确性（30）"] = scores.get("答案合规与准确性", 0)
            flat_result["时效性（20）"] = scores.get("时效性", 0)
            flat_result["实际解决力（30）"] = scores.get("实际解决力", 0)
            flat_result["非冗余与相关性（10）"] = scores.get("非冗余与相关性", 0)
            
            return flat_result

        except Exception as e:
            error_msg = str(e)
            if attempt < max_retries:
                # 特殊处理 429 Rate Limit
                if "429" in error_msg or "rate_limit" in error_msg.lower():
                    wait_time = 30  # 遇到限流强制等待 30 秒 (更加保守)
                    print(f"  [Warning] 触发速率限制 (429)，暂停 {wait_time} 秒后重试...", end="", flush=True)
                    for _ in range(wait_time):
                        time.sleep(1)
                        print(".", end="", flush=True)
                    print(" 重试", flush=True)
                else:
                    wait_time = retry_delay * (2 ** attempt) # 指数退避
                    print(f"  [Warning] 调用失败 ({error_msg})，{wait_time}秒后重试...")
                
                time.sleep(wait_time)
            else:
                print(f"  [Error] 最终调用失败 ID: {row['question_wiki_id']} - {error_msg}")
                # 返回默认失败结构
                return {
                    "问题ID": row['question_wiki_id'],
                    "问题内容": row['question'],
                    "answer": row.get('answer', ''),
                    "product_name": row['product_name'],
                    "update_time": str(row.get('update_time', '未知')),
                    "urls": _aggregate_urls_from_row(row),
                    "分析过程": f"API调用失败: {error_msg}",
                    "总分": 0,
                    "多媒体加分": 0,
                    "处理建议": "人工复核",
                    "问题质量（10）": 0, "答案合规与准确性（30）": 0, "时效性（20）": 0, 
                    "实际解决力（30）": 0, "非冗余与相关性（10）": 0
                }

def generate_final_excel(csv_path, xlsx_path):
    """
    将 CSV 缓存转换为最终的格式化 Excel
    """
    print("正在生成最终 Excel 报表...")
    try:
        # 尝试标准读取
        try:
            df_result = pd.read_csv(csv_path, encoding='utf-8-sig', on_bad_lines='skip')
        except UnicodeDecodeError:
            print("CSV 文件编码异常，尝试使用 errors='replace' 读取...")
            with open(csv_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                df_result = pd.read_csv(f, on_bad_lines='skip')

        # 去重：保留最后一次出现的结果（假设后面的重试是修正后的）
        if '问题ID' in df_result.columns:
            original_len = len(df_result)
            df_result.drop_duplicates(subset=['问题ID'], keep='last', inplace=True)
            if len(df_result) < original_len:
                print(f"已去除重复数据: {original_len - len(df_result)} 条")
        
        # 统计分析
        score_cols = ["问题质量（10）", "答案合规与准确性（30）", "时效性（20）", "实际解决力（30）", "非冗余与相关性（10）", "多媒体加分", "总分"]
        
        # 确保列存在
        for col in score_cols:
            if col not in df_result.columns:
                 # 兼容旧列名（如果存在）
                if "非冗余性（10）" in df_result.columns and col == "非冗余与相关性（10）":
                     df_result.rename(columns={"非冗余性（10）": "非冗余与相关性（10）"}, inplace=True)
                else:
                    print(f"警告：缺失列 {col}")

        # 转换为数值类型
        for col in score_cols:
            if col in df_result.columns:
                df_result[col] = pd.to_numeric(df_result[col], errors='coerce').fillna(0)

        # 3. 计算统计信息
        avg_scores = df_result[score_cols].mean()
        suggestion_counts = df_result["处理建议"].value_counts(normalize=True).mul(100).round(1).astype(str) + '%'
        
        analysis_data = []
        for idx, val in avg_scores.items():
            analysis_data.append({"项目": f"平均-{idx}", "数值": round(val, 2)})
        for idx, val in suggestion_counts.items():
            analysis_data.append({"项目": f"占比-{idx}", "数值": val})
        analysis_df = pd.DataFrame(analysis_data)
        
        # 评分标准说明 (V3)
        rules_data = [
            ["维度", "分值", "评分细则"],
            ["问题质量", "10", "清晰、自包含(10); 指代不明扣10; 宽泛扣5"],
            ["答案合规与准确性", "30", "准确亲切(30); 事实错误扣30; 违规/敏感词扣20; 语气生硬扣10"],
            ["时效性", "20", "≤6个月(20); 6-12个月(15); 1-2年(10); >2年(5); 过期(0)"],
            ["实际解决力", "30", "有步骤结论(30); 无方案扣15-20; 步骤混乱扣10"],
            ["非冗余与相关性", "10", "独特且相关(10); 机型重叠冗余扣10; 答非所问/无效内容扣10"],
            ["多媒体加分", "3", "包含图片/视频+3分 (不计入总分)"]
        ]
        rules_df = pd.DataFrame(rules_data)

        # 写入 Excel
        with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
            df_result.to_excel(writer, sheet_name='QA对评分结果', index=False)
            analysis_df.to_excel(writer, sheet_name='评分统计分析', index=False)
            rules_df.to_excel(writer, sheet_name='评分标准说明', index=False, header=False)
            
            # 设置列宽
            worksheet = writer.sheets['QA对评分结果']
            worksheet.column_dimensions['B'].width = 40 # 问题内容
            worksheet.column_dimensions['K'].width = 50 # 分析过程
            
        print(f"Excel 生成成功：{xlsx_path}")
        
    except Exception as e:
        print(f"生成 Excel 失败: {e}")
        import traceback
        traceback.print_exc()

# ================= 主流程 =================

def main():
    parser = argparse.ArgumentParser(description="KB1 知识库 LLM 自动评分工具")
    parser.add_argument("--input", type=str, default=DEFAULT_INPUT_FILE, help="输入的Excel文件路径")
    parser.add_argument("--limit", type=int, default=0, help="测试条数 (0 表示全量运行)")
    parser.add_argument("--output_dir", type=str, default=DEFAULT_OUTPUT_DIR, help="结果输出目录")
    
    args = parser.parse_args()
    
    input_file = args.input
    output_dir = args.output_dir
    limit_count = args.limit
    
    if not os.path.exists(input_file):
        print(f"错误: 输入文件不存在 -> {input_file}")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 生成动态文件名
    file_basename = os.path.basename(input_file).split('.')[0]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_str = f"抽样{limit_count}条" if limit_count > 0 else "全量"
    
    output_xlsx = os.path.join(output_dir, f"{file_basename}_{mode_str}_评分报告_{timestamp}.xlsx")
    cache_csv = os.path.join(output_dir, f"{file_basename}_{mode_str}_评分缓存.csv")
    
    print(f"=== 开始执行 KB1 知识库评分 ({mode_str}模式) ===")
    print(f"输入: {input_file}")
    print(f"输出: {output_xlsx}")
    print(f"缓存: {cache_csv}")
    
    # 1. 读取原始数据
    try:
        df = pd.read_excel(input_file, sheet_name=SHEET_NAME)
    except Exception as e:
        print(f"读取 Excel 失败: {e}")
        return

    # 2. 数据预处理
    target_df = df[df['question_wiki_id'].notna()].copy()
    
    # === 计算精确的机型重叠计数 ===
    print("正在计算全量数据的机型重叠冗余...")
    overlap_counts = calculate_product_overlap(target_df)
    target_df['overlap_count'] = target_df.index.map(overlap_counts)
    
    # === 抽样逻辑 ===
    if limit_count > 0:
        print(f"全量有效数据: {len(target_df)} 条，正在随机抽取 {limit_count} 条进行测试...")
        if limit_count < len(target_df):
            target_df = target_df.sample(n=limit_count, random_state=42)
        else:
            print(f"警告: 请求样本数 {limit_count} 大于总数据量，将使用全量数据。")
    else:
        print(f"全量模式: 将处理所有 {len(target_df)} 条数据。")
    
    print(f"待处理数据: {len(target_df)} 条")

    # 3. 断点续传检查
    processed_ids = set()
    if os.path.exists(cache_csv):
        try:
            # 读取缓存中的ID
            try:
                cache_df = pd.read_csv(cache_csv, encoding='utf-8-sig', on_bad_lines='skip')
            except UnicodeDecodeError:
                print("缓存文件编码异常，尝试使用 errors='replace' 读取...")
                with open(cache_csv, 'r', encoding='utf-8-sig', errors='replace') as f:
                    cache_df = pd.read_csv(f, on_bad_lines='skip')
            
            if '问题ID' in cache_df.columns:
                def is_success(row):
                    try:
                        score = float(row.get('总分', 0))
                        analysis = str(row.get('分析过程', ''))
                        if score == 0 and "API调用失败" in analysis:
                            return False
                        return True
                    except:
                        return False

                success_ids = []
                for _, row in cache_df.iterrows():
                    if is_success(row):
                        success_ids.append(str(row['问题ID']))
                
                processed_ids = set(success_ids)
            print(f"检测到中间缓存文件，已处理有效数据: {len(processed_ids)} 条")
        except Exception as e:
            print(f"读取缓存文件出错，将重新开始: {e}")

    # 排除已处理的数据
    remaining_df = target_df[~target_df['question_wiki_id'].astype(str).isin(processed_ids)]
    print(f"剩余待处理数据: {len(remaining_df)} 条")

    if len(remaining_df) == 0:
        print("所有数据已处理完毕，直接生成最终报表。")
        generate_final_excel(cache_csv, output_xlsx)
        
        # 清理中间缓存
        if os.path.exists(cache_csv) and os.path.exists(output_xlsx):
            try:
                os.remove(cache_csv)
                print(f"中间缓存文件已清理: {cache_csv}")
            except Exception as e:
                print(f"清理缓存文件失败: {e}")
        return

    if not API_KEY.strip():
        print("错误: 未设置 API_KEY。请设置环境变量 MOONSHOT_API_KEY 或 LLM_API_KEY")
        return

    # 5. 准备写入 CSV
    headers = ["问题ID", "问题内容", "answer", "产品", "update_time", "urls",
               "问题质量（10）", "答案合规与准确性（30）", "时效性（20）", 
               "实际解决力（30）", "非冗余与相关性（10）", "多媒体加分", "总分", "处理建议", "分析过程"]

    file_exists = os.path.exists(cache_csv) and os.path.getsize(cache_csv) > 0
    
    # 6. 处理循环
    print("开始进行 API 评分调用 (单线程模式，每条间隔 4.0s)...")
    
    processed_count = 0
    total_remaining = len(remaining_df)

    with open(cache_csv, mode='a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            writer.writeheader()
            f.flush()
            
        for index, row in remaining_df.iterrows():
            processed_count += 1
            qid = row['question_wiki_id']
            print(f"[{processed_count}/{total_remaining}] 正在处理: {qid} ...", end="", flush=True)
            
            start_time = time.time()
            try:
                result = get_llm_score(row, API_KEY, BASE_URL, MODEL_NAME)
                
                writer.writerow(result)
                f.flush() # 立即写入磁盘
                
                elapsed = time.time() - start_time
                print(f" 完成 (耗时{elapsed:.2f}s)", flush=True)
                
                # 速率限制保护 (API限制 20 RPM -> 4s/req = 15 RPM)
                time.sleep(4.0)
            except Exception as e:
                print(f"\n[CRITICAL ERROR] 处理 {qid} 时发生异常: {e}", flush=True)
                # 记录错误但不中断循环 (可选择写入错误记录)
                time.sleep(5)

    print("所有数据处理完成。")
    generate_final_excel(cache_csv, output_xlsx)
    
    # 清理中间缓存
    if os.path.exists(cache_csv) and os.path.exists(output_xlsx):
        try:
            os.remove(cache_csv)
            print(f"中间缓存文件已清理: {cache_csv}")
        except Exception as e:
            print(f"清理缓存文件失败: {e}")

if __name__ == "__main__":
    main()
