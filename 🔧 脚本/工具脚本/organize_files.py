#!/usr/bin/env python3
"""
KnowBase Hub 文件自动分类整理脚本
自动将文件按类型分类到不同文件夹
"""
import os
import shutil
from pathlib import Path

# 基础路径
BASE_DIR = Path("/Users/guoying/AI建设和学习/One/knowbase_hub_8085")

# 分类规则
CATEGORIES = {
    "📚 文档/迁移文档": {
        "patterns": ["MIGRATION", "迁移", "README_LOCAL"],
        "files": []
    },
    "📚 文档/优化报告": {
        "patterns": ["优化", "OPTIMIZATION"],
        "files": []
    },
    "📚 文档/修复说明": {
        "patterns": ["修复", "BUG", "TASK", "问题"],
        "files": []
    },
    "📚 文档/使用指南": {
        "patterns": ["指南", "验证", "快速"],
        "files": []
    },
    "🔧 脚本/测试脚本": {
        "patterns": ["test_", "check_", "debug_", "verify"],
        "files": []
    },
    "🔧 脚本/修复脚本": {
        "patterns": ["fix_", "create_", "force_"],
        "files": []
    },
    "🔧 脚本/工具脚本": {
        "patterns": ["manual_", "backfill_", "migrate_", "run_"],
        "files": []
    },
    "🗄️ 数据库/SQL脚本": {
        "patterns": [".sql"],
        "files": []
    },
    "⚙️ 配置文件": {
        "patterns": ["config", ".json", "requirements.txt", "known_hosts"],
        "files": []
    },
    "📝 日志文件": {
        "patterns": [".log", "Logs/"],
        "files": []
    },
    "🚀 启动脚本": {
        "patterns": ["start", "启动", "deploy"],
        "files": []
    }
}

def should_skip(path):
    """判断是否应该跳过该文件/文件夹"""
    skip_patterns = [
        ".DS_Store",
        "__pycache__",
        "migration_export",  # 迁移数据不移动
        "organize_files.py",  # 本脚本不移动
        "organize_report.md",  # 报告不移动
        "文件整理说明.md"  # 说明文档不移动
    ]
    
    name = os.path.basename(path)
    
    # 特殊处理：如果是 KnowledgeBaseTool_Local 文件夹本身，跳过
    # 但如果是其中的文件，需要检查
    if name == "KnowledgeBaseTool_Local" and os.path.isdir(path):
        return True
    
    return any(pattern in name for pattern in skip_patterns)

def categorize_file(filename):
    """根据文件名判断分类"""
    filename_lower = filename.lower()
    
    # 按优先级匹配
    for category, info in CATEGORIES.items():
        for pattern in info["patterns"]:
            if pattern.lower() in filename_lower:
                return category
    
    return None

