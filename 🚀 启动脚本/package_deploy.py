import os
import zipfile
import datetime

DB_SUFFIXES = (".db", ".sqlite", ".sqlite3")


def _should_skip_file(rel_path: str) -> bool:
    rp = str(rel_path or "").replace("\\", "/").lower()
    # Never deploy runtime sqlite databases from local package.
    if rp.startswith("instance/") and rp.endswith(DB_SUFFIXES):
        return True
    return False


def package_project():
    project_root = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(project_root)
    project_root = os.path.join(project_root, 'KnowledgeBaseTool_Local')
    
    # Check if directory exists
    if not os.path.exists(project_root):
        print(f"Error: Project root directory not found at {project_root}")
        return
        
    output_dir = os.path.dirname(os.path.abspath(__file__))
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"KnowledgeBaseTool_Deploy_{timestamp}.zip"
    zip_path = os.path.join(output_dir, zip_filename)

    # Files to include (using glob patterns concept but manual list for precision)
    # NOTE:
    # Avoid non-ASCII filenames inside the zip (Linux `unzip` may decode them as mojibake depending on locale).
    # Use a mapping so we can keep local filenames but store ASCII names in the archive.
    include_files = [
        # Core Backend
        "server.py",
        "scoring_logic.py",
        "llm_score_evaluator.py",
        "requirements.txt",
        
        # Configs
        "scoring_config.json",
        "supabase_config.json",
        "supabase_config_local.json",
        "tag_pool.json",
        "model_mappings.json",
        "product_catalog.json",
        
        # Scripts (Startup & Debug)
        "启动服务.bat",
        "KB1知识库评分工具.bat",
        "README_DEPLOY.txt",
        "PROJECT_STRUCTURE.md",
        
        # Database Scripts
        "create_kb_scores.sql",
        "create_mod_table.sql",
        "supabase_schema.sql",
        "update_schema_v2.sql",
        "update_schema_v3.sql",
        "migrate_ops_to_supabase.py",
    ]

    archive_name_overrides = {
        "启动服务.bat": "start_service.bat",
        "KB1知识库评分工具.bat": "kb1_score_tool.bat",
    }

    # Directories to include recursively
    include_dirs = [
        "link_viewer", # Frontend
        "prompt",      # Prompts
        "Scripts",     # Utility Scripts (Optional but safer to include)
        "instance",
        "DevTools",
    ]

    print(f"Creating deployment package: {zip_filename}")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add individual files
        for filename in include_files:
            file_path = os.path.join(project_root, filename)
            if os.path.exists(file_path):
                arcname = archive_name_overrides.get(filename, filename)
                if arcname != filename:
                    print(f"Adding file: {filename} -> {arcname}")
                else:
                    print(f"Adding file: {filename}")
                zipf.write(file_path, arcname=arcname)
            else:
                print(f"Warning: File not found: {filename}")

        # Add directories
        for dirname in include_dirs:
            dir_path = os.path.join(project_root, dirname)
            if os.path.exists(dir_path):
                print(f"Adding directory: {dirname}")
                for root, dirs, files in os.walk(dir_path):
                    # Skip __pycache__ and hidden files
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                    
                    for file in files:
                        if file.startswith('.') or file.endswith('.pyc'):
                            continue
                            
                        abs_path = os.path.join(root, file)
                        # Calculate relative path for arcname
                        rel_path = os.path.relpath(abs_path, project_root)
                        if _should_skip_file(rel_path):
                            print(f"  Skipping runtime DB: {rel_path}")
                            continue
                        print(f"  Adding: {rel_path}")
                        zipf.write(abs_path, arcname=rel_path)
            else:
                print(f"Warning: Directory not found: {dirname}")

    print(f"\nPackage created successfully at: {zip_path}")

if __name__ == "__main__":
    package_project()
