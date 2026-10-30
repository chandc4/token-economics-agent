import sqlite3
import json
from pathlib import Path

db_path = Path.home() / '.local' / 'share' / 'opencode' / 'opencode.db'
if db_path.exists():
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    cur = conn.cursor()
    cur.execute("SELECT data FROM session_message WHERE session_id = 'ses_e74a178bbffemBt1EGjaDPClWL' AND type = 'assistant' LIMIT 1;")
    raw = cur.fetchone()[0]
    data = json.loads(raw)
    print("Assistant Msg Keys:", list(data.keys()))
    if "parts" in data:
        print("Parts count in msg:", len(data["parts"]))
        for p in data["parts"]:
            print("Part type:", p.get("type"))
            if p.get("type") == "tool" or "tool" in p:
                print("Tool call found:", p)
    conn.close()
