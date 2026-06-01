import os
import sys
import json
import time

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from server import get_supabase_client
except ImportError:
    print("Error: Could not import get_supabase_client from server.py")
    sys.exit(1)

def debug_delete():
    client = get_supabase_client()
    if not client:
        print("Error: Supabase client not configured.")
        return

    target_id = "ICWIKI202307243151"
    
    print(f"--- Debugging Deletion for ID: {target_id} ---")
    
    # 1. Check existence
    print("Checking if record exists...")
    resp = client.select('knowledge_base_v1', filters={'question_wiki_id': f'eq.{target_id}'})
    if resp.status_code != 200 or not resp.json():
        print("Record not found. Picking another one...")
        # Get any record
        resp = client.select('knowledge_base_v1', page=1, page_size=1)
        if resp.json():
            target_id = resp.json()[0]['question_wiki_id']
            print(f"New target: {target_id}")
        else:
            print("Table is empty!")
            return

    # 2. Check for dependencies in kb_scores
    print(f"Checking for dependencies in kb_scores for kb_id={target_id}...")
    scores_resp = client.select('kb_scores', filters={'kb_id': f'eq.{target_id}'})
    scores = scores_resp.json() if scores_resp.status_code == 200 else []
    print(f"Found {len(scores)} related scores.")
    
    # 3. Attempt Delete
    print(f"Attempting to delete {target_id} from knowledge_base_v1...")
    del_resp = client.delete('knowledge_base_v1', {'question_wiki_id': f'eq.{target_id}'})
    
    print(f"Delete Status: {del_resp.status_code}")
    print(f"Delete Response: {del_resp.text}")
    
    if del_resp.status_code >= 400:
        print("DELETE FAILED!")
    else:
        print("DELETE SUCCESSFUL!")
        # Verify
        check = client.select('knowledge_base_v1', filters={'question_wiki_id': f'eq.{target_id}'})
        if not check.json():
            print("Verified: Record is gone.")
        else:
            print("Verified: Record STILL EXISTS (Ghost data?)")

if __name__ == "__main__":
    debug_delete()
