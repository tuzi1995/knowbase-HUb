import os
import zipfile
import datetime
import argparse
import ast
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

RUNTIME_FILES = (
    "server.py",
    "scoring_logic.py",
    "llm_score_evaluator.py",
    "matrix_submit_validation.py",
    "parameter_check.py",
    "knowledge_graph.py",
    "kb_v1_sync.py",
    "clone_difference_rules.py",
    "prompt_runtime.py",
    "runtime_safety.py",
    "new_product_release.py",
    "product_categories.py",
    "business_config.py",
    "comparison_matrix.py",
    "comparison_matrix_migration.py",
)

FRONTEND_FILES = (
    "index.html", "app_v8.js", "styles.css", "extra_styles.css",
    "design-system.css", "scroll-performance.css", "loading-states.css",
    "loading-manager.js", "login_bootstrap.js",
    "platform_intro.html", "platform_intro.css",
    "comparison_matrix.js",
)

RELEASE_SCRIPT_FILES = (
    "Scripts/migrate_parameter_check_postgres.py",
    "Scripts/primary_db_sync.py",
    "Scripts/retire_kb_v1_t1.py",
)

# Only immutable dependency input is packaged here. Business state stays on
# each instance and must never be overwritten by a code-only release.
EXTERNAL_RUNTIME_FILES = (
    ("⚙️ 配置文件/requirements.txt", "requirements.txt"),
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


class _AssetReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key not in {"src", "href"} or not value:
                continue
            url = urlsplit(value)
            if not url.scheme and not url.netloc and url.path.endswith((".js", ".css")):
                self.paths.append(url.path.lstrip("/"))


def validate_runtime_inputs(workspace_root):
    """Fail before writing a ZIP if required files or local imports are missing."""
    project_root = Path(workspace_root) / "KnowledgeBaseTool_Local"
    required = [project_root / name for name in (*RUNTIME_FILES, *RELEASE_SCRIPT_FILES)]
    required.extend(project_root / "link_viewer" / name for name in FRONTEND_FILES)
    required.extend(Path(workspace_root) / name for name, _ in EXTERNAL_RUNTIME_FILES)
    required.extend((project_root / "link_viewer" / "vendor", project_root / "prompt"))
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("缺少发布所需文件: " + ", ".join(missing))

    modules = {Path(name).stem for name in RUNTIME_FILES}
    for name in (*RUNTIME_FILES, *RELEASE_SCRIPT_FILES):
        tree = ast.parse((project_root / name).read_text(encoding="utf-8"), filename=name)
        for node in ast.walk(tree):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports = [node.module.split(".")[0]]
            for module in imports:
                if (project_root / (module + ".py")).is_file() and module not in modules:
                    raise ValueError(f"{name} 依赖的本地模块未加入发布清单: {module}.py")

    for name in FRONTEND_FILES:
        if not name.endswith(".html"):
            continue
        parser = _AssetReferences()
        parser.feed((project_root / "link_viewer" / name).read_text(encoding="utf-8"))
        for path in parser.paths:
            if not (project_root / "link_viewer" / path).is_file():
                raise FileNotFoundError(f"{name} 引用的静态资源不存在: {path}")
            if path not in FRONTEND_FILES and not path.startswith("vendor/"):
                raise ValueError(f"{name} 引用的静态资源未加入发布清单: {path}")


def package_project(output_dir=None):
    startup_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.dirname(startup_dir)
    project_root = os.path.join(workspace_root, 'KnowledgeBaseTool_Local')
    
    validate_runtime_inputs(workspace_root)
        
    output_dir = os.fspath(output_dir) if output_dir is not None else startup_dir
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"KnowledgeBaseTool_Deploy_{timestamp}.zip"
    zip_path = os.path.join(output_dir, zip_filename)

    include_files = list(RUNTIME_FILES)
    include_dirs = ["link_viewer/vendor", "prompt", "config_templates"]
    included_script_files = RELEASE_SCRIPT_FILES

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

        # Source HTML is what server.py serves; never ship stale generated
        # siblings, test pages, package managers or build scripts with it.
        for filename in FRONTEND_FILES:
            zipf.write(os.path.join(project_root, "link_viewer", filename),
                       arcname="link_viewer/" + filename)

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
    return Path(zip_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="创建并校验 8085 代码包，不连接或写入云端。")
    parser.add_argument("--output-dir", help="代码包输出目录，默认保留历史发布路径")
    args = parser.parse_args()
    package_project(output_dir=args.output_dir)
