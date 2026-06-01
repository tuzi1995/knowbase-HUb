import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import os
# Add parent directory to path to allow importing modules from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sys
import os
import json

sys.path.append(os.getcwd())
from server import get_supabase_client

def debug_structure():
    client = get_supabase_client()
    if not client:
        print("Supabase not configured.")
        return

    tables = ['kb_scores', 'link_previews', 'knowledge_base_modifications']
    
    for table in tables:
        print(f"\nChecking table: {table}")
        
        # Check count
        resp = client.select(table, page=1, page_size=1)
        if resp.status_code in (200, 206):
            cr = resp.headers.get('Content-Range')
            if cr:
                total = int(cr.split('/')[-1])
                print(f"Total records: {total}")
            
            data = resp.json()
            if data:
                print(f"First record keys (columns): {list(data[0].keys())}")
                if 'id' in data[0]:
                    print(f"Sample ID: {data[0]['id']}")
                if 'kb_id' in data[0]:
                    print(f"Sample kb_id: {data[0]['kb_id']}")
                if 'question_wiki_id' in data[0]:
                    print(f"Sample question_wiki_id: {data[0]['question_wiki_id']}")
            else:
                print("Table is empty (or no access).")
        else:
            print(f"Error checking table {table}: {resp.status_code} {resp.text}")

if __name__ == '__main__':
    debug_structure()
