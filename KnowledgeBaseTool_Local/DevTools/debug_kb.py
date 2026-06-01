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

# Add current directory to path
sys.path.append(os.getcwd())

from server import get_supabase_client

def debug_kb():
    client = get_supabase_client()
    if not client:
        print("Supabase not configured.")
        return

    print("Checking knowledge_base_v1...")
    
    # 1. Get Total Count
    resp = client.select('knowledge_base_v1', page=1, page_size=1)
    total = -1
    if resp.status_code in (200, 206):
        cr = resp.headers.get('Content-Range')
        if cr:
            total = int(cr.split('/')[-1])
            print(f"Total records: {total}")
        else:
            print("Content-Range header missing.")
    else:
        print(f"Error getting count: {resp.status_code} {resp.text}")

    # 2. Check for ID = -1
    resp = client.select('knowledge_base_v1', filters={'question_wiki_id': 'eq.-1'}, page_size=10)
    if resp.status_code in (200, 206):
        data = resp.json()
        print(f"Records with question_wiki_id='-1': {len(data)}")
        if data:
            print(f"Sample: {data[0]}")
    else:
        print(f"Error checking -1: {resp.status_code} {resp.text}")

    # 3. Check for NULL ID
    resp = client.select('knowledge_base_v1', filters={'question_wiki_id': 'is.null'}, page_size=10)
    if resp.status_code in (200, 206):
        data = resp.json()
        print(f"Records with question_wiki_id=NULL: {len(data)}")
    else:
        print(f"Error checking NULL: {resp.status_code} {resp.text}")

if __name__ == '__main__':
    debug_kb()
