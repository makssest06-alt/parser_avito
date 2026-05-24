import sqlite3
c = sqlite3.connect('users.db').cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = c.fetchall()
for t in tables:
    name = t[0]
    count = c.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
    print(f"{name}: {count}")
    if count > 0:
        print(c.execute(f"SELECT * FROM {name} LIMIT 5").fetchall())
