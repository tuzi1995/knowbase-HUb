import requests
import sys

url = "https://files.roborock.com/wiz/customer/video/78UngtrMEhk0qRRO6AcTgd/1RxktgpCYOlo5cQmngzGFM.mp4"

try:
    print(f"Testing URL: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    resp = requests.head(url, headers=headers, verify=False, timeout=10)
    print(f"Status Code: {resp.status_code}")
    print("Headers:")
    for k, v in resp.headers.items():
        print(f"  {k}: {v}")
        
    print("-" * 20)
    print("Testing Range Request (bytes=0-1024)")
    headers['Range'] = 'bytes=0-1024'
    resp = requests.get(url, headers=headers, verify=False, stream=True, timeout=10)
    print(f"Status Code: {resp.status_code}")
    print("Headers:")
    for k, v in resp.headers.items():
        print(f"  {k}: {v}")
    
    # Check if we can read content
    chunk = next(resp.iter_content(chunk_size=1024), None)
    if chunk:
        print(f"Read {len(chunk)} bytes successfully.")
    else:
        print("Failed to read content.")

except Exception as e:
    print(f"Error: {e}")
