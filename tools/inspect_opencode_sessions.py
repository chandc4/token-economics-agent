import sqlite3
from pathlib import Path

db_path = Path.home() / '.local' / 'share' / 'opencode' / 'opencode.db'
if db_path.exists():
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(session_v2);")
    print("session_v2 columns:", [c[1] for c in cur.fetchall()])
    cur.execute("SELECT id, project_id, title, time_created, time_updated FROM session_v2 ORDER BY time_updated DESC LIMIT 5;")
    for r in cur.fetchall():
        print("Session:", r)

    cur.execute("PRAGMA table_info(session_message);")
    print("\nsession_message columns:", [c[1] for c in cur.fetchall()])

    cur.execute("PRAGMA table_info(session_part);")
    print("\nsession_part columns:", [c[1] for c in cur.fetchall()])
    conn.close()
