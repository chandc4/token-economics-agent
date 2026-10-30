import sqlite3
import json
from pathlib import Path

db_path = Path.home() / '.local' / 'share' / 'opencode' / 'opencode.db'
if db_path.exists():
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    cur = conn.cursor()
    cur.execute("SELECT data FROM session_message WHERE session_id = 'ses_e74a178bbffemBt1EGjaDPClWL' LIMIT 10;")
    for row in cur.fetchall():
        d = json.loads(row[0])
        print("Role/Agent:", d.get("agent"), "Tokens:", d.get("tokens"))
        if "content" in d:
            c = d["content"]
            if isinstance(c, list):
                for item in c:
                    print("Content block type:", type(item), list(item.keys()) if isinstance(item, dict) else item[:30])
    conn.close()
