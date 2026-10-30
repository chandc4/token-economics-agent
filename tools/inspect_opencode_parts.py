import sqlite3
import json
from pathlib import Path

db_path = Path.home() / '.local' / 'share' / 'opencode' / 'opencode.db'
if db_path.exists():
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    cur = conn.cursor()
    cur.execute("SELECT id, title, cost, tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write, directory FROM session_v2 WHERE id = 'ses_e74a178bbffemBt1EGjaDPClWL';")
    print("Latest OpenCode Session Details:", cur.fetchone())

    cur.execute("SELECT type, data FROM session_part WHERE session_id = 'ses_e74a178bbffemBt1EGjaDPClWL' LIMIT 10;")
    parts = cur.fetchall()
    print(f"Parts count: {len(parts)}")
    for p in parts[:4]:
        print("Part type:", p[0])
        try:
            d = json.loads(p[1])
            print("Part data keys:", list(d.keys()))
            if "tool" in d or "name" in d or "toolCall" in d or "call" in d:
                print("Tool info:", d)
        except Exception:
            pass
    conn.close()
