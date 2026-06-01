#!/usr/bin/env python3
"""
数据库索引优化执行脚本
自动读取配置并执行索引优化
"""

import json
import psycopg2
import sys
from pathlib import Path

def load_db_config():
    """加载数据库配置"""
    config_file = Path(__file__).parent / 'supabase_config_local.json'
    
    if not config_file.exists():
        print("❌ 错误：未找到配置文件 supabase_config_local.json")
        return None
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    if 'local_db' not in config:
        print("❌ 错误：配置文件中缺少 local_db 配置")
        return None
    
    return config['local_db']

def connect_db(db_config):
    """连接数据库"""
    try:
        conn = psycopg2.connect(
            host=db_config.get('host', 'localhost'),
            port=db_config.get('port', 5432),
            database=db_config.get('database'),
            user=db_config.get('user'),
            password=db_config.get('password')
        )
        return conn
    except Exception as e:
        print(f"❌ 数据库连接失败：{e}")
        return None

def execute_sql_file(conn, sql_file):
    """执行 SQL 文件"""
    sql_path = Path(__file__).parent / sql_file
    
    if not sql_path.exists():
        print(f"❌ 错误：SQL 文件不存在：{sql_file}")
        return False
    
    print(f"📖 读取 SQL 文件：{sql_file}")
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()
    
    try:
        cursor = conn.cursor()
        print("⚙️  执行 SQL...")
        cursor.execute(sql)
        conn.commit()
        
        # 获取所有通知消息
        notices = conn.notices
        for notice in notices:
            print(notice.strip())
        
        cursor.close()
        return True
    except Exception as e:
        print(f"❌ SQL 执行失败：{e}")
        conn.rollback()
        return False

def verify_indexes(conn):
    """验证索引创建"""
    try:
        cursor = conn.cursor()
        
        # 查询索引数量
        cursor.execute("""
            SELECT COUNT(*) 
            FROM pg_indexes 
            WHERE tablename = 'knowledge_base_v1'
              AND indexname LIKE 'idx_kb_v1_%'
        """)
        count = cursor.fetchone()[0]
        
        print(f"\n📊 验证结果：")
        print(f"   knowledge_base_v1 表共有 {count} 个优化索引")
        
        # 查询索引列表
        cursor.execute("""
            SELECT indexname, pg_size_pretty(pg_relation_size(schemaname||'.'||indexname)) AS size
            FROM pg_indexes
            WHERE tablename = 'knowledge_base_v1'
              AND indexname LIKE 'idx_kb_v1_%'
            ORDER BY indexname
        """)
        
        indexes = cursor.fetchall()
        if indexes:
            print("\n   已创建的索引：")
            for idx_name, idx_size in indexes:
                print(f"   ✅ {idx_name} ({idx_size})")
        
        cursor.close()
        return True
    except Exception as e:
        print(f"❌ 验证失败：{e}")
        return False

def test_query_performance(conn):
    """测试查询性能"""
    try:
        cursor = conn.cursor()
        
        print("\n🧪 测试查询性能...")
        
        # 测试查询
        test_queries = [
            ("产品搜索", "SELECT * FROM knowledge_base_v1 WHERE product_name LIKE '%iPhone%' LIMIT 10"),
            ("时间排序", "SELECT * FROM knowledge_base_v1 ORDER BY update_time DESC LIMIT 10"),
            ("状态筛选", "SELECT * FROM knowledge_base_v1 WHERE review_status = 'unadjusted' LIMIT 10"),
        ]
        
        for name, query in test_queries:
            cursor.execute(f"EXPLAIN ANALYZE {query}")
            result = cursor.fetchall()
            
            # 提取执行时间
            for row in result:
                line = row[0]
                if 'Execution Time' in line:
                    print(f"   {name}: {line.strip()}")
                    break
        
        cursor.close()
        return True
    except Exception as e:
        print(f"❌ 性能测试失败：{e}")
        return False

def main():
    """主函数"""
    print("=" * 50)
    print("🚀 数据库索引优化工具")
    print("=" * 50)
    print()
    
    # 1. 加载配置
    print("📋 步骤 1/5: 加载数据库配置...")
    db_config = load_db_config()
    if not db_config:
        sys.exit(1)
    print(f"✅ 配置加载成功：{db_config.get('host')}:{db_config.get('port')}/{db_config.get('database')}")
    print()
    
    # 2. 连接数据库
    print("📋 步骤 2/5: 连接数据库...")
    conn = connect_db(db_config)
    if not conn:
        sys.exit(1)
    print("✅ 数据库连接成功")
    print()
    
    # 3. 选择 SQL 文件
    print("📋 步骤 3/5: 选择优化方案...")
    print("   1. 快速优化（6个核心索引，1-3分钟）")
    print("   2. 完整优化（18个索引，5-15分钟）")
    print()
    
    choice = input("请选择（1 或 2，默认 1）：").strip() or "1"
    
    if choice == "1":
        sql_file = "quick_index_optimization.sql"
        print("✅ 已选择：快速优化")
    elif choice == "2":
        sql_file = "database_index_optimization.sql"
        print("✅ 已选择：完整优化")
    else:
        print("❌ 无效选择")
        conn.close()
        sys.exit(1)
    print()
    
    # 4. 执行优化
    print("📋 步骤 4/5: 执行索引优化...")
    print("⏳ 请稍候，这可能需要几分钟...")
    print()
    
    success = execute_sql_file(conn, sql_file)
    if not success:
        conn.close()
        sys.exit(1)
    print()
    
    # 5. 验证和测试
    print("📋 步骤 5/5: 验证和测试...")
    verify_indexes(conn)
    print()
    test_query_performance(conn)
    
    # 关闭连接
    conn.close()
    
    print()
    print("=" * 50)
    print("🎉 索引优化完成！")
    print("=" * 50)
    print()
    print("📝 建议：")
    print("   1. 在应用中测试查询性能")
    print("   2. 定期执行 ANALYZE 更新统计信息")
    print("   3. 监控索引使用情况")
    print()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  操作已取消")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 发生错误：{e}")
        sys.exit(1)
