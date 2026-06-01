import pandas as pd
import requests
import io

# Create a sample DataFrame with NaN
data = {
    'question_wiki_id': ['test_1', 'test_2'],
    'question': ['Q1', 'Q2'],
    'answer': ['A1', None], # None in Python becomes NaN in pandas/numpy usually, but let's be explicit
    'if_bm25': [True, False],
    'similar_questions': ['["sq1"]', None]
}
df = pd.DataFrame(data)
# Introduce actual NaN
import numpy as np
df.loc[1, 'answer'] = np.nan

# Save to bytes
output = io.BytesIO()
with pd.ExcelWriter(output, engine='openpyxl') as writer:
    df.to_excel(writer, index=False)
output.seek(0)

# Send request
url = 'http://localhost:8080/api/kb/import'
files = {'file': ('test.xlsx', output, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}

# Login first to get cookie/session if needed, but the code uses @login_required.
# Wait, the test script needs to login.

session = requests.Session()
# Login
login_resp = session.post('http://localhost:8080/login', json={'username': 'admin', 'password': '123456'})
print(f"Login status: {login_resp.status_code}")

# Upload
resp = session.post(url, files=files)
print(f"Upload status: {resp.status_code}")
print(f"Upload response: {resp.text}")
