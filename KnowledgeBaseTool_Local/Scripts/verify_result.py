import pandas as pd
import os

log_file = r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Logs\verify_log.txt"
file_path = r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Excel_Data\2026智能助理-语料库-第六周_processed.xlsx"

with open(log_file, "w", encoding="utf-8") as f:
    try:
        df = pd.read_excel(file_path, nrows=5)
        f.write("验证结果 (前5行):\n")
        f.write(f"P列名: {df.columns[15]}\n")
        f.write(f"Q列名: {df.columns[16]}\n")
        f.write(f"R列名: {df.columns[17]}\n")
        f.write("-" * 30 + "\n")
        for i in range(len(df)):
            p_val = df.iloc[i, 15]
            q_val = df.iloc[i, 16]
            r_val = df.iloc[i, 17]
            f.write(f"行 {i+1}: P='{str(p_val)[:10]}...' | Q={q_val} | R={r_val}\n")
    except Exception as e:
        f.write(f"验证失败: {e}")
