import os
import sys

# Add parent directory to path to import server
# Using os.getcwd() if script is run from project root, or specific path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import get_supabase_client

def check_counts():
    print("Connecting to Supabase...")
    client = get_supabase_client()
    
    # Check Source Table
    print("Checking 'knowledge_base_v1' count...")
    res_kb = client.select('knowledge_base_v1', page=1, page_size=1)
    print(f"Status Code: {res_kb.status_code}")
    print(f"Headers: {res_kb.headers}")
    kb_count = 0
    if res_kb.status_code >= 200 and res_kb.status_code < 300:
        cr = res_kb.headers.get('Content-Range', '')
        if '/' in cr:
            kb_count = int(cr.split('/')[1])
    print(f"Source (knowledge_base_v1) Total: {kb_count}")
    
    # Check Destination Table
    print("Checking 'kb_scores' count...")
    res_scores = client.select('kb_scores', page=1, page_size=1)
    print(f"Status Code: {res_scores.status_code}")
    scores_count = 0
    if res_scores.status_code >= 200 and res_scores.status_code < 300:
        cr = res_scores.headers.get('Content-Range', '')
        if '/' in cr:
            scores_count = int(cr.split('/')[1])
    print(f"Destination (kb_scores) Total: {scores_count}")
    
    if kb_count > 0 and scores_count != kb_count:
        print(f"MISMATCH: Diff is {abs(kb_count - scores_count)}")
    elif kb_count > 0 and scores_count == kb_count:
        print("MATCH: Counts are synchronized.")
    else:
        print("ERROR: Could not retrieve counts.")

if __name__ == "__main__":
    check_counts()
