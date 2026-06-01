#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 button 表的序列值问题
解决 "duplicate key value violates unique constraint button_pkey" 错误
"""

import psycopg2

# 从配置文件读取
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'knowledgebase_local',
    'user': 'postgres',
    'password': '11111111'
}

def fix_button_sequence():
    """修复 button 表的序列值"""
    print("=" * 70)
    print("修复 button 表序列值")
    print("=" * 70)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("✅ 成功连接数据库")
        
        cur = conn.cursor()
        
        # 1. 查看当前状态
        print("\n1. 当前状态:")
        
        cur.execute("SELECT last_value FROM button_id_seq;")
        seq_val = cur.fetchone()[0]
        print(f"   序列当前值: {seq_val}")
        
        cur.execute("SELECT MAX(id) FROM button;")
        max_id_result = cur.fetchone()
        max_id = max_id_result[0] if max_id_result[0] else 0
        print(f"   表中最大ID: {max_id}")
        
        # 2. 判断是否需要修复
        if seq_val <= max_id:
            print(f"\n⚠️  发现问题：序列值({seq_val}) <= 最大ID({max_id})")
            print("   这会导致主键冲突！")
            
            # 3. 修复序列值
            print("\n2. 修复序列值...")
            cur.execute(f"SELECT setval('button_id_seq', {max_id});")
            conn.commit()
            
            # 4. 验证修复
            cur.execute("SELECT last_value FROM button_id_seq;")
            new_seq_val = cur.fetchone()[0]
            print(f"   ✅ 序列值已更新: {seq_val} -> {new_seq_val}")
            
            print("\n✅ 修复完成！")
            print("\n现在可以正常提交机型矩阵修改了。")
        else:
            print(f"\n✅ 序列值正常，无需修复")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n❌ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n🔧 修复 button 表序列值问题\n")
    
    result = fix_button_sequence()
    
    if result:
        print("\n" + "=" * 70)
        print("下一步")
        print("=" * 70)
        print("1. 无需重启8085服务")
        print("2. 直接在浏览器中测试机型矩阵管理")
        print("3. 点击'提交已选修改'应该成功了")
    else:
        print("\n修复失败，请检查错误信息")
