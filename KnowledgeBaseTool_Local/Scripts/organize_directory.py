import os
import shutil

# 配置分类规则
# 优先级：Backups > Extension Rules
DIRECTORIES = {
    "Scripts": [".py"],
    "Excel_Data": [".xlsx", ".xls"],
    "Logs": [".txt", ".log"],
}

# 忽略列表 (文件名或文件夹名)
# 必须保留在根目录的应用核心文件
IGNORE_LIST = {
    "server.py", 
    "启动服务.bat", 
    "link_viewer", 
    "instance", 
    "配件MD", 
    "待处理",
    "organize_directory.py", # 自身
    ".git",
    ".vscode",
    "__pycache__"
}

def is_backup(filename):
    lower_name = filename.lower()
    return "backup" in lower_name or "copy" in lower_name

def organize():
    base_dir = os.getcwd()
    print(f"Working directory: {base_dir}")
    
    # 预先创建所有目标文件夹（如果还没创建）
    # 包括 Backups
    target_dirs = list(DIRECTORIES.keys()) + ["Backups"]
    for dir_name in target_dirs:
        dir_path = os.path.join(base_dir, dir_name)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"Created directory: {dir_name}")

    # 遍历文件
    files_moved = 0
    for item in os.listdir(base_dir):
        if item in IGNORE_LIST:
            continue
            
        item_path = os.path.join(base_dir, item)
        
        # 只处理文件，不处理未知的文件夹
        if os.path.isfile(item_path):
            _, ext = os.path.splitext(item)
            dest_folder = None
            
            # 1. 检查是否为备份文件
            if is_backup(item):
                dest_folder = "Backups"
            else:
                # 2. 检查扩展名规则
                for dir_name, extensions in DIRECTORIES.items():
                    if ext in extensions:
                        dest_folder = dir_name
                        break
            
            if dest_folder:
                dest_path = os.path.join(base_dir, dest_folder, item)
                try:
                    shutil.move(item_path, dest_path)
                    print(f"Moved: {item} -> {dest_folder}/")
                    files_moved += 1
                except Exception as e:
                    print(f"Error moving {item}: {e}")
            else:
                print(f"Skipped: {item} (no matching rule)")
        else:
             print(f"Skipped directory: {item}")

    print(f"\nOrganization complete. {files_moved} files moved.")

    # 清理空文件夹（可选，这里先不清理刚创建的文件夹）
    for dir_name in target_dirs:
        dir_path = os.path.join(base_dir, dir_name)
        if os.path.exists(dir_path) and not os.listdir(dir_path):
            os.rmdir(dir_path)
            print(f"Removed empty directory: {dir_name}")

if __name__ == "__main__":
    organize()
