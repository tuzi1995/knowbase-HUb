#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查修改记录完整链路
验证从保存到显示的整个流程
"""

import psycopg2
from datetime import datetime, timedelta

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'knowledgebase_local',
    'user': 'postgres',
    'password': 'postgres'
}

def check_modifications_table():
    """检查修改记录表是否存在及其结构"""
    print("=" * 70)
    print("1. 检查 knowledge_base_modifications 表")
    print("=" * 70)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # 检查表是否存在
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'knowledge_base_modifications'
            );
        """)
        exists = cur.fetchone()[0]
        
        if not exists:
            print("❌ 表不存在！")
            return False
        
        print("✅ 表存在")
        
        # 获取表结构
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'knowledge_base_modifications'
            ORDER BY ordinal_position;
        """)
        columns = cur.fetchall()
        
        print(f"\n表结构（共 {len(columns)} 个字段）：")
        for col_name, data_type, nullable in columns[:10]:  # 只显示前10个
            print(f"  - {col_name}: {data_type} {'NULL' if nullable == 'YES' else 'NOT NULL'}")
        
        if len(columns) > 10:
            print(f"  ... 还有 {len(columns) - 10} 个字段")
        
        # 统计记录数
        cur.execute("SELECT COUNT(*) FROM knowledge_base_modifications;")
        count = cur.fetchone()[0]
        print(f"\n当前记录数: {count}")
        
        # 获取最近的记录
        if count > 0:
            cur.execute("""
                SELECT kb_id, modifier, modification_time, change_type, source
                FROM knowledge_base_modifications
                ORDER BY modification_time DESC
                LIMIT 5;
            """)
            recent = cur.fetchall()
            
            print("\n最近5条记录：")
            for kb_id, modifier, mod_time, change_type, source in recent:
                print(f"  - {kb_id} | {modifier} | {mod_time} | {change_type} | {source}")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_recent_kb_updates():
    """检查最近的知识库更新"""
    print("\n" + "=" * 70)
    print("2. 检查最近的知识库更新")
    print("=" * 70)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # 获取最近更新的记录
        cur.execute("""
            SELECT question_wiki_id, question, review_status, update_time
            FROM knowledge_base_v1
            ORDER BY update_time DESC
            LIMIT 5;
        """)
        recent = cur.fetchall()
        
        if not recent:
            print("⚠️  没有找到任何知识库记录")
            return False
        
        print(f"\n最近更新的5条知识库记录：")
        for wiki_id, question, status, update_time in recent:
            question_short = question[:50] + "..." if len(question) > 50 else question
            print(f"  - {wiki_id}")
            print(f"    问题: {question_short}")
            print(f"    状态: {status}")
            print(f"    更新时间: {update_time}")
            print()
        
        # 检查这些记录是否有对应的修改记录
        print("检查这些记录是否有对应的修改记录：")
        for wiki_id, _, _, _ in recent:
            cur.execute("""
                SELECT COUNT(*) FROM knowledge_base_modifications
                WHERE kb_id = %s;
            """, (wiki_id,))
            mod_count = cur.fetchone()[0]
            
            if mod_count > 0:
                print(f"  ✅ {wiki_id}: {mod_count} 条修改记录")
            else:
                print(f"  ❌ {wiki_id}: 没有修改记录")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_modification_api():
    """检查修改记录API端点"""
    print("\n" + "=" * 70)
    print("3. 检查修改记录API端点")
    print("=" * 70)
    
    import requests
    
    try:
        # 测试获取修改记录的API
        url = "http://localhost:8085/api/modifications"
        print(f"\n测试 GET {url}")
        
        response = requests.get(url, params={'page': 1, 'page_size': 10}, timeout=10)
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 401:
            print("⚠️  需要登录才能访问")
            return False
        
        if response.status_code != 200:
            print(f"❌ API返回错误: {response.text[:200]}")
            return False
        
        data = response.json()
        print(f"✅ API正常响应")
        
        if isinstance(data, dict):
            total = data.get('total', 0)
            items = data.get('data', [])
            print(f"总记录数: {total}")
            print(f"返回记录数: {len(items)}")
            
            if len(items) > 0:
                print("\n第一条记录示例：")
                first = items[0]
                print(f"  kb_id: {first.get('kb_id')}")
                print(f"  modifier: {first.get('modifier')}")
                print(f"  modification_time: {first.get('modification_time')}")
                print(f"  change_type: {first.get('change_type')}")
                print(f"  source: {first.get('source')}")
            else:
                print("⚠️  API返回空列表")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到8085服务")
        return False
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_insert_modification():
    """测试直接插入修改记录"""
    print("\n" + "=" * 70)
    print("4. 测试直接插入修改记录")
    print("=" * 70)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # 插入测试记录
        test_data = {
            'kb_id': 'TEST_' + datetime.now().strftime('%Y%m%d%H%M%S'),
            'modifier': 'test_user',
            'modification_time': datetime.now().isoformat(),
            'change_type': 'edit',
            'source': '测试插入',
            'question': '测试问题',
            'answer': '测试答案'
        }
        
        print(f"\n插入测试记录: {test_data['kb_id']}")
        
        cur.execute("""
            INSERT INTO knowledge_base_modifications 
            (kb_id, modifier, modification_time, change_type, source, question, answer)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            test_data['kb_id'],
            test_data['modifier'],
            test_data['modification_time'],
            test_data['change_type'],
            test_data['source'],
            test_data['question'],
            test_data['answer']
        ))
        
        inserted_id = cur.fetchone()[0]
        conn.commit()
        
        print(f"✅ 插入成功，ID: {inserted_id}")
        
        # 验证插入
        cur.execute("""
            SELECT kb_id, modifier, change_type, source
            FROM knowledge_base_modifications
            WHERE id = %s;
        """, (inserted_id,))
        
        result = cur.fetchone()
        if result:
            print(f"✅ 验证成功: {result}")
        else:
            print("❌ 验证失败：找不到刚插入的记录")
        
        # 清理测试数据
        cur.execute("DELETE FROM knowledge_base_modifications WHERE id = %s;", (inserted_id,))
        conn.commit()
        print(f"✅ 测试数据已清理")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_server_logs():
    """检查服务器日志中的修改记录相关信息"""
    print("\n" + "=" * 70)
    print("5. 服务器日志检查建议")
    print("=" * 70)
    
    print("""
请在8085服务的终端窗口中查找以下关键信息：

1. 保存成功的日志：
   - 搜索: "Modification record inserted successfully"
   - 应该在每次保存后出现

2. 插入失败的日志：
   - 搜索: "Failed to insert modification record"
   - 如果出现，会显示具体错误

3. 修改记录相关的错误：
   - 搜索: "knowledge_base_modifications"
   - 查看是否有表不存在或字段错误

4. API调用日志：
   - 搜索: "POST /api/kb/update"
   - 查看保存请求是否成功

5. 查询修改记录的日志：
   - 搜索: "GET /api/modifications"
   - 查看前端是否正确调用了API
    """)

