import pandas as pd
import numpy as np
import datetime
import re
import os
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

# 1. Config
INPUT_FILE = r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Excel_Data\KB1知识库-0206.xlsx"
OUTPUT_FILE = r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\KB1知识库50条样本QA对评分表.xlsx"
SHEET_NAME = "KB1-自动同步（勿动）"
TARGET_DATE = datetime.datetime(2026, 2, 1)

# 2. Load Data
print("Loading data...")
try:
    df = pd.read_excel(INPUT_FILE, sheet_name=SHEET_NAME)
except Exception as e:
    print(f"Error loading file: {e}")
    exit(1)

# Filter valid ID
df = df[df['question_wiki_id'].astype(str).str.startswith("ICWIKI20230724")].copy()

# 3. Categorize
def get_category(row):
    cat = str(row['product_category_name'])
    prod = str(row['product_name'])
    if "," in cat or "通用" in prod:
        return "多品类通用"
    if "扫地机" in cat: return "扫地机"
    if "洗地机" in cat: return "洗地机"
    if "洗衣机" in cat: return "洗衣机"
    if "吸尘器" in cat: return "吸尘器"
    return "多品类通用" # Default to General if unknown

df['category'] = df.apply(get_category, axis=1)

# 4. Sampling
samples = []
categories = ["扫地机", "洗地机", "洗衣机", "吸尘器", "多品类通用"]
sampled_indices = set()

# First, ensure 5 from each
for cat in categories:
    cat_df = df[df['category'] == cat]
    if len(cat_df) >= 5:
        sample = cat_df.sample(n=5, random_state=42) # fixed seed for reproducibility
        samples.append(sample)
        sampled_indices.update(sample.index)
    else:
        # Fallback if not enough data
        samples.append(cat_df)
        sampled_indices.update(cat_df.index)

# Fill the rest to reach 50
current_count = sum(len(s) for s in samples)
needed = 50 - current_count
if needed > 0:
    remaining_df = df[~df.index.isin(sampled_indices)]
    if len(remaining_df) >= needed:
        extra_sample = remaining_df.sample(n=needed, random_state=42)
        samples.append(extra_sample)
    else:
        samples.append(remaining_df)

final_sample = pd.concat(samples).sample(frac=1, random_state=42).reset_index(drop=True) # Shuffle
final_sample = final_sample.iloc[:50] # Ensure exactly 50

# 5. Scoring Logic
results = []

for idx, row in final_sample.iterrows():
    qid = row['question_wiki_id']
    q_content = str(row['question'])
    prod = str(row['product_name'])
    ans = str(row['answer'])
    update_time = pd.to_datetime(row['update_time'])
    
    reasons = []
    
    # --- 1. Compliance (40) ---
    score_comp = 40
    # Simple check: Empty answer?
    if not ans or ans.lower() == 'nan' or len(ans) < 5:
        score_comp -= 20
        reasons.append("核心信息缺失")
    else:
        pass
    
    # --- 2. Timeliness (20) ---
    score_time = 0
    if pd.isnull(update_time):
        diff_months = 999
        time_str = "无日期"
    else:
        # Calculate month difference: (2026*12 + 2) - (Year*12 + Month)
        diff_months = (2026 * 12 + 2) - (update_time.year * 12 + update_time.month)
        if diff_months < 0: diff_months = 0 # Future dates?
    
        if diff_months <= 6:
            score_time = 20
            time_str = "6个月内"
        elif diff_months <= 12:
            score_time = 15
            time_str = "6-12个月"
        elif diff_months <= 24:
            score_time = 10
            time_str = "1-2年"
        else:
            score_time = 5
            time_str = "2年以上"
    
    reasons.append(f"时效：距今{diff_months}个月({time_str})")

    # --- 3. Value (20) ---
    score_val = 20
    if "咨询客服" in ans or "正常现象" in ans:
         if len(ans) < 50: # Only penalize if short
            score_val -= 10
            reasons.append("表述空洞")
    if len(ans) < 20 and score_val == 20: # Don't double penalize
        score_val -= 5
        reasons.append("内容过简")
        
    # --- 4. Non-redundancy (10) ---
    score_red = 10
    # Check if this question exists elsewhere in the FULL df
    dup_count = len(df[df['question'] == q_content])
    if dup_count > 1:
        # It exists elsewhere.
        score_red = 0
        reasons.append("存在完全重复QA")
    
    # --- 5. Norms (10) ---
    score_norm = 10
    # Check for mess
    if re.search(r'[^\x00-\xff\u4e00-\u9fa5\u3000-\u303f\uff00-\uffef\n\r\t]', q_content + ans):
         score_norm -= 1
         reasons.append("存在乱码/特殊字符")
    
    total = score_comp + score_time + score_val + score_red + score_norm
    
    suggestion = "直接保留"
    if total < 60:
        suggestion = "建议删除"
    elif total < 80:
        suggestion = "优化后保留"
        
    # Format Reasons
    reason_str = "；".join(reasons)
    if not reason_str: reason_str = "符合标准"

    results.append({
        "问题ID": qid,
        "问题内容": q_content,
        "产品": prod,
        "合规准确性（40）": score_comp,
        "时效性（20）": score_time,
        "实际使用价值（20）": score_val,
        "非冗余性（10）": score_red,
        "基础规范性（10）": score_norm,
        "总分": total,
        "处理建议": suggestion,
        "评分原因": reason_str
    })

result_df = pd.DataFrame(results)

# 6. Analysis Sheet
avg_scores = result_df[["合规准确性（40）", "时效性（20）", "实际使用价值（20）", "非冗余性（10）", "基础规范性（10）", "总分"]].mean()
suggestion_counts = result_df["处理建议"].value_counts(normalize=True).mul(100).round(1).astype(str) + '%'

analysis_data = []
for idx, val in avg_scores.items():
    analysis_data.append({"项目": f"平均-{idx}", "数值": round(val, 2)})

for idx, val in suggestion_counts.items():
    analysis_data.append({"项目": f"占比-{idx}", "数值": val})

analysis_df = pd.DataFrame(analysis_data)

# 7. Rules Sheet
rules_text = [
    ["维度", "分值", "说明"],
    ["合规准确性", "40", "答案无事实错误、与对应产品特性/参数一致"],
    ["时效性", "20", "更新时间距2026年2月：≤6月(20), 6-12月(15), 1-2年(10), >2年(5)"],
    ["实际使用价值", "20", "有具体操作步骤、解决方案"],
    ["非冗余性", "10", "无重复QA对"],
    ["基础规范性", "10", "无错别字、标点正确"],
]
rules_df = pd.DataFrame(rules_text[1:], columns=rules_text[0])

# 8. Write Excel
with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
    result_df.to_excel(writer, sheet_name='QA对评分结果', index=False)
    analysis_df.to_excel(writer, sheet_name='评分统计分析', index=False)
    rules_df.to_excel(writer, sheet_name='评分标准说明', index=False)
    
    # Auto-adjust columns width
    for sheet_name in writer.sheets:
        worksheet = writer.sheets[sheet_name]
        for column in worksheet.columns:
            max_length = 0
            column = [cell for cell in column]
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = (max_length + 2)
            if adjusted_width > 50: adjusted_width = 50 # Cap width
            worksheet.column_dimensions[get_column_letter(column[0].column)].width = adjusted_width

print(f"File created: {OUTPUT_FILE}")
