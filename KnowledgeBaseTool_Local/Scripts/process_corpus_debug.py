import pandas as pd
import os
import sys

log_file = r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Logs\process_log.txt"
os.makedirs(os.path.dirname(log_file), exist_ok=True)

with open(log_file, "w", encoding="utf-8") as f:
    f.write("开始执行脚本...\n")
    try:
        input_file = r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Excel_Data\2026智能助理-语料库-第六周.xlsx"
        output_file = r"D:\AI处理\accessory_markdown\KnowledgeBaseTool\Excel_Data\2026智能助理-语料库-第六周_processed.xlsx"
        
        if not os.path.exists(input_file):
            f.write(f"错误：输入文件不存在: {input_file}\n")
            sys.exit(1)
            
        f.write(f"正在读取文件: {input_file}\n")
        df = pd.read_excel(input_file)
        f.write(f"读取成功，行数: {len(df)}, 列数: {len(df.columns)}\n")
        
        if len(df.columns) < 17:
            f.write(f"错误: 列数不足 {len(df.columns)}\n")
        else:
            # 计算 P (15) 列长度写入 Q (16) 列
            f.write("开始计算字数...\n")
            
            def safe_len(x):
                if pd.isna(x):
                    return 0
                return len(str(x))
            
            # 使用 apply 应用函数，不先强制转 str，以正确处理 NaN
            df.iloc[:, 16] = df.iloc[:, 15].apply(safe_len)
            
            f.write(f"正在保存到: {output_file}\n")
            df.to_excel(output_file, index=False)
            f.write("保存成功！\n")
            
    except Exception as e:
        f.write(f"发生异常: {str(e)}\n")
        import traceback
        f.write(traceback.format_exc())

print("脚本执行结束，请查看日志文件。")
