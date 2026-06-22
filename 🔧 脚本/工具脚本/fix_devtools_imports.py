#!/usr/bin/env python3
"""
修复 DevTools 中脚本的导入路径
"""
import os
import re
from pathlib import Path

DEVTOOLS_DIR = Path("/Users/guoying/AI建设和学习/One/knowbase_hub_8085/KnowledgeBaseTool_Local/DevTools")

def fix_script_imports(file_path):
    """修复单个脚本的导入路径"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # 查找 sys.path.insert 行
        # 匹配模式：sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        pattern1 = r"sys\.path\.insert\(0,\s*os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\)"
        
        # 替换为：sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        replacement1 = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))"
        
        if re.search(pattern1, content):
            content = re.sub(pattern1, replacement1, content)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
        
        # 如果没有 sys.path.insert，检查是否需要添加
        if 'from server import' in content or 'import server' in content:
            # 检查是否已经有 sys.path 设置
            if 'sys.path.insert' not in content:
                # 在 import sys 后添加
                if 'import sys' in content:
                    # 找到 import sys 的位置
                    lines = content.split('\n')
                    new_lines = []
                    added = False
                    
                    for i, line in enumerate(lines):
                        new_lines.append(line)
                        
                        # 在 import sys 和 import os 之后添加
                        if not added and 'import sys' in line:
                            # 检查下一行是否是 import os
                            if i + 1 < len(lines) and 'import os' in lines[i + 1]:
                                new_lines.append(lines[i + 1])
                                new_lines.append('')
                                new_lines.append('# 添加项目根目录到 Python 路径')
                                new_lines.append('sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))')
                                added = True
                                # 跳过下一行（import os）
                                continue
                    
                    if added:
                        content = '\n'.join(new_lines)
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
    print("修复 DevTools 脚本的导入路径")
    print("=" * 70)
    print()
    
    if not DEVTOOLS_DIR.exists():
        print(f"❌ DevTools 目录不存在: {DEVTOOLS_DIR}")
        return
    
    # 查找所有 Python 脚本
    scripts = list(DEVTOOLS_DIR.glob("*.py"))
    
    if not scripts:
        print("⚠️  DevTools 目录中没有 Python 脚本")
        return
    
    print(f"找到 {len(scripts)} 个脚本\n")
    
    fixed_count = 0
    skipped_count = 0
    
    for script in scripts:
        print(f"处理: {script.name}")
        
        if fix_script_imports(script):
            print(f"  ✅ 已修复")
            fixed_count += 1
        else:
            print(f"  ⏭️  跳过（无需修改或已正确）")
            skipped_count += 1
    
    print()
    print("=" * 70)
    print("修复完成")
    print("=" * 70)
    print(f"已修复: {fixed_count} 个脚本")
    print(f"跳过: {skipped_count} 个脚本")
    
    print("\n💡 验证:")
    print("  cd KnowledgeBaseTool_Local")
    print("  python3 DevTools/test_source_module_fix.py")

if __name__ == '__main__':
    main()
