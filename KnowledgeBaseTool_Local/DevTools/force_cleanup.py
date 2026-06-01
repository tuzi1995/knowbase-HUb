import os
import sys
import time

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from server import get_supabase_client
except ImportError:
    print("Error: Could not import get_supabase_client from server.py")
    sys.exit(1)

def force_cleanup():
    client = get_supabase_client()
    if not client:
        print("Error: Supabase client not configured.")
        return

    print("=== STARTING FORCE CLEANUP ===")
    
    # ---------------------------------------------------------
    # 1. Clear kb_scores (Dependency Table)
    # ---------------------------------------------------------
    print("\n[Step 1] Clearing kb_scores...")
    retry_count = 0
    while True:
        # Check count
        # Note: select() headers already include count=exact. Do not pass invalid args.
        resp = client.select('kb_scores', page=1, page_size=1)
        total = 0
        if resp.status_code in (200, 206):
            cr = resp.headers.get('Content-Range')
            if cr:
                try:
                    total = int(cr.split('/')[-1])
                except: pass
        
        print(f"Current kb_scores count: {total}")
        
        if total == 0:
            print("kb_scores is empty. Proceeding.")
            break
            
        # Delete batch
        # Fetch IDs
        ids_resp = client.select('kb_scores', page=1, page_size=1000, columns='id')
        if ids_resp.status_code not in (200, 206):
            print(f"Error fetching IDs: {ids_resp.text}")
            time.sleep(1)
            continue
            
        ids = [item['id'] for item in ids_resp.json()]
        if not ids:
            print("No IDs found despite count > 0. Retrying count check...")
            continue
            
        print(f"Deleting batch of {len(ids)} scores...")
        id_str = "(" + ",".join([str(x) for x in ids]) + ")"
        del_resp = client.delete('kb_scores', {'id': f'in.{id_str}'})
        
        if del_resp.status_code >= 400:
            print(f"Delete failed: {del_resp.text}")
            time.sleep(1)
        else:
            print("Batch deleted.")
            time.sleep(0.1) # Be nice to API
            
        retry_count += 1
        if retry_count > 100:
            print("CRITICAL ERROR: Failed to clear kb_scores after 100 attempts.")
            return

    # ---------------------------------------------------------
    # 2. Clear knowledge_base_v1 (Main Table)
    # ---------------------------------------------------------
    print("\n[Step 2] Clearing knowledge_base_v1...")
    retry_count = 0
    while True:
        # Check count
        # Note: select() headers already include count=exact. Do not pass invalid args.
        resp = client.select('knowledge_base_v1', page=1, page_size=1)
        total = 0
        if resp.status_code in (200, 206):
            cr = resp.headers.get('Content-Range')
            if cr:
                try:
                    total = int(cr.split('/')[-1])
                except: pass
        
        print(f"Current knowledge_base_v1 count: {total}")
        
        if total == 0:
            print("knowledge_base_v1 is empty. Proceeding.")
            break
            
        # Delete batch
        # Fetch IDs (question_wiki_id is string)
        ids_resp = client.select('knowledge_base_v1', page=1, page_size=100, columns='question_wiki_id')
        if ids_resp.status_code not in (200, 206):
            print(f"Error fetching IDs: {ids_resp.text}")
            time.sleep(1)
            continue
            
        ids = [item['question_wiki_id'] for item in ids_resp.json()]
        if not ids:
            print("No IDs found despite count > 0. Retrying count check...")
            continue
            
        print(f"Deleting batch of {len(ids)} records...")
        # Handle string IDs with quotes
        quoted_ids = [f'"{str(x)}"' for x in ids]
        id_str = "(" + ",".join(quoted_ids) + ")"
        
        del_resp = client.delete('knowledge_base_v1', {'question_wiki_id': f'in.{id_str}'})
        
        if del_resp.status_code >= 400:
            print(f"Delete failed: {del_resp.text}")
            # Likely foreign key constraint if kb_scores wasn't truly empty
            # But we checked kb_scores above.
            print("Retrying...")
            time.sleep(1)
        else:
            print("Batch deleted.")
            time.sleep(0.1)
            
        retry_count += 1
        if retry_count > 100:
            print("CRITICAL ERROR: Failed to clear knowledge_base_v1 after 100 attempts.")
            return

    print("\n=== CLEANUP COMPLETE ===")
    print("Both tables are now empty.")

if __name__ == "__main__":
    force_cleanup()