def organize_files(dry_run=True):
    """整理文件"""
    print("=" * 70)
    print("📂 KnowBase Hub 文件自动分类整理")
    print("=" * 70)
    
    if dry_run:
        print("\n⚠️  预览模式（不会实际移动文件）")
    else:
        print("\n✅ 执行模式（将实际移动文件）")
    
    print(f"\n基础目录: {BASE_DIR}\n")
    
    # 收集需要整理的文件
    files_to_organize = []
    
    # 扫描根目录
    for item in os.listdir(BASE_DIR):
        item_path = BASE_DIR / item
        
        if should_skip(item_path):
            continue
        
        if os.path.isfile(item_path):
            category = categorize_file(item)
            if category:
                files_to_organize.append((item, category, item_path))
    
    # 扫描 KnowledgeBaseTool_Local 根目录的文档和脚本
    local_dir = BASE_DIR / "KnowledgeBaseTool_Local"
    if local_dir.exists():
        # 需要保留在项目中的核心运行文件（白名单）
        core_runtime_files = {
            'server.py',  # 核心服务器
            'scoring_logic.py',  # 评分逻辑
            'llm_score_evaluator.py',  # LLM评估器
            'matrix_submit_validation.py',  # 矩阵验证
            'ai_config.json',  # AI配置
            'model_mappings.json',  # 模型映射
            'product_catalog.json',  # 产品目录
            'scoring_config.json',  # 评分配置
            'tag_pool.json',  # 标签池
            'supabase_config.json',  # Supabase配置
            'supabase_config_local.json',  # 本地配置
            'requirements.txt',  # Python依赖
            'known_hosts',  # SSH配置
            'KB1知识库评分工具.bat',  # Windows启动脚本
            'PROJECT_STRUCTURE.md',  # 项目结构（保留作为参考）
            'K-Matrix助手_功能介绍与数据流.md',  # 功能介绍（保留作为参考）
            '优化清单'  # 优化清单（保留作为TODO）
        }
        
        for item in os.listdir(local_dir):
            item_path = local_dir / item
            
            if should_skip(item_path):
                continue
            
            # 跳过子文件夹
            if os.path.isdir(item_path):
                continue
            
            # 跳过核心运行文件
            if item in core_runtime_files:
                continue
            
            # 处理所有其他文档和脚本文件
            if os.path.isfile(item_path):
                ext = os.path.splitext(item)[1].lower()
                # 扩展文件类型，包括无扩展名的文件
                if ext in ['.md', '.txt', '.py', '.sql', '.sh', '.bat', '.json', '.log'] or ext == '':
                    category = categorize_file(item)
                    if category:
                        files_to_organize.append((item, category, item_path))
                    else:
                        # 如果没有匹配到分类，根据扩展名给一个默认分类
                        if ext == '.md' or ext == '.txt':
                            files_to_organize.append((item, "📚 文档/其他文档", item_path))
                        elif ext == '.py':
                            files_to_organize.append((item, "🔧 脚本/其他脚本", item_path))
                        elif ext == '.sql':
                            files_to_organize.append((item, "🗄️ 数据库/SQL脚本", item_path))
                        elif ext == '.log':
                            files_to_organize.append((item, "📝 日志文件", item_path))
    
    # 按分类分组
    categorized = {}
    for filename, category, filepath in files_to_organize:
        if category not in categorized:
            categorized[category] = []
        categorized[category].append((filename, filepath))
    
    # 显示分类结果
    total_files = 0
    for category in sorted(categorized.keys()):
        files = categorized[category]
        total_files += len(files)
        print(f"\n{category} ({len(files)} 个文件)")
        print("-" * 70)
        for filename, filepath in sorted(files):
            # 显示相对路径
            rel_path = filepath.relative_to(BASE_DIR)
            print(f"  • {filename}")
            print(f"    来源: {rel_path}")
    
    print(f"\n" + "=" * 70)
    print(f"总计: {total_files} 个文件需要整理")
    print("=" * 70)
    
    if not dry_run:
        print("\n开始移动文件...")
        
        moved_count = 0
        error_count = 0
        
        for category in sorted(categorized.keys()):
            # 创建目标文件夹
            target_dir = BASE_DIR / category
            target_dir.mkdir(parents=True, exist_ok=True)
            
            files = categorized[category]
            for filename, filepath in files:
                try:
                    target_path = target_dir / filename
                    
                    # 如果目标文件已存在，添加序号
                    if target_path.exists():
                        base, ext = os.path.splitext(filename)
                        counter = 1
                        while target_path.exists():
                            new_name = f"{base}_{counter}{ext}"
                            target_path = target_dir / new_name
                            counter += 1
                    
                    shutil.move(str(filepath), str(target_path))
                    moved_count += 1
                    print(f"  ✅ {filename} → {category}")
                    
                except Exception as e:
                    error_count += 1
                    print(f"  ❌ {filename}: {e}")
        
        print(f"\n" + "=" * 70)
        print(f"完成！成功移动 {moved_count} 个文件，失败 {error_count} 个")
        print("=" * 70)
    else:
        print("\n💡 提示：")
        print("  - 这是预览模式，没有实际移动文件")
        print("  - 如果分类结果满意，运行以下命令执行移动：")
        print(f"    python3 organize_files.py --execute")
    
    return categorized

def create_report(categorized):
    """创建整理报告"""
    report_path = BASE_DIR / "organize_report.md"
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# KnowBase Hub 文件整理报告\n\n")
        f.write(f"整理时间: {os.popen('date').read().strip()}\n\n")
        f.write("## 分类统计\n\n")
        
        total = sum(len(files) for files in categorized.values())
        f.write(f"总计: **{total}** 个文件\n\n")
        
        for category in sorted(categorized.keys()):
            files = categorized[category]
            f.write(f"### {category}\n\n")
            f.write(f"文件数: {len(files)}\n\n")
            
            for filename, filepath in sorted(files):
                rel_path = filepath.relative_to(BASE_DIR)
                f.write(f"- `{filename}`\n")
                f.write(f"  - 原路径: `{rel_path}`\n")
            
            f.write("\n")
        
        f.write("## 文件夹结构\n\n")
        f.write("```\n")
        f.write("KnowBase Hub/\n")
        for category in sorted(categorized.keys()):
            f.write(f"├── {category}/\n")
            files = categorized[category]
            for i, (filename, _) in enumerate(sorted(files)):
                prefix = "└──" if i == len(files) - 1 else "├──"
                f.write(f"│   {prefix} {filename}\n")
        f.write("└── KnowledgeBaseTool_Local/ (主项目，未移动)\n")
        f.write("```\n")
    
    print(f"\n📄 整理报告已生成: {report_path}")

if __name__ == "__main__":
    import sys
    
    # 检查是否是执行模式
    execute_mode = "--execute" in sys.argv or "-e" in sys.argv
    
    # 执行整理
    categorized = organize_files(dry_run=not execute_mode)
    
    # 生成报告
    create_report(categorized)
    
    if not execute_mode:
        print("\n" + "=" * 70)
        print("📋 下一步操作：")
        print("=" * 70)
        print("1. 查看上面的分类预览")
        print("2. 如果满意，运行以下命令执行整理：")
        print(f"   python3 {__file__} --execute")
        print("3. 查看详细报告：")
        print(f"   cat organize_report.md")
        print("=" * 70)