def main():
    print("\n🔍 开始检查修改记录完整链路\n")
    
    results = []
    
    # 1. 检查表结构
    results.append(("修改记录表检查", check_modifications_table()))
    
    # 2. 检查知识库更新
    results.append(("知识库更新检查", check_recent_kb_updates()))
    
    # 3. 检查API端点
    results.append(("API端点检查", check_modification_api()))
    
    # 4. 测试插入
    results.append(("插入测试", test_insert_modification()))
    
    # 5. 日志检查建议
    check_server_logs()
    
    # 总结
    print("\n" + "=" * 70)
    print("检查总结")
    print("=" * 70)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n✅ 所有检查通过！")
        print("\n如果修改记录还是不显示，可能的原因：")
        print("1. 前端没有正确调用 /api/modifications API")
        print("2. 前端过滤条件导致记录被过滤掉")
        print("3. 浏览器缓存问题（尝试 Cmd+Shift+R 强制刷新）")
        print("4. 保存时虽然没报错，但实际没有插入记录（检查服务器日志）")
    else:
        print("\n⚠️  部分检查失败，请根据上述错误信息排查")
    
    print("\n" + "=" * 70)
    print("下一步建议")
    print("=" * 70)
    print("""
1. 在浏览器中打开开发者工具（F12）
2. 切换到 Network 标签页
3. 在知识库管理中编辑并保存一条记录
4. 观察以下请求：
   - POST /api/kb/update（保存知识库）
   - PUT /api/kb/item/tags（保存标签）
   - GET /api/modifications（加载修改记录）
5. 检查每个请求的响应内容
6. 查看 Console 标签页是否有JavaScript错误
    """)

if __name__ == "__main__":
    main()
