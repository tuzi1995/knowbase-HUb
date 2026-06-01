
import os
import json
import requests

# Load env manually
def load_env_file(path):
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

# Try loading from parent directory if not in current
if os.path.exists('.env'):
    load_env_file('.env')
elif os.path.exists('../.env'):
    load_env_file('../.env')
elif os.path.exists('../../.env'):
    load_env_file('../../.env')

# Fallback to supabase_config.json
if not os.environ.get("SUPABASE_URL"):
    config_path = 'supabase_config.json'
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                if config.get('url'):
                    os.environ["SUPABASE_URL"] = config['url']
                if config.get('key'):
                    os.environ["SUPABASE_KEY"] = config['key']
        except Exception as e:
            print(f"Failed to load config from {config_path}: {e}")

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

class SupabaseClient:
    def __init__(self, url, key):
        self.url = url
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    def select(self, table, select="*", range_start=0, range_end=9):
        # range header: items=0-9
        headers = self.headers.copy()
        headers["Range"] = f"{range_start}-{range_end}"
        res = requests.get(f"{self.url}/rest/v1/{table}?select={select}", headers=headers)
        return res

    def update(self, table, data, match_col, match_val):
        # update one row
        res = requests.patch(f"{self.url}/rest/v1/{table}?{match_col}=eq.{match_val}", headers=self.headers, json=data)
        return res

def clean_data():
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY not found in environment.")
        return

    client = SupabaseClient(url, key)
    print("Fetching links to check for leading/trailing spaces...")
    
    offset = 0
    limit = 1000
    total_cleaned = 0
    
    while True:
        # Fetch batch
        res = client.select('link_previews', select='id,url,kb_id', range_start=offset, range_end=offset + limit - 1)
        if res.status_code != 200:
            print(f"Error fetching data: {res.text}")
            break
            
        rows = res.json()
        if not rows:
            break
            
        print(f"Processing batch {offset} to {offset + len(rows)}...")
        
        for row in rows:
            needs_update = False
            updates = {}
            
            # Check URL
            if row.get('url'):
                original_url = row['url']
                cleaned_url = original_url.strip()
                if original_url != cleaned_url:
                    updates['url'] = cleaned_url
                    needs_update = True
                    # print(f"Cleaning URL: '{original_url}' -> '{cleaned_url}'")
            
            # Check KB_ID
            if row.get('kb_id'):
                original_kb = row['kb_id']
                cleaned_kb = original_kb.strip()
                if original_kb != cleaned_kb:
                    updates['kb_id'] = cleaned_kb
                    needs_update = True
                    print(f"Cleaning KB_ID: '{original_kb}' -> '{cleaned_kb}'")
            
            if needs_update:
                try:
                    update_res = client.update('link_previews', updates, 'id', row['id'])
                    if update_res.status_code in (200, 204):
                        total_cleaned += 1
                    else:
                        print(f"Error updating row {row['id']}: {update_res.text}")
                except Exception as e:
                    print(f"Exception updating row {row['id']}: {e}")
        
        if len(rows) < limit:
            break
        offset += limit

    print(f"link_previews cleaning complete. Updated {total_cleaned} rows.")

    # ---------------------------------------------------------
    # 2. Clean knowledge_base_v1 table
    # ---------------------------------------------------------
    print("\nFetching knowledge_base_v1 to check for leading/trailing spaces...")
    
    offset = 0
    limit = 1000
    total_cleaned_kb = 0
    
    while True:
        # Fetch batch
        res = client.select('knowledge_base_v1', select='question_wiki_id,question,product_name', range_start=offset, range_end=offset + limit - 1)
        if res.status_code != 200:
            print(f"Error fetching KB data: {res.text}")
            break
            
        rows = res.json()
        if not rows:
            break
            
        print(f"Processing KB batch {offset} to {offset + len(rows)}...")
        
        for row in rows:
            needs_update = False
            updates = {}
            row_id = row.get('question_wiki_id')
            if not row_id: continue

            # Check ID (question_wiki_id)
            original_id = row_id
            cleaned_id = original_id.strip()
            if original_id != cleaned_id:
                # Can't update ID easily if it's PK, but let's try or skip. 
                # Ideally we update it if allowed.
                # If question_wiki_id is PK, we need to handle constraints.
                # Assuming we can update it.
                updates['question_wiki_id'] = cleaned_id
                needs_update = True
                print(f"Cleaning ID: '{original_id}' -> '{cleaned_id}'")
            
            # Check Question
            if row.get('question'):
                original_q = row['question']
                cleaned_q = original_q.strip()
                if original_q != cleaned_q:
                    updates['question'] = cleaned_q
                    needs_update = True
            
            # Check Product Name
            if row.get('product_name'):
                original_p = row['product_name']
                cleaned_p = original_p.strip()
                if original_p != cleaned_p:
                    updates['product_name'] = cleaned_p
                    needs_update = True

            if needs_update:
                try:
                    # Use original ID to find row
                    update_res = client.update('knowledge_base_v1', updates, 'question_wiki_id', original_id)
                    if update_res.status_code in (200, 204):
                        total_cleaned_kb += 1
                    else:
                        print(f"Error updating KB row {original_id}: {update_res.text}")
                except Exception as e:
                    print(f"Exception updating KB row {original_id}: {e}")
        
        if len(rows) < limit:
            break
        offset += limit

    print(f"knowledge_base_v1 cleaning complete. Updated {total_cleaned_kb} rows.")

if __name__ == "__main__":
    clean_data()
