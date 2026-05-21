import sqlite3
c = sqlite3.connect("users.db")
for r in c.execute("SELECT key, value FROM settings WHERE key LIKE 'certificate%'"):
    print(r)
