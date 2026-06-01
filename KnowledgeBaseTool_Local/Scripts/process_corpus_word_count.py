import pandas as pd
import os
import re

# 文件路径
input_file = r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Excel_Data\2026智能助理-语料库-第六周.xlsx"
output_file = r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Excel_Data\2026智能助理-语料库-第六周_processed.xlsx"

def process_word_count():
    print(f"正在读取文件: {input_file}")
    
    # 读取 Excel 文件
    # 默认读取第一行作为 header
    df = pd.read_excel(input_file)
    
    # 检查列数是否足够
    if len(df.columns) < 17:
        print(f"错误: 文件列数不足。当前只有 {len(df.columns)} 列，需要至少 17 列 (Q列)。")
        return

    # 获取 P 列和 Q 列的名称（索引从 0 开始，P=15, Q=16）
    col_p_name = df.columns[15]
    col_q_name = df.columns[16]
    
    print(f"P列 (索引15) 名称: {col_p_name}")
    print(f"Q列 (索引16) 名称: {col_q_name}")
    
    print("正在计算字数...")
    def md_to_text(s):
        t = s
        t = re.sub(r"```([\s\S]*?)```", r"\1", t)
        t = re.sub(r"`([^`]*)`", r"\1", t)
        t = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", t)
        t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
        t = re.sub(r"<[^>]+>", "", t)
        t = re.sub(r"^[>#\-\*\+]+\s*", "", t, flags=re.MULTILINE)
        t = re.sub(r"^\d+\.\s*", "", t, flags=re.MULTILINE)
        t = re.sub(r"[*_~#]+", "", t)
        t = re.sub(r"\\([*_~#`>\-])", r"\1", t)
        return t
    def count_hanzi_eng_num(val):
        if pd.isna(val):
            return 0
        s = md_to_text(str(val))
        chars = re.findall(r"[\u3400-\u4DBF\u4E00-\u9FFFA-Za-z0-9]", s)
        return len(chars)
    def count_all_no_space(val):
        if pd.isna(val):
            return 0
        s = md_to_text(str(val))
        s = re.sub(r"\\s+", "", s)
        return len(s)

    # 更新 Q 列与 R 列
    df.iloc[:, 16] = df.iloc[:, 15].apply(count_hanzi_eng_num)
    if len(df.columns) < 18:
        df.insert(17, "R_count", 0)
    df.iloc[:, 17] = df.iloc[:, 15].apply(count_all_no_space)
    
    # 保存结果
    print(f"正在保存结果到: {output_file}")
    df.to_excel(output_file, index=False)
    print("处理完成！")

if __name__ == "__main__":
    if os.path.exists(input_file):
        process_word_count()
    else:
        print(f"文件不存在: {input_file}")
