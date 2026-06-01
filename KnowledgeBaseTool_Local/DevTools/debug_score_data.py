
import sqlite3
import json
import os

# Connect to the database
db_path = os.path.join('instance', 'data.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Fetch a few records from kb_scores
try:
    cursor.execute("SELECT id, kb_id, total_score, score_data FROM kb_scores WHERE status='scored' LIMIT 5")
    rows = cursor.fetchall()
    
    print(f"Found {len(rows)} scored records.")
    for row in rows:
        id, kb_id, total_score, score_data = row
        print(f"ID: {id}, KB_ID: {kb_id}, Total: {total_score}")
        print(f"Score Data (Type: {type(score_data)}):")
        print(score_data)
        print("-" * 50)
        
        # Try parsing if it's a string
        if score_data and isinstance(score_data, str):
            try:
                parsed = json.loads(score_data)
                print("Parsed keys:", parsed.keys())
            except json.JSONDecodeError as e:
                print("JSON Decode Error:", e)

except Exception as e:
    print("Error:", e)
finally:
    conn.close()
