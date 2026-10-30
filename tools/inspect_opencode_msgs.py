import sqlite3
from pathlib import Path

db_path = Path.home() / '.local' / 'share' / 'opencode' / 'opencode.db'
if db_path.exists():
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    cur = conn.cursor()
    cur.execute("SELECT id, session_id, type, data FROM session_message WHERE session_id = 'ses_e74a178bbffemBt1EGjaDPClWL' LIMIT 6;")
    msgs = cur.fetchall()
    print("Messages count:", len(msgs))
    for m in msgs:
        print("Msg type:", m[2], "Data preview:", m[3][:120])
    conn.close()
