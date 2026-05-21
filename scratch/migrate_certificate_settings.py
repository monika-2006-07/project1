import json
import sqlite3

DEFAULT_FIELDS = {
    "studentName": {"top": 48, "left": 62, "fontSize": "3.2rem", "fontFamily": "'Alex Brush', cursive", "fontWeight": "400", "color": "#111111", "textAlign": "center", "transform": "translateX(-50%)", "maxWidth": "42%"},
    "courseName": {"top": 58, "left": 62, "fontSize": "0.72rem", "fontFamily": "'Montserrat', sans-serif", "fontWeight": "400", "color": "#333333", "textAlign": "center", "transform": "translateX(-50%)", "maxWidth": "34%"},
    "completionDate": {"top": 76, "left": 17.5, "fontSize": "0.55rem", "fontFamily": "'Montserrat', sans-serif", "fontWeight": "600", "color": "#111111", "textAlign": "center", "transform": "translateX(-50%)"},
    "certificateId": {"top": 97, "left": 97, "fontSize": "0.55rem", "fontFamily": "monospace", "fontWeight": "400", "color": "#666666", "textAlign": "right", "transform": "none"},
    "instructorName": {"top": 89, "left": 48, "fontSize": "0.82rem", "fontFamily": "'Montserrat', sans-serif", "fontWeight": "700", "color": "#111111", "textAlign": "center", "transform": "translateX(-50%)"},
}

conn = sqlite3.connect("users.db")
for key, value in [
    ("certificate_aspect_ratio", "1.414"),
    ("certificate_field_positions", json.dumps(DEFAULT_FIELDS)),
    ("certificate_theme", "template"),
]:
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
conn.commit()
conn.close()
print("Migration done.")
