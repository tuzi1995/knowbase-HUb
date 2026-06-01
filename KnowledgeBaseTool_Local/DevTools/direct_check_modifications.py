#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接查询数据库检查修改记录
绕过API逻辑，直接看数据库中是否有数据
"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入 server 模块以使用其数据库连接
try:
    from server import get_supabase_client
    print("✅ 成功导入 server 模块")
except Exception as e:
    print(f"❌ 导入失败: {e}")
    print("\n尝试直接连接数据库...")
    get_supabase_client = None

def check_with_server_client():
    """使用 server.py 的客户端检查"""
    print("\n" + "=" * 70)
    print("方法1：使用 server.py 的数据库客户端")
    print("=" * 70)
    
    if not get_supabase_client:
        print("❌ 无法使用 server.py 的客户端")
        return False
    
    try:
        client = get_supabase_client()
        if not client:
            print("❌ 无法获取数据库客户端")
            return False
        
        print("✅ 成功连接数据库")
        
        # 查询所有修改记录
        print("\n查询修改记录表...")
        
        # 方法1：使用 select_all
        try:
            rows = client.select_all(
                'knowledge_base_modifications',
                order_by='modification_time',
                order_dir='desc',
                page_size=10
            )
            
            if rows:
                print(f"✅ 找到 {len(rows)} 条记录（最多显示10条）")
                
                for i, row in enumerate(rows, 1):
                    print(f"\n记录 {i}:")
                    print(f"  id: {row.get('id')}")
                    print(f"  kb_id: {row.get('kb_id')}")
                    print(f"  question_wiki_id: {row.get('question_wiki_id')}")
                    print(f"  modifier: {row.get('modifier')}")
                    print(f"  modification_time: {row.get('modification_time')}")
                    print(f"  change_type: {row.get('change_type')}")
                    print(f"  source: {row.get('source')}")
                    
                    # 检查关键字段
                    question = row.get('question', '')
                    answer = row.get('answer', '')
                    print(f"  question: {question[:50] if question else '(空)'}...")
                    print(f"  answer: {answer[:50] if answer else '(空)'}...")
                
                return True
            else:
                print("⚠️  查询返回空结果")
                return False
                
        except Exception as e:
            print(f"❌ 查询失败: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_specific_record():
    """检查特定的记录"""
    print("\n" + "=" * 70)
    print("方法2：检查特定记录 ICWIKI202604170055")
    print("=" * 70)
    
    if not get_supabase_client:
        print("❌ 无法使用 server.py 的客户端")
        return False
    
    try:
        client = get_supabase_client()
        if not client:
            print("❌ 无法获取数据库客户端")
            return False
        
        kb_id = "ICWIKI202604170055"
        print(f"\n查询 kb_id = {kb_id} 的修改记录...")
        
        rows = client.select_all(
            'knowledge_base_modifications',
            filters={'kb_id': f'eq.{kb_id}'},
            order_by='modification_time',
            order_dir='desc',
            page_size=10
        )
        
        if rows:
            print(f"✅ 找到 {len(rows)} 条记录")
            
            for i, row in enumerate(rows, 1):
                print(f"\n记录 {i}:")
                print(f"  id: {row.get('id')}")
                print(f"  kb_id: {row.get('kb_id')}")
                print(f"  modifier: {row.get('modifier')}")
                print(f"  modification_time: {row.get('modification_time')}")
                print(f"  change_type: {row.get('change_type')}")
                print(f"  source: {row.get('source')}")
                
                # 打印所有字段
                print(f"\n  所有字段:")
                for key, value in row.items():
                    if key in ['id', 'kb_id', 'modifier', 'modification_time', 'change_type', 'source']:
                        continue
                    if value is not None:
                        value_str = str(value)[:100] if len(str(value)) > 100 else str(value)
                        print(f"    {key}: {value_str}")
            
            return True
        else:
            print(f"⚠️  没有找到 kb_id = {kb_id} 的记录")
            print("\n可能的原因：")
            print("1. 记录确实没有插入")
            print("2. kb_id 字段的值不是 'ICWIKI202604170055'")
            print("3. 记录被删除了")
            
            # 尝试查询所有记录看看有没有类似的
            print("\n尝试模糊查询...")
            rows2 = client.select_all(
                'knowledge_base_modifications',
                filters={'kb_id': f'ilike.*ICWIKI*'},
                order_by='modification_time',
                order_dir='desc',
                page_size=5
            )
            
            if rows2:
                print(f"找到 {len(rows2)} 条包含 'ICWIKI' 的记录:")
                for row in rows2:
                    print(f"  - {row.get('kb_id')} | {row.get('modification_time')}")
            else:
                print("没有找到任何包含 'ICWIKI' 的记录")
            
            return False
            
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_table_structure():
    """检查表结构"""
    print("\n" + "=" * 70)
    print("方法3：检查表结构")
    print("=" * 70)
    
    if not get_supabase_client:
        print("❌ 无法使用 server.py 的客户端")
        return False
    
    try:
        client = get_supabase_client()
        if not client:
            print("❌ 无法获取数据库客户端")
            return False
        
        # 尝试查询一条记录来看字段
        print("\n查询一条记录以查看字段结构...")
        
        rows = client.select_all(
            'knowledge_base_modifications',
            order_by='id',
            order_dir='desc',
            page_size=1
        )
        
        if rows and len(rows) > 0:
            print("✅ 表结构（字段列表）:")
            row = rows[0]
            for key in sorted(row.keys()):
                value = row.get(key)
                value_type = type(value).__name__
                print(f"  - {key}: {value_type}")
            return True
        else:
            print("⚠️  表中没有数据，无法查看字段结构")
            return False
            
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n🔍 直接检查数据库中的修改记录\n")
    
    # 检查1：查询所有记录
    result1 = check_with_server_client()
    
    # 检查2：查询特定记录
    result2 = check_specific_record()
    
    # 检查3：查看表结构
    result3 = check_table_structure()
    
    # 总结
    print("\n" + "=" * 70)
    print("检查总结")
    print("=" * 70)
    
    if result1:
        print("✅ 数据库中有修改记录")
        print("\n问题分析：")
        print("1. 数据确实插入了（mod_log_ok: true）")
        print("2. 数据库中也能查到记录")
        print("3. 但 API 返回 total: 0")
        print("\n结论：问题在 API 的查询逻辑中！")
        print("\n可能的原因：")
        print("- archived_keys 过滤掉了记录")
        print("- source_module 或 operation 过滤条件")
        print("- _normalize_mod_record 函数返回 None")
        print("- _is_archived_mod_item 判断为已归档")
    elif result2:
        print("✅ 找到了特定记录")
        print("问题在 API 查询逻辑")
    else:
        print("⚠️  数据库中没有找到记录")
        print("\n问题分析：")
        print("1. mod_log_ok 为 true，说明代码认为插入成功")
        print("2. 但数据库中查不到记录")
        print("\n可能的原因：")
        print("- 插入时发生了静默失败")
        print("- 事务回滚了")
        print("- 插入到了错误的表")
        print("- 数据库连接问题")
    
    print("\n" + "=" * 70)
    print("下一步建议")
    print("=" * 70)
    
    if result1 or result2:
        print("""
数据库中有记录，但 API 返回空，说明问题在查询逻辑。

需要检查：
1. archived_keys 是否过滤掉了记录
2. _normalize_mod_record 是否返回了 None
3. source_module 和 operation 过滤条件

建议：
1. 在服务器日志中添加调试信息
2. 检查 _normalize_mod_record 函数
3. 检查 archived_keys 的值
        """)
    else:
        print("""
数据库中没有记录，说明插入失败了。

需要检查：
1. 服务器日志中的 "[INFO] Modification record inserted successfully"
2. 是否真的打印了这条日志
3. _supabase_insert_drop_unknown_columns 函数的实现
4. 数据库事务是否提交
        """)

if __name__ == "__main__":
    main()
