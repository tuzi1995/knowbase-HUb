
import requests
import json
import os

# Supabase Config
try:
    with open('supabase_config.json', 'r') as f:
        config = json.load(f)
        URL = config['url']
        KEY = config['key']
except Exception as e:
    print(f"Error loading config: {e}")
    exit(1)

HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json"
}

def get_data():
    try:
        # Fetch first 5 scored records
        params = {
            "select": "id,kb_id,total_score,score_data,status",
            "status": "eq.scored",
            "limit": 5
        }
        resp = requests.get(f"{URL}/rest/v1/kb_scores", headers=HEADERS, params=params)
        
        if resp.status_code >= 400:
            print(f"Error: {resp.status_code} - {resp.text}")
            return
            
        data = resp.json()
        print(f"Found {len(data)} records.")
        
        for item in data:
            print("-" * 50)
            print(f"ID: {item.get('id')}")
            print(f"Total Score: {item.get('total_score')}")
            score_data = item.get('score_data')
            print(f"Score Data Raw: {score_data}")
            
            if score_data:
                try:
                    if isinstance(score_data, str):
                        parsed = json.loads(score_data)
                    else:
                        parsed = score_data
                    print("Parsed Keys:", parsed.keys())
                except Exception as e:
                    print(f"Parse Error: {e}")
            else:
                print("Score Data is EMPTY/NULL")
                
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    get_data()
