import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(BASE_DIR), 'instance', 'data.db')

def check_matrix_categories():
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库文件不存在: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT count(*) FROM product_matrix")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT count(*) FROM product_matrix WHERE product_category IS NULL OR product_category = '' OR product_category = 'nan'")
        empty = cursor.fetchone()[0]
        
        print(f"📊 Matrix 表统计:")
        print(f"  - 总记录数: {total}")
        print(f"  - 分类为空: {empty}")
        
        if empty > 0:
            cursor.execute("SELECT question_wiki_id, product_name, product_category FROM product_matrix WHERE product_category IS NULL OR product_category = '' OR product_category = 'nan' LIMIT 5")
            rows = cursor.fetchall()
            print(f"🧐 检查空记录样例:")
            for r in rows:
                print(f"  - [{r[0]}]: model='{r[1]}', cat='{r[2]}'")
                
    except Exception as e:
        print(f"❌ 查询失败: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_matrix_categories()
