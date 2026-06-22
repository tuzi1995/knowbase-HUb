#!/usr/bin/env python3
"""
更新文档中的脚本路径引用
"""
import os
import re
from pathlib import Path

BASE_DIR = Path("/Users/guoying/AI建设和学习/One/knowbase_hub_8085")

# 脚本文件映射：旧路径 -> 新路径
SCRIPT_MAPPINGS = {
    # 测试脚本
    'test_kb_tags_api.py': '🔧 脚本/测试脚本/test_kb_tags_api.py',
    'test_modification_api.py': '🔧 脚本/测试脚本/test_modification_api.py',
    'test_modification_record.py': '🔧 脚本/测试脚本/test_modification_record.py',
    'test_insert_modification.py': '🔧 脚本/测试脚本/test_insert_modification.py',
    'test_source_module_fix.py': '🔧 脚本/测试脚本/test_source_module_fix.py',
    'test_matrix_modification_record.py': '🔧 脚本/测试脚本/test_matrix_modification_record.py',
    'test_change_meta_fix.py': '🔧 脚本/测试脚本/test_change_meta_fix.py',
    'check_modifications.py': '🔧 脚本/测试脚本/check_modifications.py',
    'check_mod_table_structure.py': '🔧 脚本/测试脚本/check_mod_table_structure.py',
    'check_modifications_after_submit.py': '🔧 脚本/测试脚本/check_modifications_after_submit.py',
    'direct_check_modifications.py': '🔧 脚本/测试脚本/direct_check_modifications.py',
    
    # 修复脚本
    'fix_button_sequence.py': '🔧 脚本/修复脚本/fix_button_sequence.py',
    'create_mod_table_now.py': '🔧 脚本/修复脚本/create_mod_table_now.py',
}

def update_document(file_path):
    """更新单个文档"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        updated = False
        
        # 替换脚本路径
        for old_script, new_path in SCRIPT_MAPPINGS.items():
            # 匹配 python3 script_name.py 的模式
            pattern = rf'python3\s+{re.escape(old_script)}'
            if re.search(pattern, content):
                # 替换为相对于 KnowBase Hub 的路径
                replacement = f'python3 "../{new_path}"'
                content = re.sub(pattern, replacement, content)
                updated = True
                print(f"  更新: {old_script} -> {new_path}")
        
        if updated:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
        
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return False

def main():
    """主函数"""
    print("=" * 70)
    print("更新文档中的脚本路径引用")
    print("=" * 70)
    print()
    
    # 查找所有 Markdown 文档
    doc_dirs = [
        BASE_DIR / "📚 文档",
    ]
    
    updated_files = []
    skipped_files = []
    
    for doc_dir in doc_dirs:
        if not doc_dir.exists():
            continue
        
        for md_file in doc_dir.rglob("*.md"):
            rel_path = md_file.relative_to(BASE_DIR)
            print(f"检查: {rel_path}")
            
            if update_document(md_file):
                updated_files.append(rel_path)
            else:
                skipped_files.append(rel_path)
    
    print()
    print("=" * 70)
    print("更新完成")
    print("=" * 70)
    print(f"更新文件数: {len(updated_files)}")
    print(f"跳过文件数: {len(skipped_files)}")
    
    if updated_files:
        print("\n已更新的文件:")
        for f in updated_files:
            print(f"  ✅ {f}")
    
    print("\n💡 提示:")
    print("  文档中的脚本路径已更新为相对路径")
    print("  运行脚本时需要在 KnowledgeBaseTool_Local 目录下执行")
    print("  例如: cd KnowledgeBaseTool_Local && python3 \"../🔧 脚本/测试脚本/test_xxx.py\"")

if __name__ == '__main__':
    main()
