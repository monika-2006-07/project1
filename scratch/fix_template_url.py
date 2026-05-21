import sqlite3
import os

upload_dir = os.path.join(os.path.dirname(__file__), "..", "static", "uploads")
latest = None
latest_mtime = 0
for name in os.listdir(upload_dir):
    if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        path = os.path.join(upload_dir, name)
        mtime = os.path.getmtime(path)
        if mtime > latest_mtime:
            latest_mtime = mtime
            latest = name

if latest:
    local = f"/static/uploads/{latest}"
    conn = sqlite3.connect("users.db")
    conn.execute(
        "UPDATE settings SET value = ? WHERE key = 'certificate_background_url'",
        (local,),
    )
    conn.commit()
    print("Set certificate_background_url to", local)
    conn.close()
