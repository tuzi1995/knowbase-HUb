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

def debug_investigate():
    client = get_supabase_client()
    if not client:
        print("Supabase not configured.")
        return

    print("Investigating knowledge_base_v1...")
    
    # 1. Check Total Count
    resp = client.select('knowledge_base_v1', page=1, page_size=1)
    total = -1
    if resp.status_code in (200, 206):
        cr = resp.headers.get('Content-Range')
        if cr:
            total = int(cr.split('/')[-1])
            print(f"Total records in knowledge_base_v1: {total}")
        else:
            print("Content-Range header missing.")
    else:
        print(f"Error getting count: {resp.status_code} {resp.text}")

    # 2. Check Oldest Record (Potential leftover)
    # Using 'update_time' as 'created_at' does not exist
    print("Checking oldest record by update_time...")
    resp = client.select('knowledge_base_v1', page=1, page_size=1, order_by='update_time', order_dir='asc')
    oldest_id = None
    if resp.status_code in (200, 206):
        data = resp.json()
        if data:
            oldest_rec = data[0]
            oldest_id = oldest_rec.get('question_wiki_id')
            print(f"Oldest Record ID: {oldest_id}")
            print(f"Update Time: {oldest_rec.get('update_time')}")
            print(f"Question: {oldest_rec.get('question')}")
        else:
            print("No records found.")
    else:
        print(f"Error checking oldest: {resp.status_code} {resp.text}")

    if not oldest_id:
        return

    # 3. Check for Foreign Key Dependency in kb_scores
    print(f"Checking if ID {oldest_id} exists in kb_scores...")
    # Assuming kb_id is the foreign key in kb_scores
    resp = client.select('kb_scores', filters={'kb_id': f'eq.{oldest_id}'}, page_size=1)
    if resp.status_code in (200, 206):
        data = resp.json()
        print(f"Records in kb_scores linking to {oldest_id}: {len(data)}")
        if data:
            print("Found dependency in kb_scores!")
    else:
        print(f"Error checking kb_scores: {resp.status_code} {resp.text}")

    # 4. Try to delete the oldest record to see error
    print(f"Attempting to delete oldest record {oldest_id} to capture error...")
    del_resp = client.delete('knowledge_base_v1', {'question_wiki_id': f'eq.{oldest_id}'})
    print(f"Delete Response Code: {del_resp.status_code}")
    print(f"Delete Response Text: {del_resp.text}")

if __name__ == '__main__':
    debug_investigate()
