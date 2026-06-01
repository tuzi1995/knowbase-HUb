import os
import shutil
import sys
from pathlib import Path
import datetime

# ================= 配置区 =================
# 定义文件类型映射规则
FILE_TYPES = {
    'Images': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico'],
    'Documents': ['.pdf', '.doc', '.docx', '.txt', '.md', '.rtf', '.odt'],
    'Spreadsheets': ['.xls', '.xlsx', '.csv', '.ods'],
    'Presentations': ['.ppt', '.pptx', '.key'],
    'Archives': ['.zip', '.rar', '.7z', '.tar', '.gz', '.iso'],
    'Audio': ['.mp3', '.wav', '.flac', '.m4a', '.wma'],
    'Video': ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv'],
    'Code': ['.py', '.js', '.html', '.css', '.java', '.c', '.cpp', '.php', '.json', '.xml', '.sql'],
    'Executables': ['.exe', '.msi', '.bat', '.sh', '.app'],
    'Fonts': ['.ttf', '.otf', '.woff', '.woff2']
}

# 忽略的文件或目录名（精确匹配）
IGNORE_NAMES = {'.DS_Store', 'Thumbs.db', '.git', '.vscode', 'node_modules', '__pycache__'}

def get_category(extension):
    """根据后缀名获取分类文件夹名"""
    ext = extension.lower()
    for category, extensions in FILE_TYPES.items():
        if ext in extensions:
            return category
    return 'Others'

def unique_path(path):
    """如果文件已存在，添加 (1), (2) 等后缀避免覆盖"""
    if not os.path.exists(path):
        return path
    
    filename, extension = os.path.splitext(path)
    counter = 1
    while os.path.exists(f"{filename}_({counter}){extension}"):
        counter += 1
    return f"{filename}_({counter}){extension}"

def organize_folder(target_path):
    target_path = Path(target_path)
    
    if not target_path.exists():
        print(f"❌ 错误：路径不存在 -> {target_path}")
        return

    print(f"📂 正在整理目录: {target_path}")
    print("-" * 50)

    stats = {cat: 0 for cat in FILE_TYPES.keys()}
    stats['Others'] = 0
    moved_count = 0

    # 遍历目录下的所有文件（不递归进入子目录，只整理第一层，防止打乱深层结构）
    # 如果需要递归整理，可以使用 target_path.rglob('*')，但通常不建议这样做
    for item in target_path.iterdir():
        if item.is_dir():
            continue
        
        if item.name in IGNORE_NAMES or item.name.startswith('~$'):
            continue
            
        # 跳过脚本自身（如果脚本被放在目标目录中运行）
        if item.name == os.path.basename(__file__):
            continue

        category = get_category(item.suffix)
        
        # 创建分类目录
        category_dir = target_path / category
        if not category_dir.exists():
            category_dir.mkdir()
        
        # 移动文件
        dest_path = unique_path(category_dir / item.name)
        try:
            shutil.move(str(item), str(dest_path))
            print(f"✅ 移动: {item.name} -> {category}/{Path(dest_path).name}")
            stats[category] += 1
            moved_count += 1
        except Exception as e:
            print(f"❌ 移动失败 {item.name}: {e}")

    print("-" * 50)
    print(f"🎉 整理完成！共移动 {moved_count} 个文件。")
    print("📊 统计详情：")
    for cat, count in stats.items():
        if count > 0:
            print(f"   - {cat}: {count}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 如果命令行传了路径
        target = sys.argv[1]
    else:
        # 否则交互式输入
        print("请输入您想要整理的文件夹绝对路径")
        print("例如: D:\\Downloads 或 C:\\Users\\Name\\Desktop")
        target = input("路径: ").strip().strip('"').strip("'")
    
    if target:
        organize_folder(target)
    else:
        print("未提供路径，程序退出。")
