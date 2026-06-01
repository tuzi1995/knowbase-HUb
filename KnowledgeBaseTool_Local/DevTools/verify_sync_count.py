import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import os
# Add parent directory to path to allow importing modules from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import sys
import io
import time
from server import get_supabase_client

# Set stdout to utf-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def verify_count():
    print("Initializing Supabase client...")
    client = get_supabase_client()
    
    table = 'knowledge_base_v1'
    print(f"Fetching count from {table}...")
    
    # 1. Get exact count using HEAD or select with count
    # Supabase-py might not have a direct count method exposed in our wrapper, 
    # but let's try a small select with count header
    try:
        # Our client.select sets Prefer: count=exact
        resp = client.select(table, page=1, page_size=1)
        total_count = -1
        if resp.status_code == 200:
            # content-range: 0-0/5321
            cr = resp.headers.get('content-range', '')
            if '/' in cr:
                total_count = int(cr.split('/')[1])
                print(f"Server reports Total Count: {total_count}")
        else:
            print(f"Failed to get count: {resp.status_code} {resp.text}")
            
        # 2. Test select_all
        print("\nTesting select_all fetching...")
        start_time = time.time()
        all_data = client.select_all(table, order_by='question_wiki_id')
        duration = time.time() - start_time
        
        fetched_count = len(all_data)
        print(f"select_all fetched: {fetched_count} items")
        print(f"Time taken: {duration:.2f} seconds")
        
        if total_count != -1:
            if fetched_count == total_count:
                print("SUCCESS: Fetched count matches server total.")
            else:
                print(f"FAILURE: Mismatch! Server said {total_count}, fetched {fetched_count}")
        
        # 3. Check kb_scores
        print("\nChecking kb_scores...")
        scores = client.select_all('kb_scores')
        print(f"kb_scores count: {len(scores)}")
        
        # Check duplicates
        kb_ids = [s.get('kb_id') for s in scores if s.get('kb_id')]
        unique_ids = set(kb_ids)
        print(f"Unique kb_ids in kb_scores: {len(unique_ids)}")
        if len(kb_ids) != len(unique_ids):
            print(f"WARNING: Found {len(kb_ids) - len(unique_ids)} duplicates in kb_scores!")

                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_count()
