import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import RECOGNITION_FIELD_POSITIONS

db = os.path.join(os.path.dirname(__file__), "..", "users.db")
conn = sqlite3.connect(db)
conn.execute(
    "UPDATE settings SET value = ? WHERE key = 'certificate_field_positions'",
    (json.dumps(RECOGNITION_FIELD_POSITIONS),),
)
conn.commit()
print("Updated field positions for Certificate of Recognition template")
conn.close()
