import os
import zipfile
import datetime

RUNTIME_FILES = (
    "server.py",
    "scoring_logic.py",
    "llm_score_evaluator.py",
    "matrix_submit_validation.py",
    "parameter_check.py",
    "knowledge_graph.py",
    "kb_v1_sync.py",
)

# These files contain the current product/model definitions but no credentials.
# Store them with ASCII archive names so Linux unzip does not depend on locale.
EXTERNAL_RUNTIME_FILES = (
    ("⚙️ 配置文件/requirements.txt", "requirements.txt"),
    ("⚙️ 配置文件/product_catalog.json", "product_catalog.json"),
    ("⚙️ 配置文件/model_mappings.json", "model_mappings.json"),
)

# Credentials and mutable runtime state are deliberately not packaged.  The
# cloud host keeps its own configuration, and data is transferred by the
# guarded release procedure after integrity checks and a remote backup.
EXCLUDED_RUNTIME_FILES = {
    "ai_config.json",
    "scoring_config.json",
    "smart_mapping_embedding_config.json",
    "supabase_config.json",
    "supabase_config_local.json",
}


def package_project():
    startup_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.dirname(startup_dir)
    project_root = os.path.join(workspace_root, 'KnowledgeBaseTool_Local')
    
    # Check if directory exists
    if not os.path.exists(project_root):
        print(f"Error: Project root directory not found at {project_root}")
        return
        
    output_dir = startup_dir
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"KnowledgeBaseTool_Deploy_{timestamp}.zip"
    zip_path = os.path.join(output_dir, zip_filename)

    include_files = list(RUNTIME_FILES)
    include_dirs = ["link_viewer", "prompt"]
    included_script_files = [
        "Scripts/migrate_parameter_check_postgres.py",
        "Scripts/primary_db_sync.py",
    ]

    print(f"Creating deployment package: {zip_filename}")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add Python runtime modules.  Do not deploy local credentials or
        # mutable configuration files: cloud configuration stays on the host.
        for filename in include_files:
            if filename in EXCLUDED_RUNTIME_FILES:
                continue
            file_path = os.path.join(project_root, filename)
            if os.path.exists(file_path):
                print(f"Adding file: {filename}")
                zipf.write(file_path, arcname=filename)
            else:
                print(f"Warning: File not found: {filename}")

        for source_rel, archive_name in EXTERNAL_RUNTIME_FILES:
            source_path = os.path.join(workspace_root, source_rel)
            if not os.path.exists(source_path):
                print(f"Warning: External runtime file not found: {source_rel}")
                continue
            print(f"Adding external runtime file: {source_rel} -> {archive_name}")
            zipf.write(source_path, arcname=archive_name)

        for filename in included_script_files:
            file_path = os.path.join(project_root, filename)
            if os.path.exists(file_path):
                print(f"Adding release script: {filename}")
                zipf.write(file_path, arcname=filename)
            else:
                print(f"Warning: Release script not found: {filename}")

        # Add static assets and prompt templates.  Development dependencies,
        # build outputs, and transient backups are not server runtime inputs.
        for dirname in include_dirs:
            dir_path = os.path.join(project_root, dirname)
            if os.path.exists(dir_path):
                print(f"Adding directory: {dirname}")
                for root, dirs, files in os.walk(dir_path):
                    dirs[:] = [
                        d for d in dirs
                        if not d.startswith('.') and d not in {'__pycache__', 'node_modules', 'dist', 'backup', 'backups'}
                    ]
                    
                    for file in files:
                        if file.startswith('.') or file.endswith('.pyc') or file in EXCLUDED_RUNTIME_FILES:
                            continue
                        abs_path = os.path.join(root, file)
                        rel_path = os.path.relpath(abs_path, project_root)
                        print(f"  Adding: {rel_path}")
                        zipf.write(abs_path, arcname=rel_path)
            else:
                print(f"Warning: Directory not found: {dirname}")

    print(f"\nPackage created successfully at: {zip_path}")

if __name__ == "__main__":
    package_project()
