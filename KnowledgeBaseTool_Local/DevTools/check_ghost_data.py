import os
import sys
import json
from collections import Counter

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from server import get_supabase_client
except ImportError:
    print("Error: Could not import get_supabase_client from server.py")
    sys.exit(1)

def check_ghosts():
    client = get_supabase_client()
    if not client:
        print("Error: Supabase client not configured.")
        return

    print("--- Diagnostic Report ---")
    
    # 1. Check knowledge_base_v1 count
    print("Fetching all IDs from knowledge_base_v1...")
    # Use update_time if available, or just ID
    all_items = client.select_all('knowledge_base_v1', columns='question_wiki_id, review_status, update_time', order_by='question_wiki_id')
    
    total_count = len(all_items)
    print(f"Total records in knowledge_base_v1: {total_count}")
    
    if total_count == 0:
        print("Table is empty.")
        return

    # 2. Check for duplicates
    ids = [item.get('question_wiki_id') for item in all_items]
    id_counts = Counter(ids)
    duplicates = [id for id, count in id_counts.items() if count > 1]
    
    if duplicates:
        print(f"Found {len(duplicates)} duplicate IDs: {duplicates[:5]}...")
    else:
        print("No duplicate IDs found.")

    # 3. Check review_status distribution
    statuses = [item.get('review_status') for item in all_items]
    status_counts = Counter(statuses)
    print("Review Status Distribution:")
    for status, count in status_counts.items():
        print(f"  {status}: {count}")

    # 4. Check kb_scores count
    print("\nFetching kb_scores count...")
    scores = client.select_all('kb_scores', columns='id, kb_id')
    print(f"Total records in kb_scores: {len(scores)}")
    
    # 5. Check if any scores refer to non-existent KB items
    score_kb_ids = set(s.get('kb_id') for s in scores)
    kb_ids_set = set(ids)
    
    orphaned_scores = [kid for kid in score_kb_ids if kid not in kb_ids_set]
    print(f"Orphaned scores (kb_id not in knowledge_base_v1): {len(orphaned_scores)}")
    
    # 6. Specific Check for the 31 Ghost Records
    print("\n--- Investigating Ghost Records (IDs in KB but maybe not in import) ---")
    # We assume the "ghosts" are the ones currently in DB.
    # Let's check their relation to kb_scores
    
    ghost_ids = [item.get('question_wiki_id') for item in all_items]
    
    # Check if these IDs exist in kb_scores
    print(f"Checking {len(ghost_ids)} KB IDs against kb_scores...")
    
    # Fetch all kb_scores kb_ids
    all_score_kb_ids = set()
    page = 1
    while True:
        s_resp = client.select('kb_scores', page=page, page_size=1000, columns='kb_id')
        if not s_resp.json():
            break
        for s in s_resp.json():
            all_score_kb_ids.add(s.get('kb_id'))
        page += 1
        
    print(f"Total unique kb_ids in kb_scores: {len(all_score_kb_ids)}")
    
    related_count = 0
    ghosts_with_scores = []
    for gid in ghost_ids:
        if gid in all_score_kb_ids:
            related_count += 1
            ghosts_with_scores.append(gid)
            
    print(f"Out of {len(ghost_ids)} KB records, {related_count} have related entries in kb_scores.")
    if ghosts_with_scores:
        print(f"Example IDs with scores: {ghosts_with_scores[:5]}")
    else:
        print("None of the KB records have related scores. (Constraint might be elsewhere?)")

if __name__ == "__main__":
    check_ghosts()
