import sqlite3
import json
from pathlib import Path

db_path = Path.home() / '.local' / 'share' / 'opencode' / 'opencode.db'
if db_path.exists():
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    cur = conn.cursor()
    cur.execute("SELECT data FROM session_message WHERE session_id = 'ses_e74a178bbffemBt1EGjaDPClWL' AND type = 'assistant' LIMIT 2;")
    for row in cur.fetchall():
        d = json.loads(row[0])
        for c in d.get("content", []):
            if c.get("type") not in ("text", "reasoning"):
                print("Actual action item:", json.dumps(c, indent=2))
                break
    conn.close()
