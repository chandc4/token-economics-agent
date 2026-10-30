import sqlite3
from pathlib import Path

db_path = Path.home() / '.local' / 'share' / 'opencode' / 'opencode.db'
if db_path.exists():
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cur.fetchall()]
    print('Tables:', tables)
    for t in ['session', 'project', 'message', 'part']:
        if t in tables:
            cur.execute(f"PRAGMA table_info({t});")
            cols = [c[1] for c in cur.fetchall()]
            cur.execute(f"SELECT COUNT(*) FROM {t};")
            cnt = cur.fetchone()[0]
            print(f"Table {t} ({cnt} rows):", cols)
            cur.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 2;")
            print(f"Sample from {t}:", cur.fetchall())
    conn.close()
