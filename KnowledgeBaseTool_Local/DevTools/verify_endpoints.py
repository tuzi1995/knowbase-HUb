
import requests
import json
import os

BASE_URL = 'http://127.0.0.1:8080'
SESSION = requests.Session()

def login(username='admin', password='123456'): # Wait, default is '123456'? Let's check init_db
    # Line 107: user = User(username='admin', password_hash=generate_password_hash('123456'))
    # Wait, check_password_hash compares with '123456'.
    # But line 121: check_password_hash(user.password_hash, data.get('password'))
    
    print(f"Logging in as {username}...")
    try:
        resp = SESSION.post(f'{BASE_URL}/login', json={'username': username, 'password': password})
        if resp.status_code == 200 and resp.json().get('success'):
            print("Login successful")
            return True
        else:
            print(f"Login failed: {resp.text}")
            return False
    except Exception as e:
        print(f"Login error: {e}")
        return False

def test_api_config():
    print("\n--- Testing API Config ---")
    # GET
    resp = SESSION.get(f'{BASE_URL}/api/scoring/config')
    if resp.status_code == 200:
        print("GET /api/scoring/config: OK")
        print("Config:", resp.json())
    else:
        print(f"GET /api/scoring/config FAILED: {resp.status_code} {resp.text}")

    # POST (Update)
    new_config = {'model': 'deepseek-chat-test'}
    resp = SESSION.post(f'{BASE_URL}/api/scoring/config', json=new_config)
    if resp.status_code == 200 and resp.json().get('success'):
        print("POST /api/scoring/config: OK")
    else:
        print(f"POST /api/scoring/config FAILED: {resp.status_code} {resp.text}")

    # Verify Update
    resp = SESSION.get(f'{BASE_URL}/api/scoring/config')
    if resp.status_code == 200 and resp.json().get('model') == 'deepseek-chat-test':
        print("Verify Config Update: OK")
    else:
        print(f"Verify Config Update FAILED: {resp.json()}")

def test_scoring_prompt():
    print("\n--- Testing Scoring Prompt ---")
    # GET
    resp = SESSION.get(f'{BASE_URL}/api/scoring/prompt')
    if resp.status_code == 200:
        print("GET /api/scoring/prompt: OK")
        print("Prompt length:", len(resp.json().get('prompt', '')))
    else:
        print(f"GET /api/scoring/prompt FAILED: {resp.status_code} {resp.text}")

    # POST
    new_prompt = "Test Prompt " + str(os.urandom(4).hex())
    resp = SESSION.post(f'{BASE_URL}/api/scoring/prompt', json={'prompt': new_prompt})
    if resp.status_code == 200 and resp.json().get('success'):
        print("POST /api/scoring/prompt: OK")
    else:
        print(f"POST /api/scoring/prompt FAILED: {resp.status_code} {resp.text}")

    # Verify Update
    resp = SESSION.get(f'{BASE_URL}/api/scoring/prompt')
    if resp.status_code == 200 and resp.json().get('prompt') == new_prompt:
        print("Verify Prompt Update: OK")
    else:
        print(f"Verify Prompt Update FAILED: {resp.json().get('prompt')} != {new_prompt}")

def test_matrix_sync_and_export():
    print("\n--- Testing Matrix Sync & Export ---")
    
    # 1. Check KB Data (using scoring endpoint as proxy for KB existence)
    resp = SESSION.get(f'{BASE_URL}/api/scoring/data?page=1&pageSize=1')
    if resp.status_code == 200:
        data = resp.json().get('data', [])
        if not data:
            print("KB/Scoring data is empty.")
            # return # Don't return, maybe matrix sync works anyway
        else:
            print(f"KB has data (first item ID: {data[0].get('kb_id')})")
    else:
        print(f"Failed to fetch KB/Scoring data: {resp.status_code}")

    # 2. Sync Matrix (Merge mode)
    print("Syncing Matrix (Merge)...")
    resp = SESSION.post(f'{BASE_URL}/api/matrix/sync', json={'mode': 'merge'})
    if resp.status_code == 200:
        print("Sync OK:", resp.json())
    else:
        print(f"Sync FAILED: {resp.status_code} {resp.text}")
        return

    # 3. Fetch Matrix Data
    print("Fetching Matrix Data...")
    resp = SESSION.get(f'{BASE_URL}/api/matrix/data?page=1&pageSize=5')
    if resp.status_code == 200:
        data = resp.json()
        items = data.get('data', [])
        print(f"Matrix Data OK. Total: {data.get('total')}, Returned: {len(items)}")
        if items:
            print(f"First Matrix Item: {items[0].get('question_wiki_id')} - {items[0].get('product_name')}")
    else:
        print(f"Matrix Data FAILED: {resp.status_code} {resp.text}")

    # 4. Export Matrix
    print("Exporting Matrix...")
    resp = SESSION.get(f'{BASE_URL}/api/matrix/export')
    if resp.status_code == 200:
        print("GET /api/matrix/export: OK (Content-Type: {})".format(resp.headers.get('Content-Type')))
        # Save to file to verify
        with open('matrix_export_test.xlsx', 'wb') as f:
            f.write(resp.content)
        print("Saved matrix_export_test.xlsx")
    else:
        print(f"GET /api/matrix/export FAILED: {resp.status_code} {resp.text}")

def main():
    if login('admin', '123456'):
        # test_api_config()
        # test_scoring_prompt()
        test_matrix_sync_and_export()
    else:
        print("Aborting tests due to login failure")

if __name__ == '__main__':
    main()
