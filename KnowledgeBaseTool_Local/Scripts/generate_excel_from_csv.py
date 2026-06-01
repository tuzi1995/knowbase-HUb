import pandas as pd
import os

CSV_FILE = r"D:\AI处理\accessory_markdown\Output\KB1知识库_V2Prompt测试_10条.csv"
XLSX_FILE = r"D:\AI处理\accessory_markdown\Output\KB1知识库_V2Prompt测试_10条.xlsx"

def generate_final_excel(csv_path, xlsx_path):
    print("正在生成最终 Excel 报表...")
    try:
        # 尝试不同的编码读取
        try:
            df_result = pd.read_csv(csv_path, encoding='utf-8-sig')
        except UnicodeDecodeError:
            print("utf-8-sig 读取失败，尝试 gb18030...")
            df_result = pd.read_csv(csv_path, encoding='gb18030')
        
        # 统计分析
        # 确保列存在，如果列名不匹配则打印列名
        print("CSV 列名:", df_result.columns.tolist())
        
        score_cols = ["问题质量（10）", "答案合规与准确性（30）", "时效性（20）", "实际解决力（30）", "非冗余性（10）", "总分"]
        
        # 检查列是否存在
        missing_cols = [c for c in score_cols if c not in df_result.columns]
        if missing_cols:
            print(f"警告: 缺失列 {missing_cols}")
            # 尝试修复列名 (如果 header 被重复写入)
            df_result = df_result[df_result["问题ID"] != "问题ID"] # 移除重复的 header 行
            for c in score_cols:
                df_result[c] = pd.to_numeric(df_result[c], errors='coerce')
        
        avg_scores = df_result[score_cols].mean()
        suggestion_counts = df_result["处理建议"].value_counts(normalize=True).mul(100).round(1).astype(str) + '%'
        
        analysis_data = []
        for idx, val in avg_scores.items():
            analysis_data.append({"项目": f"平均-{idx}", "数值": round(val, 2)})
        for idx, val in suggestion_counts.items():
            analysis_data.append({"项目": f"占比-{idx}", "数值": val})
        analysis_df = pd.DataFrame(analysis_data)
        
        # 评分标准说明 (V2)
        rules_data = [
            ["维度", "分值", "评分细则"],
            ["问题质量", "10", "清晰、自包含(10); 指代不明扣10; 宽泛扣5"],
            ["答案合规与准确性", "30", "准确亲切(30); 事实错误扣30; 违规/敏感词扣20; 语气生硬扣10"],
            ["时效性", "20", "≤6个月(20); 6-12个月(15); 1-2年(10); >2年(5); 过期(0)"],
            ["实际解决力", "30", "有步骤结论(30); 无方案扣15-20; 步骤混乱扣10"],
            ["非冗余性", "10", "独特(10); 完全重复扣10"]
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

if __name__ == "__main__":
    generate_final_excel(CSV_FILE, XLSX_FILE)
