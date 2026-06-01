import requests

try:
    response = requests.get('http://localhost:8080/api/scoring/data')
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Data length: {len(data)}")
        if len(data) > 0:
            print("First item:", data[0])
        else:
            print("Data is empty list []")
    else:
        print("Response:", response.text)
except Exception as e:
    print(f"Error: {e}")
