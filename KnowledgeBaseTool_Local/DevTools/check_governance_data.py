#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查知识库治理数据

验证 kb_recall 表中是否有数据
"""

import sys
import os
import json

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_governance_data():
    """检查知识库治理数据"""
    
    print("="*60)
    print("检查知识库治理数据")
    print("="*60)
    
    # 1. 检查配置
    print("\n1. 检查配置文件...")
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'supabase_config_local.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print(f"   ✅ 配置文件读取成功")
        print(f"   - use_supabase_governance: {config.get('use_supabase_governance')}")
        print(f"   - database: {config.get('local_db', {}).get('database')}")
        
        if not config.get('use_supabase_governance'):
            print("   ⚠️  警告: use_supabase_governance 未启用")
    except Exception as e:
        print(f"   ❌ 配置文件读取失败: {e}")
        return False
    
    # 2. 连接数据库
    print("\n2. 连接数据库...")
    try:
        import psycopg2
        
        db_config = config.get('local_db', {})
        conn = psycopg2.connect(
            host=db_config.get('host', 'localhost'),
            port=db_config.get('port', 5432),
            database=db_config.get('database', 'knowledgebase_local'),
            user=db_config.get('user', 'postgres'),
            password=db_config.get('password', '')
        )
        print(f"   ✅ 数据库连接成功")
        
        cur = conn.cursor()
        
        # 3. 检查表是否存在
        print("\n3. 检查 kb_recall 表...")
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'kb_recall'
            );
        """)
        table_exists = cur.fetchone()[0]
        
        if not table_exists:
            print("   ❌ kb_recall 表不存在")
            conn.close()
            return False
        
        print("   ✅ kb_recall 表存在")
        
        # 4. 检查数据量
        print("\n4. 检查数据量...")
        cur.execute("SELECT COUNT(*) FROM kb_recall;")
        total_count = cur.fetchone()[0]
        print(f"   总记录数: {total_count}")
        
        if total_count == 0:
            print("   ⚠️  警告: kb_recall 表是空的")
            print("\n   可能的原因:")
            print("   1. 数据还未导入")
            print("   2. 数据在其他数据库中")
            print("   3. 需要通过 Excel 导入数据")
        else:
            print(f"   ✅ 找到 {total_count} 条记录")
            
            # 5. 检查月份分布
            print("\n5. 检查月份分布...")
            cur.execute("""
                SELECT month, COUNT(*) as count 
                FROM kb_recall 
                GROUP BY month 
                ORDER BY month DESC 
                LIMIT 10;
            """)
            months = cur.fetchall()
            
            if months:
                print("   最近的月份数据:")
                for month, count in months:
                    print(f"   - {month}: {count} 条记录")
            
            # 6. 查看示例数据
            print("\n6. 查看示例数据...")
            cur.execute("""
                SELECT id, month, kb_id, recall_count 
                FROM kb_recall 
                ORDER BY month DESC 
                LIMIT 3;
            """)
            samples = cur.fetchall()
            
            if samples:
                print("   示例记录:")
                for sample in samples:
                    id_val, month, wiki_id, recall_count = sample
                    print(f"   - ID: {id_val}, 月份: {month}, Wiki ID: {wiki_id}")
                    print(f"     召回次数: {recall_count}")
        
        conn.close()
        
        print("\n" + "="*60)
        if total_count > 0:
            print("✅ 知识库治理数据检查完成 - 数据正常")
        else:
            print("⚠️  知识库治理数据检查完成 - 表为空，需要导入数据")
        print("="*60)
        
        return total_count > 0
        
    except ImportError:
        print("   ❌ psycopg2 模块未安装")
        print("   请运行: pip install psycopg2-binary")
        return False
    except Exception as e:
        print(f"   ❌ 数据库操作失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    try:
        success = check_governance_data()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
