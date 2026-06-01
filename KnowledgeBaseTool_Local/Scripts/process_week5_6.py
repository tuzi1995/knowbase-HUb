import pandas as pd
import re
import os
import sys

# 设置标准输出编码为 utf-8，避免中文乱码
sys.stdout.reconfigure(encoding='utf-8')

def clean_markdown(text):
    if not isinstance(text, str):
        return ""
        
    # 1. 移除代码块标记 (```...```) 保留内容
    text = re.sub(r'```[\s\S]*?```', lambda m: m.group(0).replace('```', ''), text)
    # 2. 移除行内代码标记 (`...`)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # 3. 移除链接 [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # 4. 移除图片 ![alt](url) -> alt
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', text)
    # 5. 移除 HTML 标签 <...>
    text = re.sub(r'<[^>]+>', '', text)
    # 6. 移除标题标记 (#, ##, ...)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    # 7. 移除列表标记 (-, *, +, 1.)
    text = re.sub(r'^[\*\-\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    # 8. 移除粗体/斜体 (**, *, __, _)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # 9. 移除引用标记 (>)
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
    
    return text

def count_chars(text, mode='simple'):
    """
    mode='simple': 仅中文汉字、数字、英文 (Q列逻辑)
    mode='full': 含标点符号 (R列逻辑)
    """
    if not text:
        return 0
        
    # 基础清洗：去掉空白字符
    text = re.sub(r'\s+', '', text)
    
    if mode == 'simple':
        # 匹配中文汉字、英文大小写、数字
        # \u4e00-\u9fff: CJK Unified Ideographs
        matches = re.findall(r'[\u4e00-\u9fffA-Za-z0-9]', text)
        return len(matches)
    elif mode == 'full':
        # 所有可见字符（不含空白，含标点）
        return len(text)
    return 0

def process_file(input_path):
    print(f"正在处理文件: {input_path}")
    if not os.path.exists(input_path):
        print(f"错误: 文件不存在 {input_path}")
        return

    try:
        df = pd.read_excel(input_path)
        
        # 检查 N 列是否存在 (索引 13)
        # 目标: O列 (索引 14) -> 仅汉字英文数字
        #       P列 (索引 15) -> 含标点
        
        if len(df.columns) <= 13:
             print(f"错误: 文件列数不足，无法找到 N 列 (需要至少 14 列)")
             return

        # N 列数据
        col_n_idx = 13
        col_o_idx = 14
        col_p_idx = 15
        
        print(f"N列名称: {df.columns[col_n_idx]}")
        
        # 确保 O, P 列存在，如果不存在则追加
        while len(df.columns) <= 15:
            new_col_name = f"Unnamed: {len(df.columns)}"
            df[new_col_name] = None
            
        print("正在计算字数...")
        
        # 清洗并计算
        def calculate_row(row):
            raw_text = row.iloc[col_n_idx]
            cleaned_text = clean_markdown(raw_text)
            
            count_simple = count_chars(cleaned_text, mode='simple')
            count_full = count_chars(cleaned_text, mode='full')
            
            return count_simple, count_full

        # 应用计算
        results = df.apply(calculate_row, axis=1)
        
        # 赋值回 DataFrame
        # 注意: 如果直接赋值 df.iloc[:, col_o_idx] = ... 可能会有 SettingWithCopyWarning
        # 这里使用列表赋值更稳妥
        df.iloc[:, col_o_idx] = [res[0] for res in results]
        df.iloc[:, col_p_idx] = [res[1] for res in results]
        
        # 重命名 O 和 P 列
        df.columns.values[col_o_idx] = "字数(汉字英文数字)"
        df.columns.values[col_p_idx] = "字数(含标点)"
        
        # 保存为新文件
        output_path = input_path.replace('.xlsx', '_processed.xlsx')
        print(f"正在保存到: {output_path}")
        df.to_excel(output_path, index=False)
        print("处理完成！\n")
        
        # 验证前 3 行
        print("验证前 3 行结果:")
        print(df.iloc[:3, [col_n_idx, col_o_idx, col_p_idx]])
        print("-" * 50)

    except Exception as e:
        print(f"处理失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    files = [
        r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Excel_Data\第五周.xlsx",
        r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Excel_Data\第六周.xlsx"
    ]
    
    for f in files:
        process_file(f)
