from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, has_request_context
import sqlite3
import hashlib
import os
import json
from datetime import datetime
from werkzeug.utils import secure_filename

from certificate_render import (
    CERTIFICATE_FIELD_KEYS,
    config_from_admin_form,
    parse_field_config,
    render_certificate_image,
)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Use /tmp directory on Vercel because the root filesystem is read-only
if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
    DB_PATH = "/tmp/users.db"
else:
    DB_PATH = "users.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                punch_in  TIMESTAMP NOT NULL,
                punch_out TIMESTAMP,
                work_status TEXT DEFAULT NULL,   -- 'finished' | 'not_finished'
                reason      TEXT DEFAULT NULL,   -- filled when not_finished
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS work_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                priority TEXT DEFAULT 'medium',  -- 'low' | 'medium' | 'high'
                status TEXT DEFAULT 'pending',   -- 'pending' | 'in_progress' | 'completed'
                assigned_by INTEGER NOT NULL,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                due_date TEXT,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (assigned_by) REFERENCES admins(id)
            )
        """)
        # LMS Tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                thumbnail_url TEXT,
                creator_id INTEGER,
                creator_type TEXT DEFAULT 'admin', -- 'admin' or 'user'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                video_url TEXT,
                order_index INTEGER DEFAULT 0,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, course_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (course_id) REFERENCES courses(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_lesson_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, lesson_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (lesson_id) REFERENCES lessons(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS certificates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                certificate_code TEXT UNIQUE NOT NULL,
                issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (course_id) REFERENCES courses(id)
            )
        """)
        # Add columns to existing DB if upgrading from older version
        try:
            conn.execute("ALTER TABLE attendance ADD COLUMN work_status TEXT DEFAULT NULL")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE attendance ADD COLUMN reason TEXT DEFAULT NULL")
        except sqlite3.OperationalError:
            pass
        
        # Add email column to admins table if it doesn't exist
        try:
            conn.execute("ALTER TABLE admins ADD COLUMN email TEXT UNIQUE")
        except sqlite3.OperationalError:
            pass
        
        # Add created_at column to admins table if it doesn't exist
        try:
            conn.execute("ALTER TABLE admins ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError:
            pass
        
        try:
            conn.execute("ALTER TABLE courses ADD COLUMN creator_id INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE courses ADD COLUMN creator_type TEXT DEFAULT 'admin'")
        except sqlite3.OperationalError:
            pass
        
        # Create default admin if not exists
        try:
            admin_exists = conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
            if admin_exists == 0:
                conn.execute(
                    "INSERT INTO admins (username, email, password) VALUES (?, ?, ?)",
                    ("admin", "admin@example.com", hash_password("admin123")),
                )
        except sqlite3.OperationalError:
            # If admins table has different structure, recreate it
            conn.execute("DROP TABLE IF EXISTS admins")
            conn.execute("""
                CREATE TABLE admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute(
                "INSERT INTO admins (username, email, password) VALUES (?, ?, ?)",
                ("admin", "admin@example.com", hash_password("admin123")),
            )
        
        # Settings Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('academy_name', 'Learning Management Academy')")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('instructor_name', 'Course Instructor')")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('instructor_signature', 'Course Instructor')")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('director_name', 'Academic Director')")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('director_signature', 'Academic Director')")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('certificate_theme', 'template')")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('certificate_background_url', '/static/uploads/canva.webp')")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('certificate_aspect_ratio', '1.414')")
        default_fields = json.dumps(RECOGNITION_FIELD_POSITIONS)
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('certificate_field_positions', ?)", (default_fields,))
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('certificates_enabled', '1')")
        
        conn.commit()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def generate_certificate_code():
    """Generate a unique random code for certificates."""
    import string
    import random
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(12))


# Positions for "Certificate of Recognition" style (landscape, centered lines)
RECOGNITION_FIELD_POSITIONS = {
    "studentName": {
        "top": 51, "left": 50, "fontSize": "2.4rem",
        "fontFamily": "'Cormorant Garamond', 'Times New Roman', Georgia, serif",
        "fontWeight": "600", "color": "#111111", "textAlign": "center",
        "transform": "translateX(-50%) translateY(-100%)",
        "maxWidth": "55%", "lineHeight": "1",
    },
    "courseName": {
        "top": 64, "left": 50, "fontSize": "0.95rem",
        "fontFamily": "'Times New Roman', Georgia, serif",
        "fontWeight": "600", "color": "#111111", "textAlign": "center",
        "transform": "translateX(-50%)", "maxWidth": "50%",
        "letterSpacing": "0.1em", "lineHeight": "1.2",
    },
    "completionDate": {
        "top": 75, "left": 68.5, "fontSize": "1rem",
        "fontFamily": "'Times New Roman', Georgia, serif",
        "fontWeight": "600", "color": "#111111", "textAlign": "center",
        "transform": "translateX(-50%) translateY(-100%)",
        "lineHeight": "1",
    },
    "certificateId": {
        "top": 87, "left": 50, "fontSize": "0.48rem",
        "fontFamily": "'Times New Roman', Georgia, serif",
        "fontWeight": "400", "color": "#555555", "textAlign": "center",
        "transform": "translateX(-50%)",
        "lineHeight": "1",
    },
    "instructorName": {
        "top": 75, "left": 31.5, "fontSize": "1rem",
        "fontFamily": "'Times New Roman', Georgia, serif",
        "fontWeight": "600", "color": "#111111", "textAlign": "center",
        "transform": "translateX(-50%) translateY(-100%)",
        "lineHeight": "1",
    },
}

# Positions for Canva gold ribbon template (left-heavy layout)
CANVA_FIELD_POSITIONS = {
    "studentName": {"top": 48, "left": 62, "fontSize": "3.2rem", "fontFamily": "'Alex Brush', cursive", "fontWeight": "400", "color": "#111111", "textAlign": "center", "transform": "translateX(-50%)", "maxWidth": "42%"},
    "courseName": {"top": 58, "left": 62, "fontSize": "0.72rem", "fontFamily": "'Montserrat', sans-serif", "fontWeight": "400", "color": "#333333", "textAlign": "center", "transform": "translateX(-50%)", "maxWidth": "34%"},
    "completionDate": {"top": 76, "left": 17.5, "fontSize": "0.55rem", "fontFamily": "'Montserrat', sans-serif", "fontWeight": "600", "color": "#111111", "textAlign": "center", "transform": "translateX(-50%)"},
    "certificateId": {"top": 97, "left": 97, "fontSize": "0.55rem", "fontFamily": "monospace", "fontWeight": "400", "color": "#666666", "textAlign": "right", "transform": "none"},
    "instructorName": {"top": 89, "left": 48, "fontSize": "0.82rem", "fontFamily": "'Montserrat', sans-serif", "fontWeight": "700", "color": "#111111", "textAlign": "center", "transform": "translateX(-50%)"},
}

DEFAULT_CERTIFICATE_FIELD_POSITIONS = RECOGNITION_FIELD_POSITIONS


def field_positions_for_aspect_ratio(aspect_ratio):
    """Pick overlay layout preset from template proportions."""
    if aspect_ratio and aspect_ratio < 1.38:
        return RECOGNITION_FIELD_POSITIONS.copy()
    return CANVA_FIELD_POSITIONS.copy()


def load_settings(conn=None, sync_certificate_template=False):
    """Load all key-value settings from the database."""
    if conn is None:
        with get_db() as conn:
            if sync_certificate_template:
                sync_certificate_template_to_local_upload(conn)
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
    else:
        if sync_certificate_template:
            sync_certificate_template_to_local_upload(conn)
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


CERTIFICATE_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def get_certificate_uploads_dir():
    return os.path.join(app.root_path, "static", "uploads")


def get_latest_certificate_template_filename():
    """Return the most recently modified image in static/uploads."""
    upload_dir = get_certificate_uploads_dir()
    if not os.path.isdir(upload_dir):
        return None
    latest_name = None
    latest_mtime = 0
    for name in os.listdir(upload_dir):
        if name.lower().endswith(CERTIFICATE_IMAGE_EXTENSIONS):
            path = os.path.join(upload_dir, name)
            if os.path.isfile(path):
                mtime = os.path.getmtime(path)
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_name = name
    return latest_name


def is_direct_image_url(url):
    """True when URL points to an actual image file, not a Canva share/design page."""
    if not url:
        return False
    lower = url.lower().strip()
    if lower.startswith("/static/uploads/"):
        fname = lower.replace("/static/uploads/", "").split("?")[0]
        return os.path.isfile(os.path.join(get_certificate_uploads_dir(), fname))
    if "canva.link" in lower or ("canva.com" in lower and "/design" in lower):
        return False
    path = lower.split("?")[0]
    return path.endswith(CERTIFICATE_IMAGE_EXTENSIONS)


def absolute_certificate_static_url(filename):
    """Build a cache-busted URL for a file in static/uploads."""
    upload_dir = get_certificate_uploads_dir()
    if has_request_context():
        base = url_for("static", filename=f"uploads/{filename}", _external=True)
    else:
        base = f"/static/uploads/{filename}"
    path = os.path.join(upload_dir, filename)
    if os.path.isfile(path):
        return f"{base}?v={int(os.path.getmtime(path))}"
    return base


def sync_certificate_template_to_local_upload(conn=None):
    """
    Point certificate_background_url at the newest uploaded file.
    Fixes DB rows that still reference external/broken URLs.
    """
    upload_dir = get_certificate_uploads_dir()
    latest = get_latest_certificate_template_filename()
    if not latest:
        return None

    local_path = f"/static/uploads/{latest}"
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'certificate_background_url'"
        ).fetchone()
        current = (row["value"] if row else "") or ""
        file_ok = current.startswith("/static/uploads/") and os.path.isfile(
            os.path.join(upload_dir, current.replace("/static/uploads/", "").split("?")[0])
        )
        file_path = os.path.join(upload_dir, latest)
        aspect = detect_certificate_aspect_ratio(file_path)
        positions = field_positions_for_aspect_ratio(aspect)
        needs_sync = current != local_path or not file_ok or current.startswith("http")
        if needs_sync:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('certificate_background_url', ?)",
                (local_path,),
            )
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('certificate_aspect_ratio', ?)",
                (str(aspect),),
            )
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('certificate_field_positions', ?)",
                (json.dumps(positions),),
            )
            conn.commit()
    finally:
        if close_conn:
            conn.close()
    return local_path


def resolve_certificate_template_url(settings):
    """
    Use admin-uploaded files from static/uploads only.
    External image URLs are ignored when a local upload exists (they often block embedding).
    """
    upload_dir = get_certificate_uploads_dir()
    raw = (settings.get("certificate_background_url") or "").strip()

    if raw.startswith("/static/uploads/"):
        fname = raw.replace("/static/uploads/", "").split("?")[0]
        if os.path.isfile(os.path.join(upload_dir, fname)):
            return absolute_certificate_static_url(fname)

    latest = get_latest_certificate_template_filename()
    if latest:
        return absolute_certificate_static_url(latest)

    if os.path.isfile(os.path.join(upload_dir, "canva.webp")):
        return absolute_certificate_static_url("canva.webp")

    return absolute_certificate_static_url(latest) if latest else "/static/uploads/canva.webp"


def get_template_filesystem_path(settings):
    """Absolute path to the admin-uploaded certificate template image."""
    upload_dir = get_certificate_uploads_dir()
    raw = (settings.get("certificate_background_url") or "").strip()
    fname = None
    if raw.startswith("/static/uploads/"):
        fname = raw.replace("/static/uploads/", "").split("?")[0]
        if not os.path.isfile(os.path.join(upload_dir, fname)):
            fname = None
    if not fname:
        fname = get_latest_certificate_template_filename()
    if not fname:
        return None
    return os.path.join(upload_dir, fname)


def get_generated_certificates_dir():
    path = os.path.join(app.root_path, "static", "generated", "certificates")
    os.makedirs(path, exist_ok=True)
    return path


def _settings_config_version(settings):
    """Version stamp so we regenerate when template or field config changes."""
    parts = [
        settings.get("certificate_background_url", ""),
        settings.get("certificate_field_config", ""),
        settings.get("certificate_field_positions", ""),
        settings.get("instructor_name", ""),
        settings.get("director_name", ""),
    ]
    return hash("|".join(parts))


def ensure_certificate_image(cert, settings, force=False):
    """
    Render certificate as a flat image (template + replaced text).
    Returns URL path to the generated JPEG.
    """
    template_path = get_template_filesystem_path(settings)
    if not template_path:
        return None

    code = cert["certificate_code"]
    out_path = os.path.join(get_generated_certificates_dir(), f"{code}.jpg")
    cert_dict = dict(cert)

    config_version = _settings_config_version(settings)
    if (
        not force
        and os.path.isfile(out_path)
        and os.path.getmtime(out_path) >= os.path.getmtime(template_path)
    ):
        meta_path = out_path + ".meta"
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    if f.read().strip() == str(config_version):
                        return f"/static/generated/certificates/{code}.jpg?v={int(os.path.getmtime(out_path))}"
            except OSError:
                pass

    try:
        render_certificate_image(template_path, out_path, cert_dict, settings)
        with open(out_path + ".meta", "w", encoding="utf-8") as f:
            f.write(str(config_version))
        return f"/static/generated/certificates/{code}.jpg?v={int(os.path.getmtime(out_path))}"
    except Exception as exc:
        app.logger.error("Certificate render failed: %s", exc)
        return None


def detect_certificate_aspect_ratio(file_path):
    """Read image dimensions for accurate certificate scaling."""
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            w, h = img.size
            if h > 0:
                return round(w / h, 4)
    except Exception:
        pass
    return 1.414


def get_certificate_field_positions(settings):
    """Return field overlay positions (percent-based) for the uploaded template."""
    try:
        aspect_ratio = float(settings.get("certificate_aspect_ratio") or "1.414")
    except ValueError:
        aspect_ratio = 1.414
    base = field_positions_for_aspect_ratio(aspect_ratio)

    raw = settings.get("certificate_field_positions")
    if not raw:
        return base
    try:
        parsed = json.loads(raw)
        merged = base.copy()
        merged.update(parsed)
        return merged
    except (json.JSONDecodeError, TypeError):
        return base


def try_issue_certificate(conn, user_id, course_id):
    """Create a certificate when the user has completed every lesson in the course."""
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM lessons WHERE course_id = ?",
        (course_id,),
    ).fetchone()["c"]
    if total == 0:
        return None

    completed = conn.execute(
        """
        SELECT COUNT(*) AS c FROM user_lesson_progress up
        JOIN lessons l ON up.lesson_id = l.id
        WHERE up.user_id = ? AND l.course_id = ?
        """,
        (user_id, course_id),
    ).fetchone()["c"]

    if completed < total:
        return None

    existing = conn.execute(
        "SELECT certificate_code FROM certificates WHERE user_id = ? AND course_id = ?",
        (user_id, course_id),
    ).fetchone()
    if existing:
        return existing["certificate_code"]

    code = generate_certificate_code()
    conn.execute(
        "INSERT INTO certificates (user_id, course_id, certificate_code) VALUES (?, ?, ?)",
        (user_id, course_id, code),
    )
    conn.commit()

    cert_row = conn.execute(
        """
        SELECT cert.*, u.username, c.title AS course_title
        FROM certificates cert
        JOIN users u ON cert.user_id = u.id
        JOIN courses c ON cert.course_id = c.id
        WHERE cert.certificate_code = ?
        """,
        (code,),
    ).fetchone()
    if cert_row:
        settings = load_settings(conn)
        ensure_certificate_image(cert_row, settings, force=True)

    return code


def build_certificate_payload(cert_row, settings):
    """Build JSON payload for certificate preview / API."""
    image_url = ensure_certificate_image(cert_row, settings)
    template_url = resolve_certificate_template_url(settings)
    try:
        aspect_ratio = float(settings.get("certificate_aspect_ratio") or "1.414")
    except ValueError:
        aspect_ratio = 1.414

    issued = cert_row["issued_at"]
    if isinstance(issued, str) and len(issued) >= 10:
        completion_date = issued[:10]
    else:
        completion_date = str(issued)[:10] if issued else datetime.now().strftime("%Y-%m-%d")

    return {
        "certificateCode": cert_row["certificate_code"],
        "studentName": cert_row["username"],
        "courseName": (cert_row["course_title"] or "").upper(),
        "completionDate": completion_date,
        "instructorName": settings.get("instructor_name", "Course Instructor"),
        "founderName": settings.get("director_name", "Academic Director"),
        "generatedImageUrl": image_url,
        "templateUrl": template_url,
        "aspectRatio": aspect_ratio,
        "fields": parse_field_config(settings),
    }


# ── helpers ────────────────────────────────────────────────
def get_open_session(user_id):
    """Return the active (not yet punched-out) attendance row, or None."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM attendance WHERE user_id = ? AND punch_out IS NULL",
            (user_id,),
        ).fetchone()


def format_duration(punch_in_str, punch_out_str):
    """Return duration between two datetime strings as HH:MM:SS."""
    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        t_in  = datetime.strptime(punch_in_str,  fmt)
        t_out = datetime.strptime(punch_out_str, fmt)
        total_seconds = int((t_out - t_in).total_seconds())
        if total_seconds < 0:
            return "00:00:00"
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    except Exception:
        return "N/A"


def get_attendance_history(user_id):
    """Return all completed attendance records for the user, ordered by status then date."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, punch_in, punch_out, work_status, reason
               FROM attendance
               WHERE user_id = ? AND punch_out IS NOT NULL
               ORDER BY 
                   CASE 
                       WHEN work_status IS NULL THEN 1
                       WHEN work_status = 'not_finished' THEN 2
                       WHEN work_status = 'finished' THEN 3
                   END,
                   punch_in DESC""",
            (user_id,),
        ).fetchall()

    result = []
    for row in rows:
        result.append({
            "id":          row["id"],
            "punch_in":    row["punch_in"],
            "punch_out":   row["punch_out"],
            "duration":    format_duration(row["punch_in"], row["punch_out"]),
            "work_status": row["work_status"],
            "reason":      row["reason"],
        })
    return result


def auto_generate_lessons(course_id, course_title, course_description):
    title_lower = course_title.lower()
    lessons = []

    # 1. Python
    if "python" in title_lower:
        lessons = [
            {
                "title": "1. Getting Started with Python",
                "order_index": 10,
                "content": """<h3>Introduction to Python</h3>
<p>Python is a high-level, interpreted, general-purpose programming language. Created by Guido van Rossum and first released in 1991, Python's design philosophy emphasizes code readability with its notable use of significant whitespace.</p>

<h4>Why Choose Python?</h4>
<ul>
  <li>🚀 <strong>Clean &amp; Readable Syntax</strong> - Reads almost like plain English.</li>
  <li>🌍 <strong>High Demand</strong> - Heavily used in Data Science, Machine Learning, Web Development, Automation, and Scripting.</li>
  <li>📦 <strong>Rich Standard Library</strong> - Batteries included!</li>
</ul>

<h4>Your First Program</h4>
<p>In Python, printing to the screen is incredibly simple:</p>
<pre><code>print("Hello, World!")</code></pre>

<h4>Variables and Simple Output</h4>
<pre><code>name = "LMS Student"
age = 20
print(f"Hello {name}, you are {age} years old.")</code></pre>"""
            },
            {
                "title": "2. Control Flow and Conditionals",
                "order_index": 20,
                "content": """<h3>Making Decisions in Python</h3>
<p>Control flow allows your program to execute different branches of code depending on conditions. In Python, this is done using <code>if</code>, <code>elif</code>, and <code>else</code> statements.</p>

<h4>Conditional Syntax</h4>
<pre><code>score = 85

if score >= 90:
    print("Grade: A")
elif score >= 80:
    print("Grade: B")
else:
    print("Grade: C")</code></pre>

<h4>Important: Indentation</h4>
<p>Python uses <strong>indentation</strong> to define blocks of code, rather than curly braces <code>{}</code>. Always use 4 spaces per indentation level!</p>"""
            },
            {
                "title": "3. Python Loops &amp; Iteration",
                "order_index": 30,
                "content": """<h3>Repeating Actions with Loops</h3>
<p>Loops allow you to repeat a block of code multiple times. Python has two primary loop types: <code>for</code> loops and <code>while</code> loops.</p>

<h4>For Loops (Iterating over collections)</h4>
<pre><code>fruits = ["apple", "banana", "cherry"]
for fruit in fruits:
    print(f"I like {fruit}")</code></pre>

<h4>While Loops (Conditional execution)</h4>
<pre><code>count = 1
while count <= 5:
    print(f"Number: {count}")
    count += 1</code></pre>"""
            }
        ]
    # 2. Java
    elif "java" in title_lower:
        lessons = [
            {
                "title": "1. Introduction to Java &amp; JVM",
                "order_index": 10,
                "content": """<h3>The Java Platform</h3>
<p>Java is a robust, class-based, object-oriented programming language designed to have as few implementation dependencies as possible. Java's motto is <strong>"Write Once, Run Anywhere"</strong> (WORA), meaning compiled Java code can run on all platforms that support Java without the need for recompilation.</p>

<h4>Key Components</h4>
<ul>
  <li>☕ <strong>JVM (Java Virtual Machine)</strong> - Executes Java bytecode.</li>
  <li>📦 <strong>JRE (Java Runtime Environment)</strong> - Provides the libraries and resources to run applications.</li>
  <li>🛠️ <strong>JDK (Java Development Kit)</strong> - Includes JRE plus development tools like the compiler (<code>javac</code>).</li>
</ul>

<h4>Your First Java Program</h4>
<pre><code>public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}</code></pre>"""
            },
            {
                "title": "2. Object-Oriented Programming (OOP) in Java",
                "order_index": 20,
                "content": """<h3>Classes &amp; Objects</h3>
<p>Java is fundamentally object-oriented. Everything is associated with classes and objects, along with its attributes and methods.</p>

<h4>Defining a Class and Creating an Object</h4>
<pre><code>public class Car {
    String brand = "Tesla";
    
    public void honk() {
        System.out.println("Beep, beep!");
    }
    
    public static void main(String[] args) {
        Car myCar = new Car();
        System.out.println(myCar.brand);
        myCar.honk();
    }
}</code></pre>

<h4>The Four Pillars of OOP</h4>
<ol>
  <li>🔒 <strong>Encapsulation</strong> - Hiding data using private variables and public getters/setters.</li>
  <li>🌳 <strong>Inheritance</strong> - Acquiring fields and methods from a superclass using <code>extends</code>.</li>
  <li>🎭 <strong>Polymorphism</strong> - Allowing methods to take many forms (method overloading/overriding).</li>
  <li>🏢 <strong>Abstraction</strong> - Hiding complex implementation details using interfaces and abstract classes.</li>
</ol>"""
            }
        ]
    # 3. JavaScript / JS / React
    elif "javascript" in title_lower or "js" in title_lower or "react" in title_lower:
        lessons = [
            {
                "title": "1. Modern JavaScript (ES6+)",
                "order_index": 10,
                "content": """<h3>Modern JS Basics</h3>
<p>JavaScript is a versatile, lightweight, interpreted scripting language that powers the interactive behaviors of web pages. Standardized as ECMAScript, modern JS (ES6+) introduced clean features like arrow functions, classes, template literals, and destructuring.</p>

<h4>Variables and Arrow Functions</h4>
<pre><code>// Block scoped variables
const name = "Developer";
let status = "learning";

// Arrow functions
const greet = (user) => `Hello, ${user}!`;
console.log(greet(name));</code></pre>

<h4>Arrays and Objects Destructuring</h4>
<pre><code>const user = { username: "alice", email: "alice@example.com" };
const { username, email } = user;
console.log(username, email);</code></pre>"""
            },
            {
                "title": "2. DOM Manipulation &amp; Event Handling",
                "order_index": 20,
                "content": """<h3>Interacting with Web Pages</h3>
<p>The Document Object Model (DOM) is a programming interface for HTML documents. It represents the page so that programs can change the document structure, style, and content.</p>

<h4>Selecting Elements and Handling Events</h4>
<pre><code>// Select element
const button = document.querySelector('#action-btn');

// Add Event Listener
button.addEventListener('click', () => {
    button.style.backgroundColor = 'purple';
    button.textContent = 'Action Done! ✓';
});</code></pre>"""
            }
        ]
    # 4. HTML / CSS / Web
    elif "html" in title_lower or "css" in title_lower or "web" in title_lower:
        lessons = [
            {
                "title": "1. HTML5 Semantic Elements",
                "order_index": 10,
                "content": """<h3>Writing Structured markup</h3>
<p>Semantic HTML introduces meaning to the web page rather than just presentation. Element types like <code>&lt;header&gt;</code>, <code>&lt;nav&gt;</code>, <code>&lt;main&gt;</code>, <code>&lt;section&gt;</code>, and <code>&lt;footer&gt;</code> describe their contents clearly to both browsers and developer.</p>

<h4>Example Structure</h4>
<pre><code>&lt;main&gt;
  &lt;article&gt;
    &lt;header&gt;
      &lt;h1&gt;Semantic Web&lt;/h1&gt;
    &lt;/header&gt;
    &lt;p&gt;This is structured content.&lt;/p&gt;
  &lt;/article&gt;
&lt;/main&gt;</code></pre>"""
            },
            {
                "title": "2. CSS Layouts (Flexbox and Grid)",
                "order_index": 20,
                "content": """<h3>Creating Modern Layouts</h3>
<p>CSS layout engines make responsive and aligned designs straightforward. The two main layout mechanisms are <strong>Flexbox</strong> (for 1-dimensional layouts) and <strong>Grid</strong> (for 2-dimensional layouts).</p>

<h4>Flexbox Example</h4>
<pre><code>.container {
  display: flex;
  justify-content: space-between;
  align-items: center;
}</code></pre>

<h4>Grid Example</h4>
<pre><code>.grid-layout {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}</code></pre>"""
            }
        ]
    # 5. Database / SQL
    elif "sql" in title_lower or "db" in title_lower or "database" in title_lower:
        lessons = [
            {
                "title": "1. Intro to SQL &amp; Relational Databases",
                "order_index": 10,
                "content": """<h3>What is SQL?</h3>
<p>Structured Query Language (SQL) is the standard language for dealing with Relational Databases. It allows you to store, manipulate, and retrieve data efficiently.</p>

<h4>Basic Query Pattern</h4>
<pre><code>SELECT * FROM users WHERE age >= 18;</code></pre>"""
            },
            {
                "title": "2. Basic CRUD Operations",
                "order_index": 20,
                "content": """<h3>Manipulating Database Content</h3>
<p>CRUD stands for Create, Read, Update, and Delete. These represent the four essential operations of database storage.</p>

<h4>CRUD Examples</h4>
<pre><code>-- CREATE
INSERT INTO students (name, grade) VALUES ('John', 'A');

-- READ
SELECT name, grade FROM students;

-- UPDATE
UPDATE students SET grade = 'A+' WHERE name = 'John';

-- DELETE
DELETE FROM students WHERE name = 'John';</code></pre>"""
            }
        ]
    # 6. Fallback Generator (For any other custom topic!)
    else:
        lessons = [
            {
                "title": f"1. Introduction to {course_title}",
                "order_index": 10,
                "content": f"""<h3>Getting Started with {course_title}</h3>
<p>Welcome to <strong>{course_title}</strong>! This course is designed to guide you through the fundamental principles, essential skills, and advanced aspects of this subject.</p>

<h4>Course Overview &amp; Objectives</h4>
<p>{course_description if course_description else "In this lesson, we will lay down the foundation of this topic, cover key terminology, and build the initial mental model needed for success."}</p>

<h4>Key Areas of Focus</h4>
<ul>
  <li>📝 <strong>Core Fundamentals</strong> - Understanding the underlying building blocks.</li>
  <li>🛠️ <strong>Practical Applications</strong> - Learning how to apply these concepts in real-world scenarios.</li>
  <li>🚀 <strong>Best Practices</strong> - Adhering to standards and optimizing execution.</li>
</ul>

<h4>Summary</h4>
<p>By the end of this introductory unit, you will have a solid foundational grasp and be prepared to dive deeper into the technical mechanics of the next chapters.</p>"""
            },
            {
                "title": f"2. Core Concepts and Principles",
                "order_index": 20,
                "content": f"""<h3>Deep Dive into {course_title}</h3>
<p>Now that we have covered the basics, let's explore the core pillars and architectural systems that make <strong>{course_title}</strong> work.</p>

<h4>Important Frameworks and Methodologies</h4>
<p>Success in this topic depends on mastering its core tenets. Here is an overview of the key conceptual systems:</p>

<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;">
  <tr style="background:#4f46e5;color:white;"><th>Core Pillar</th><th>Description</th><th>Impact</th></tr>
  <tr><td><strong>Pillar 1: Theory</strong></td><td>The conceptual knowledge baseline.</td><td>Essential for decision-making.</td></tr>
  <tr><td><strong>Pillar 2: Tooling</strong></td><td>The software, hardware, or materials used.</td><td>Drives efficiency and speed.</td></tr>
  <tr><td><strong>Pillar 3: Workflow</strong></td><td>The step-by-step procedure.</td><td>Ensures consistency and quality.</td></tr>
</table>

<h4>Step-by-Step Implementation Guide</h4>
<ol>
  <li><strong>Analysis</strong>: Define the problem state and analyze constraints.</li>
  <li><strong>Design</strong>: Architect a solution and outline the methodology.</li>
  <li><strong>Execution</strong>: Put the plan into action and build the deliverables.</li>
  <li><strong>Iteration</strong>: Test, gather feedback, and continuously refine.</li>
</ol>"""
            },
            {
                "title": f"3. Next Steps &amp; Career Roadmap",
                "order_index": 30,
                "content": f"""<h3>Advancing Your Expertise</h3>
<p>Congratulations! You are building real competency in <strong>{course_title}</strong>. In this closing lesson, we will map out advanced learning resources and career paths.</p>

<h4>Continuing Your Learning Journey</h4>
<p>To master this topic, consider practicing with concrete projects, joining professional forums, and staying updated with industry trends.</p>

<h4>Recommended Practice Activities</h4>
<ul>
  <li>👨‍💻 <strong>Hands-on Labs</strong> - Experiment with active problem scenarios.</li>
  <li>👥 <strong>Collaborative Review</strong> - Peer-review work with others.</li>
  <li>📚 <strong>Case Studies</strong> - Analyze real-world success and failure profiles.</li>
</ul>

<div style="background:#f1f5f9; padding:1.25rem; border-radius:10px; border-left:4px solid #4f46e5; margin-top:1.5rem;">
  <strong>💡 Pro-Tip:</strong> The fastest way to gain expertise is through consistent daily practice. Pick one small concept from this unit and implement it today!
</div>"""
            }
        ]

    # Save generated lessons to database
    with get_db() as conn:
        for l in lessons:
            conn.execute(
                "INSERT INTO lessons (course_id, title, content, video_url, order_index) VALUES (?, ?, ?, ?, ?)",
                (course_id, l["title"], l["content"], None, l["order_index"])
            )
        conn.commit()


def convert_to_youtube_embed(url):
    if not url:
        return None
    
    url = url.strip()
    # If it is already an embed link, return as is
    if "youtube.com/embed/" in url:
        return url
        
    # Standard: youtube.com/watch?v=VIDEO_ID
    if "youtube.com/watch" in url:
        import urllib.parse as urlparse
        parsed = urlparse.urlparse(url)
        video_id = urlparse.parse_qs(parsed.query).get('v')
        if video_id:
            return f"https://www.youtube.com/embed/{video_id[0]}"
            
    # Shortened: youtu.be/VIDEO_ID
    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[-1].split("?")[0]
        if video_id:
            return f"https://www.youtube.com/embed/{video_id}"
            
    # YouTube Shorts: youtube.com/shorts/VIDEO_ID
    if "youtube.com/shorts/" in url:
        video_id = url.split("youtube.com/shorts/")[-1].split("?")[0]
        if video_id:
            return f"https://www.youtube.com/embed/{video_id}"
            
    return url


# ── auth routes ────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return render_template("signup.html")
        if len(username) < 3:
            flash("Username must be at least 3 characters.", "error")
            return render_template("signup.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("signup.html")
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")

        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                    (username, email, hash_password(password)),
                )
                conn.commit()
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username or email already exists.", "error")
            return render_template("signup.html")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if "admin_id" in session:
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        login_type = request.form.get("login_type", "user")
        identifier = request.form.get("identifier", "").strip()
        password   = request.form.get("password", "")

        if not identifier or not password:
            flash("Please fill in all fields.", "error")
            return render_template("login.html")

        with get_db() as conn:
            if login_type == "admin":
                user = conn.execute(
                    "SELECT * FROM admins WHERE username = ? OR email = ?",
                    (identifier, identifier),
                ).fetchone()
                
                if user and user["password"] == hash_password(password):
                    session["admin_id"]  = user["id"]
                    session["admin_username"] = user["username"]
                    flash(f"Welcome back, Admin {user['username']}!", "success")
                    return redirect(url_for("admin_dashboard"))
                else:
                    flash("Invalid admin credentials.", "error")
                    return render_template("login.html")
            else:
                user = conn.execute(
                    "SELECT * FROM users WHERE username = ? OR email = ?",
                    (identifier, identifier),
                ).fetchone()

                if user and user["password"] == hash_password(password):
                    session["user_id"]  = user["id"]
                    session["username"] = user["username"]
                    flash(f"Welcome back, {user['username']}!", "success")
                    return redirect(url_for("dashboard"))
                else:
                    flash("Invalid username/email or password.", "error")
                    return render_template("login.html")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ── admin dashboard ────────────────────────────────────────
@app.route("/admin/dashboard")
def admin_dashboard():
    if "admin_id" not in session:
        flash("Please log in as admin to access this page.", "error")
        return redirect(url_for("login"))

    # Get filter parameter
    filter_user_id = request.args.get("filter_user", "")

    with get_db() as conn:
        # Get all users and their current punch-in status
        users_raw = conn.execute("SELECT id, username, email, created_at FROM users ORDER BY created_at DESC").fetchall()
        users = []
        for u in users_raw:
            user_dict = dict(u)
            open_session = conn.execute(
                "SELECT * FROM attendance WHERE user_id = ? AND punch_out IS NULL", 
                (u["id"],)
            ).fetchone()
            user_dict["is_punched_in"] = open_session is not None
            users.append(user_dict)
        
        # Get all attendance records with user info (with optional filter)
        if filter_user_id:
            attendance_records = conn.execute("""
                SELECT a.*, u.username, u.email
                FROM attendance a
                JOIN users u ON a.user_id = u.id
                WHERE a.user_id = ?
                ORDER BY 
                    CASE 
                        WHEN a.punch_out IS NULL THEN 0
                        WHEN a.work_status IS NULL THEN 1
                        WHEN a.work_status = 'not_finished' THEN 2
                        WHEN a.work_status = 'finished' THEN 3
                    END,
                    a.punch_in DESC
            """, (filter_user_id,)).fetchall()
        else:
            attendance_records = conn.execute("""
                SELECT a.*, u.username, u.email
                FROM attendance a
                JOIN users u ON a.user_id = u.id
                ORDER BY 
                    CASE 
                        WHEN a.punch_out IS NULL THEN 0
                        WHEN a.work_status IS NULL THEN 1
                        WHEN a.work_status = 'not_finished' THEN 2
                        WHEN a.work_status = 'finished' THEN 3
                    END,
                    a.punch_in DESC
                LIMIT 100
            """).fetchall()
        
        # Get all work assignments with user info
        work_assignments = conn.execute("""
            SELECT w.*, u.username, u.email
            FROM work_assignments w
            JOIN users u ON w.user_id = u.id
            ORDER BY w.assigned_at DESC
        """).fetchall()
        
        # Calculate total work duration for each user
        user_work_stats = {}
        for user in users:
            # Get all completed attendance records for this user
            completed_records = conn.execute("""
                SELECT punch_in, punch_out
                FROM attendance
                WHERE user_id = ? AND punch_out IS NOT NULL
            """, (user["id"],)).fetchall()
            
            total_seconds = 0
            for record in completed_records:
                duration_seconds = calculate_duration_seconds(record["punch_in"], record["punch_out"])
                total_seconds += duration_seconds
            
            # Convert to hours, minutes, and seconds
            total_hours = total_seconds // 3600
            total_minutes = (total_seconds % 3600) // 60
            remaining_seconds = total_seconds % 60
            
            user_work_stats[user["id"]] = {
                "username": user["username"],
                "total_hours": total_hours,
                "total_minutes": total_minutes,
                "total_seconds": total_seconds,
                "remaining_seconds": remaining_seconds,
                "total_records": len(completed_records),
                "formatted": f"{total_hours}h {total_minutes}m {remaining_seconds}s"
            }
        
        # Get all enrollments with progress for admin dashboard
        enrollments_raw = conn.execute("""
            SELECT e.*, u.username, c.title as course_title,
            (SELECT COUNT(*) FROM lessons WHERE course_id = e.course_id) as total_lessons,
            (SELECT COUNT(*) FROM user_lesson_progress up 
             JOIN lessons l ON up.lesson_id = l.id 
             WHERE up.user_id = e.user_id AND l.course_id = e.course_id) as completed_lessons
            FROM enrollments e
            JOIN users u ON e.user_id = u.id
            JOIN courses c ON e.course_id = c.id
            ORDER BY e.enrolled_at DESC
        """).fetchall()
        
        enrollments = []
        for e in enrollments_raw:
            enroll_dict = dict(e)
            enroll_dict["progress"] = int((e["completed_lessons"] / e["total_lessons"] * 100)) if e["total_lessons"] > 0 else 0
            enrollments.append(enroll_dict)
        
        # Format attendance records
        formatted_records = []
        for record in attendance_records:
            formatted_records.append({
                "id": record["id"],
                "user_id": record["user_id"],
                "username": record["username"],
                "email": record["email"],
                "punch_in": record["punch_in"],
                "punch_out": record["punch_out"],
                "duration": format_duration(record["punch_in"], record["punch_out"]) if record["punch_out"] else "In Progress",
                "work_status": record["work_status"],
                "reason": record["reason"],
            })

    return render_template(
        "admin_dashboard.html",
        admin_username=session["admin_username"],
        users=users,
        attendance_records=formatted_records,
        work_assignments=work_assignments,
        user_work_stats=user_work_stats,
        enrollments=enrollments,
        filter_user_id=int(filter_user_id) if filter_user_id else None,
    )


def calculate_duration_seconds(punch_in_str, punch_out_str):
    """Calculate duration in seconds between two datetime strings."""
    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        t_in = datetime.strptime(punch_in_str, fmt)
        t_out = datetime.strptime(punch_out_str, fmt)
        total_seconds = int((t_out - t_in).total_seconds())
        return max(0, total_seconds)
    except Exception:
        return 0


# ── admin assign work ──────────────────────────────────────
@app.route("/admin/assign_work", methods=["POST"])
def assign_work():
    if "admin_id" not in session:
        flash("Please log in as admin to access this page.", "error")
        return redirect(url_for("login"))

    user_id = request.form.get("user_id", "").strip()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    priority = request.form.get("priority", "medium")
    due_date = request.form.get("due_date", "").strip()

    if not user_id or not title:
        flash("User and title are required.", "error")
        return redirect(url_for("admin_dashboard"))

    with get_db() as conn:
        conn.execute(
            """INSERT INTO work_assignments 
               (user_id, title, description, priority, assigned_by, due_date) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, title, description, priority, session["admin_id"], due_date if due_date else None),
        )
        conn.commit()

    flash("Work assigned successfully!", "success")
    return redirect(url_for("admin_dashboard"))


# ── admin update assignment status ────────────────────────
@app.route("/admin/update_assignment/<int:assignment_id>", methods=["POST"])
def update_assignment_status(assignment_id):
    if "admin_id" not in session:
        flash("Please log in as admin to access this page.", "error")
        return redirect(url_for("login"))

    status = request.form.get("status", "")
    
    if status not in ("pending", "in_progress", "completed"):
        flash("Invalid status.", "error")
        return redirect(url_for("admin_dashboard"))

    with get_db() as conn:
        if status == "completed":
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "UPDATE work_assignments SET status = ?, completed_at = ? WHERE id = ?",
                (status, now, assignment_id),
            )
        else:
            conn.execute(
                "UPDATE work_assignments SET status = ? WHERE id = ?",
                (status, assignment_id),
            )
        conn.commit()

    flash("Assignment status updated!", "success")
    return redirect(url_for("admin_dashboard"))


# ── admin create user ──────────────────────────────────────
@app.route("/admin/create_user", methods=["POST"])
def admin_create_user():
    if "admin_id" not in session:
        flash("Please log in as admin to access this page.", "error")
        return redirect(url_for("login"))

    username = request.form.get("username", "").strip()
    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not username or not email or not password:
        flash("All fields are required.", "error")
        return redirect(url_for("admin_dashboard", _anchor="users"))
    if len(username) < 3:
        flash("Username must be at least 3 characters.", "error")
        return redirect(url_for("admin_dashboard", _anchor="users"))
    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("admin_dashboard", _anchor="users"))

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (username, email, hash_password(password)),
            )
            conn.commit()
        flash(f"User '{username}' created successfully!", "success")
    except sqlite3.IntegrityError:
        flash("Username or email already exists.", "error")

    return redirect(url_for("admin_dashboard", _anchor="users"))


# ── admin edit user ────────────────────────────────────────
@app.route("/admin/edit_user/<int:user_id>", methods=["GET", "POST"])
def admin_edit_user(user_id):
    if "admin_id" not in session:
        flash("Please log in as admin to access this page.", "error")
        return redirect(url_for("login"))

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    if not user:
        flash("User not found.", "error")
        return redirect(url_for("admin_dashboard", _anchor="users"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not username or not email:
            flash("Username and email are required.", "error")
            return render_template("admin_edit_user.html", user=user)

        try:
            with get_db() as conn:
                if password:
                    conn.execute(
                        "UPDATE users SET username = ?, email = ?, password = ? WHERE id = ?",
                        (username, email, hash_password(password), user_id),
                    )
                else:
                    conn.execute(
                        "UPDATE users SET username = ?, email = ? WHERE id = ?",
                        (username, email, user_id),
                    )
                conn.commit()
            flash(f"User '{username}' updated successfully!", "success")
            return redirect(url_for("admin_dashboard", _anchor="users"))
        except sqlite3.IntegrityError:
            flash("Username or email already exists.", "error")

    return render_template("admin_edit_user.html", user=user)


# ── admin delete assignment ────────────────────────────────
@app.route("/admin/delete_assignment/<int:assignment_id>", methods=["POST"])
def delete_assignment(assignment_id):
    if "admin_id" not in session:
        flash("Please log in as admin to access this page.", "error")
        return redirect(url_for("login"))

    with get_db() as conn:
        conn.execute("DELETE FROM work_assignments WHERE id = ?", (assignment_id,))
        conn.commit()

    flash("Assignment deleted successfully!", "success")
    return redirect(url_for("admin_dashboard"))


# ── dashboard ──────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please log in to access the dashboard.", "error")
        return redirect(url_for("login"))

    user_id      = session["user_id"]
    open_session = get_open_session(user_id)
    history      = get_attendance_history(user_id)
    
    # Get assigned work for the user
    with get_db() as conn:
        assignments = conn.execute(
            """SELECT * FROM work_assignments 
               WHERE user_id = ? 
               ORDER BY 
                   CASE status 
                       WHEN 'pending' THEN 1 
                       WHEN 'in_progress' THEN 2 
                       WHEN 'completed' THEN 3 
                   END,
                   assigned_at DESC""",
            (user_id,),
        ).fetchall()

        certs_enabled_row = conn.execute("SELECT value FROM settings WHERE key = 'certificates_enabled'").fetchone()
        certs_enabled = certs_enabled_row and certs_enabled_row['value'] == '1'
        certificate_previews = []
        if certs_enabled:
            sync_certificate_template_to_local_upload(conn)
            settings = load_settings(conn)
            certs_raw = conn.execute(
                """
                SELECT cert.*, u.username, c.title AS course_title
                FROM certificates cert
                JOIN users u ON cert.user_id = u.id
                JOIN courses c ON cert.course_id = c.id
                WHERE cert.user_id = ?
                ORDER BY cert.issued_at DESC
                LIMIT 6
                """,
                (user_id,),
            ).fetchall()
            certificate_previews = [
                build_certificate_payload(dict(row), settings) for row in certs_raw
            ]

    is_punched_in = open_session is not None

    return render_template(
        "dashboard.html",
        username=session["username"],
        open_session=open_session,
        history=history,
        assignments=assignments,
        is_punched_in=is_punched_in,
        certificates_enabled=certs_enabled,
        certificate_previews=certificate_previews,
    )


# ── edit profile ───────────────────────────────────────────
@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    if "user_id" not in session:
        flash("Please log in to access this page.", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not username or not email:
            flash("Username and email are required.", "error")
            return render_template("edit_profile.html", user=user)

        try:
            with get_db() as conn:
                if password:
                    conn.execute(
                        "UPDATE users SET username = ?, email = ?, password = ? WHERE id = ?",
                        (username, email, hash_password(password), user_id),
                    )
                else:
                    conn.execute(
                        "UPDATE users SET username = ?, email = ? WHERE id = ?",
                        (username, email, user_id),
                    )
                conn.commit()
            session["username"] = username  # Update session username
            flash("Profile updated successfully!", "success")
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("Username or email already exists.", "error")

    return render_template("edit_profile.html", user=user)


# ── user update assignment status ──────────────────────────
@app.route("/update_my_assignment/<int:assignment_id>", methods=["POST"])
def update_my_assignment(assignment_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    status = request.form.get("status", "")
    
    if status not in ("in_progress", "completed"):
        flash("Invalid status.", "error")
        return redirect(url_for("dashboard"))

    # Check if user is currently punched in
    user_id = session["user_id"]
    open_session = get_open_session(user_id)
    
    if not open_session:
        flash("You must be punched in to update task status.", "error")
        return redirect(url_for("dashboard"))

    with get_db() as conn:
        # Verify the assignment belongs to the user
        assignment = conn.execute(
            "SELECT * FROM work_assignments WHERE id = ? AND user_id = ?",
            (assignment_id, session["user_id"]),
        ).fetchone()
        
        if not assignment:
            flash("Assignment not found.", "error")
            return redirect(url_for("dashboard"))
        
        if status == "completed":
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "UPDATE work_assignments SET status = ?, completed_at = ? WHERE id = ?",
                (status, now, assignment_id),
            )
        else:
            conn.execute(
                "UPDATE work_assignments SET status = ? WHERE id = ?",
                (status, assignment_id),
            )
        conn.commit()

    flash("Assignment status updated!", "success")
    return redirect(url_for("dashboard"))


# ── punch in ──────────────────────────────────────────────
@app.route("/punch_in", methods=["POST"])
def punch_in():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    if get_open_session(user_id):
        flash("You are already punched in.", "error")
        return redirect(url_for("dashboard"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO attendance (user_id, punch_in) VALUES (?, ?)",
            (user_id, now),
        )
        conn.commit()

    flash(f"Punched in at {now}.", "success")
    return redirect(url_for("dashboard"))


# ── punch out → goes to work status page ──────────────────
@app.route("/punch_out", methods=["POST"])
def punch_out():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id      = session["user_id"]
    open_session = get_open_session(user_id)

    if not open_session:
        flash("You are not currently punched in.", "error")
        return redirect(url_for("dashboard"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            "UPDATE attendance SET punch_out = ? WHERE id = ?",
            (now, open_session["id"]),
        )
        conn.commit()

    # Redirect to work-status form, passing the attendance record id
    return redirect(url_for("work_status", attendance_id=open_session["id"]))


# ── work status form ──────────────────────────────────────
@app.route("/work_status/<int:attendance_id>", methods=["GET", "POST"])
def work_status(attendance_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        status = request.form.get("work_status", "")
        reason = request.form.get("reason", "").strip()

        if status not in ("finished", "not_finished"):
            flash("Please select a work status.", "error")
            return render_template("work_status.html", attendance_id=attendance_id)

        if status == "not_finished" and not reason:
            flash("Please provide a reason for not finishing.", "error")
            return render_template("work_status.html", attendance_id=attendance_id)

        with get_db() as conn:
            conn.execute(
                "UPDATE attendance SET work_status = ?, reason = ? WHERE id = ? AND user_id = ?",
                (status, reason if status == "not_finished" else None,
                 attendance_id, session["user_id"]),
            )
            conn.commit()

        if status == "finished":
            flash("Great work! Shift marked as finished.", "success")
        else:
            flash("Shift marked as not finished. Reason recorded.", "success")

        return redirect(url_for("dashboard"))

    return render_template("work_status.html", attendance_id=attendance_id)


# ── LMS Routes (Admin) ──────────────────────────────────────
@app.route("/admin/courses", methods=["GET", "POST"])
def admin_courses():
    if "admin_id" not in session:
        flash("Please log in as admin to access this page.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        thumbnail_url = request.form.get("thumbnail_url", "").strip()

        if not title:
            flash("Title is required.", "error")
        else:
            with get_db() as conn:
                cursor = conn.execute(
                    "INSERT INTO courses (title, description, thumbnail_url, creator_id, creator_type) VALUES (?, ?, ?, ?, ?)",
                    (title, description, thumbnail_url if thumbnail_url else None, session["admin_id"], 'admin'),
                )
                course_id = cursor.lastrowid
                conn.commit()
            
            # Automatically generate lessons
            auto_generate_lessons(course_id, title, description)
            flash("Course created successfully with automatic lessons!", "success")
        return redirect(url_for("admin_courses"))

    with get_db() as conn:
        courses = conn.execute("SELECT * FROM courses ORDER BY created_at DESC").fetchall()
    return render_template("admin_courses.html", courses=courses)


@app.route("/admin/course/delete/<int:course_id>", methods=["POST"])
def delete_course(course_id):
    if "admin_id" not in session:
        return redirect(url_for("login"))

    with get_db() as conn:
        conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
        conn.commit()
    flash("Course deleted successfully!", "success")
    return redirect(url_for("admin_courses"))


@app.route("/admin/course/<int:course_id>/lessons", methods=["GET", "POST"])
def admin_lessons(course_id):
    if "admin_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        video_url = convert_to_youtube_embed(request.form.get("video_url", "").strip())
        order_index = request.form.get("order_index", 0)

        if not title:
            flash("Title is required.", "error")
        else:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO lessons (course_id, title, content, video_url, order_index) VALUES (?, ?, ?, ?, ?)",
                    (course_id, title, content, video_url if video_url else None, order_index),
                )
                conn.commit()
            flash("Lesson added successfully!", "success")
        return redirect(url_for("admin_lessons", course_id=course_id))

    with get_db() as conn:
        course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        lessons = conn.execute("SELECT * FROM lessons WHERE course_id = ? ORDER BY order_index ASC", (course_id,)).fetchall()
    
    if not course:
        flash("Course not found.", "error")
        return redirect(url_for("admin_courses"))

    return render_template("admin_lessons.html", course=course, lessons=lessons)


@app.route("/admin/lesson/delete/<int:lesson_id>", methods=["POST"])
def delete_lesson(lesson_id):
    if "admin_id" not in session:
        return redirect(url_for("login"))

    with get_db() as conn:
        lesson = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if lesson:
            course_id = lesson["course_id"]
            conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
            conn.commit()
            flash("Lesson deleted successfully!", "success")
            return redirect(url_for("admin_lessons", course_id=course_id))
    
    flash("Lesson not found.", "error")
    return redirect(url_for("admin_courses"))


@app.route("/admin/lesson/edit/<int:lesson_id>", methods=["GET", "POST"])
def edit_lesson(lesson_id):
    if "admin_id" not in session:
        return redirect(url_for("login"))

    with get_db() as conn:
        lesson = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if not lesson:
            flash("Lesson not found.", "error")
            return redirect(url_for("admin_courses"))

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            content = request.form.get("content", "").strip()
            video_url = convert_to_youtube_embed(request.form.get("video_url", "").strip())
            order_index = request.form.get("order_index", 0)

            if not title:
                flash("Title is required.", "error")
            else:
                conn.execute(
                    "UPDATE lessons SET title = ?, content = ?, video_url = ?, order_index = ? WHERE id = ?",
                    (title, content, video_url if video_url else None, order_index, lesson_id),
                )
                conn.commit()
                flash("Lesson updated successfully!", "success")
                return redirect(url_for("admin_lessons", course_id=lesson["course_id"]))

        course = conn.execute("SELECT * FROM courses WHERE id = ?", (lesson["course_id"],)).fetchone()

    return render_template("edit_lesson.html", lesson=lesson, course=course)


# ── LMS Routes (User) ───────────────────────────────────────
@app.route("/courses")
def courses():
    if "user_id" not in session:
        flash("Please log in to browse courses.", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    with get_db() as conn:
        # Get only admin-created courses
        courses_raw = conn.execute(
            "SELECT * FROM courses WHERE creator_type = 'admin' OR creator_type IS NULL ORDER BY created_at DESC"
        ).fetchall()
        courses = []
        for c in courses_raw:
            course_dict = dict(c)
            enrollment = conn.execute(
                "SELECT id FROM enrollments WHERE user_id = ? AND course_id = ?",
                (user_id, c["id"])
            ).fetchone()
            course_dict["is_enrolled"] = enrollment is not None
            
            # Progress calculation
            if course_dict["is_enrolled"]:
                total_lessons = conn.execute("SELECT COUNT(*) FROM lessons WHERE course_id = ?", (c["id"],)).fetchone()[0]
                completed_lessons = conn.execute(
                    """SELECT COUNT(*) FROM user_lesson_progress up
                       JOIN lessons l ON up.lesson_id = l.id
                       WHERE up.user_id = ? AND l.course_id = ?""",
                    (user_id, c["id"])
                ).fetchone()[0]
                course_dict["progress"] = int((completed_lessons / total_lessons * 100)) if total_lessons > 0 else 0
            
            courses.append(course_dict)

    return render_template("courses.html", courses=courses)


@app.route("/course/enroll/<int:course_id>", methods=["POST"])
def enroll_course(course_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO enrollments (user_id, course_id) VALUES (?, ?)",
                (user_id, course_id)
            )
            conn.commit()
        flash("Enrolled successfully!", "success")
    except sqlite3.IntegrityError:
        flash("You are already enrolled in this course.", "error")
    
    return redirect(url_for("courses"))


@app.route("/course/<int:course_id>")
def view_course(course_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    with get_db() as conn:
        course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            flash("Course not found.", "error")
            return redirect(url_for("courses"))

        enrollment = conn.execute(
            "SELECT id FROM enrollments WHERE user_id = ? AND course_id = ?",
            (user_id, course_id)
        ).fetchone()

        is_enrolled = enrollment is not None

        lessons_raw = conn.execute(
            "SELECT * FROM lessons WHERE course_id = ? ORDER BY order_index ASC",
            (course_id,)
        ).fetchall()
        
        lessons = []
        for l in lessons_raw:
            lesson_dict = dict(l)
            if is_enrolled:
                progress = conn.execute(
                    "SELECT completed_at FROM user_lesson_progress WHERE user_id = ? AND lesson_id = ?",
                    (user_id, l["id"])
                ).fetchone()
                lesson_dict["is_completed"] = progress is not None
            else:
                lesson_dict["is_completed"] = False
            lessons.append(lesson_dict)

        certificate_code = None
        if is_enrolled and lessons:
            certificate_code = try_issue_certificate(conn, user_id, course_id)

    return render_template("course_view.html", course=course, lessons=lessons, is_enrolled=is_enrolled, certificate_code=certificate_code)


@app.route("/lesson/<int:lesson_id>")
def view_lesson(lesson_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    with get_db() as conn:
        lesson = conn.execute("""
            SELECT l.*, c.title as course_title 
            FROM lessons l 
            JOIN courses c ON l.course_id = c.id 
            WHERE l.id = ?
        """, (lesson_id,)).fetchone()
        
        if not lesson:
            flash("Lesson not found.", "error")
            return redirect(url_for("courses"))

        # Verify enrollment
        enrollment = conn.execute(
            "SELECT id FROM enrollments WHERE user_id = ? AND course_id = ?",
            (user_id, lesson["course_id"])
        ).fetchone()

        if not enrollment:
            flash("Please enroll in the course first.", "error")
            return redirect(url_for("courses"))

        progress = conn.execute(
            "SELECT completed_at FROM user_lesson_progress WHERE user_id = ? AND lesson_id = ?",
            (user_id, lesson_id)
        ).fetchone()
        
        # Get next lesson if any
        next_lesson = conn.execute(
            "SELECT id FROM lessons WHERE course_id = ? AND order_index > ? ORDER BY order_index ASC LIMIT 1",
            (lesson["course_id"], lesson["order_index"])
        ).fetchone()

    return render_template(
        "lesson_view.html", 
        lesson=lesson, 
        is_completed=progress is not None,
        next_lesson_id=next_lesson["id"] if next_lesson else None
    )


@app.route("/lesson/complete/<int:lesson_id>", methods=["POST"])
def complete_lesson(lesson_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    with get_db() as conn:
        lesson = conn.execute("SELECT course_id FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if lesson:
            try:
                conn.execute(
                    "INSERT INTO user_lesson_progress (user_id, lesson_id) VALUES (?, ?)",
                    (user_id, lesson_id)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass  # Already completed

            try_issue_certificate(conn, user_id, lesson["course_id"])
            return redirect(url_for("view_course", course_id=lesson["course_id"]))
    
    return redirect(url_for("courses"))


@app.route("/lesson/complete-and-next/<int:lesson_id>/<int:next_lesson_id>", methods=["POST"])
def complete_and_next_lesson(lesson_id, next_lesson_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO user_lesson_progress (user_id, lesson_id) VALUES (?, ?)",
                (user_id, lesson_id)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # Already completed

        lesson = conn.execute("SELECT course_id FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if lesson:
            try_issue_certificate(conn, user_id, lesson["course_id"])

    return redirect(url_for("view_lesson", lesson_id=next_lesson_id))






@app.route("/admin/certificates")
def admin_certificates():
    if "admin_id" not in session:
        return redirect(url_for("login"))

    with get_db() as conn:
        # Get all enrollments where completion is 100%
        # A bit complex in SQL, so we'll fetch and filter
        enrollments = conn.execute("""
            SELECT e.*, u.username, u.email, c.title as course_title,
            (SELECT COUNT(*) FROM lessons WHERE course_id = e.course_id) as total_lessons,
            (SELECT COUNT(*) FROM user_lesson_progress up 
             JOIN lessons l ON up.lesson_id = l.id 
             WHERE up.user_id = e.user_id AND l.course_id = e.course_id) as completed_lessons,
            (SELECT id FROM certificates WHERE user_id = e.user_id AND course_id = e.course_id) as cert_id
            FROM enrollments e
            JOIN users u ON e.user_id = u.id
            JOIN courses c ON e.course_id = c.id
        """).fetchall()
        
        completed_enrollments = []
        for e in enrollments:
            if e["total_lessons"] > 0 and e["total_lessons"] == e["completed_lessons"]:
                completed_enrollments.append(e)

        sync_certificate_template_to_local_upload(conn)
        settings = load_settings(conn)
        template_preview_url = resolve_certificate_template_url(settings)
        active_template_file = get_latest_certificate_template_filename()
        field_config = parse_field_config(settings)
        field_config_json = json.dumps({"fields": field_config})
        enabled_row = conn.execute("SELECT value FROM settings WHERE key = 'certificates_enabled'").fetchone()
        certificates_enabled = enabled_row and enabled_row['value'] == '1'

    return render_template(
        "admin_certificates.html",
        enrollments=completed_enrollments,
        settings=settings,
        template_preview_url=template_preview_url,
        active_template_file=active_template_file,
        field_config=field_config,
        field_config_json=field_config_json,
        field_keys=CERTIFICATE_FIELD_KEYS,
        certificates_enabled=certificates_enabled,
    )


@app.route("/admin/toggle_certificates", methods=["POST"])
def toggle_certificates():
    if "admin_id" not in session:
        return redirect(url_for("login"))
    with get_db() as conn:
        current = conn.execute("SELECT value FROM settings WHERE key = 'certificates_enabled'").fetchone()
        new_val = '0' if (current and current['value'] == '1') else '1'
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('certificates_enabled', ?)", (new_val,))
        conn.commit()
    status = "enabled" if new_val == '1' else "disabled"
    flash(f"Certificates have been {status}.", "success")
    return redirect(url_for("admin_certificates"))


@app.route("/admin/settings/certificate", methods=["POST"])
def update_certificate_settings():
    if "admin_id" not in session:
        return redirect(url_for("login"))
        
    academy_name = request.form.get("academy_name", "").strip()
    instructor_name = request.form.get("instructor_name", "").strip()
    instructor_signature = request.form.get("instructor_signature", "").strip()
    director_name = request.form.get("director_name", "").strip()
    director_signature = request.form.get("director_signature", "").strip()
    certificate_theme = request.form.get("certificate_theme", "classic_gold").strip()
    
    allowed_themes = ["template", "canva_gold", "custom"]
    if certificate_theme not in allowed_themes:
        certificate_theme = "template"

    custom_bg = request.files.get("custom_background")
    custom_bg_path = None
    aspect_ratio_update = None
    template_changed = False

    if custom_bg and custom_bg.filename:
        upload_dir = get_certificate_uploads_dir()
        os.makedirs(upload_dir, exist_ok=True)
        base = secure_filename(custom_bg.filename)
        if not base.lower().endswith(CERTIFICATE_IMAGE_EXTENSIONS):
            flash("Please upload a PNG, JPG, or WebP image file.", "error")
            return redirect(url_for("admin_certificates"))
        filename = f"cert_{int(datetime.now().timestamp())}_{base}"
        file_path = os.path.join(upload_dir, filename)
        custom_bg.save(file_path)
        custom_bg_path = f"/static/uploads/{filename}"
        aspect_val = detect_certificate_aspect_ratio(file_path)
        aspect_ratio_update = str(aspect_val)
        template_changed = True

    with get_db() as conn:
        if not (custom_bg and custom_bg.filename):
            sync_certificate_template_to_local_upload(conn)

        settings_before = load_settings(conn)
        field_config = config_from_admin_form(request.form, settings_before)
        field_config_json = json.dumps(field_config)

        conn.execute("UPDATE settings SET value = ? WHERE key = 'academy_name'", (academy_name,))
        conn.execute("UPDATE settings SET value = ? WHERE key = 'instructor_name'", (instructor_name,))
        conn.execute("UPDATE settings SET value = ? WHERE key = 'instructor_signature'", (instructor_signature,))
        conn.execute("UPDATE settings SET value = ? WHERE key = 'director_name'", (director_name,))
        conn.execute("UPDATE settings SET value = ? WHERE key = 'director_signature'", (director_signature,))
        conn.execute("UPDATE settings SET value = ? WHERE key = 'certificate_theme'", (certificate_theme,))
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('certificate_field_config', ?)",
            (field_config_json,),
        )

        if custom_bg_path:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('certificate_background_url', ?)",
                (custom_bg_path,),
            )
        if aspect_ratio_update:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('certificate_aspect_ratio', ?)",
                (aspect_ratio_update,),
            )

        conn.commit()

        if template_changed:
            gen_dir = get_generated_certificates_dir()
            for name in os.listdir(gen_dir):
                if name.endswith((".jpg", ".jpeg", ".meta")):
                    try:
                        os.remove(os.path.join(gen_dir, name))
                    except OSError:
                        pass

    flash("Certificate template saved. Drag boxes on the preview if text areas need adjustment.", "success")
    return redirect(url_for("admin_certificates"))


@app.route("/admin/issue_certificate/<int:user_id>/<int:course_id>", methods=["POST"])
def issue_certificate(user_id, course_id):
    if "admin_id" not in session:
        return redirect(url_for("login"))

    code = generate_certificate_code()
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO certificates (user_id, course_id, certificate_code) VALUES (?, ?, ?)",
                (user_id, course_id, code)
            )
            conn.commit()
            cert_row = conn.execute(
                """
                SELECT cert.*, u.username, c.title AS course_title
                FROM certificates cert
                JOIN users u ON cert.user_id = u.id
                JOIN courses c ON cert.course_id = c.id
                WHERE cert.certificate_code = ?
                """,
                (code,),
            ).fetchone()
            if cert_row:
                settings = load_settings(conn)
                ensure_certificate_image(cert_row, settings, force=True)
        flash("Certificate issued successfully!", "success")
    except sqlite3.IntegrityError:
        flash("Certificate already exists for this user/course.", "error")
    
    return redirect(url_for("admin_certificates"))


@app.route("/my_certificates")
def my_certificates():
    if "user_id" not in session:
        return redirect(url_for("login"))
    with get_db() as conn:
        enabled = conn.execute("SELECT value FROM settings WHERE key = 'certificates_enabled'").fetchone()
        if not enabled or enabled['value'] != '1':
            flash("Certificates are currently disabled.", "error")
            return redirect(url_for("dashboard"))

    user_id = session["user_id"]
    with get_db() as conn:
        sync_certificate_template_to_local_upload(conn)
        settings = load_settings(conn)
        certs = conn.execute(
            """
            SELECT cert.*, u.username, c.title AS course_title, c.description AS course_desc
            FROM certificates cert
            JOIN users u ON cert.user_id = u.id
            JOIN courses c ON cert.course_id = c.id
            WHERE cert.user_id = ?
            ORDER BY cert.issued_at DESC
            """,
            (user_id,),
        ).fetchall()
        certificate_previews = [
            build_certificate_payload(dict(row), settings) for row in certs
        ]
    return render_template(
        "user_certificates.html",
        certificates=certs,
        certificate_previews=certificate_previews,
    )


def fetch_certificate_by_code(code):
    with get_db() as conn:
        cert = conn.execute(
            """
            SELECT cert.*, u.username, c.title AS course_title
            FROM certificates cert
            JOIN users u ON cert.user_id = u.id
            JOIN courses c ON cert.course_id = c.id
            WHERE cert.certificate_code = ?
            """,
            (code,),
        ).fetchone()
        if not cert:
            return None, None
        sync_certificate_template_to_local_upload(conn)
        settings = load_settings(conn)
        return cert, settings


@app.route("/api/certificate/<string:code>")
def api_certificate(code):
    cert, settings = fetch_certificate_by_code(code)
    if not cert:
        return jsonify({"error": "Certificate not found"}), 404
    return jsonify(build_certificate_payload(cert, settings))


@app.route("/certificate/view/<string:code>")
def view_certificate(code):
    with get_db() as conn:
        enabled = conn.execute("SELECT value FROM settings WHERE key = 'certificates_enabled'").fetchone()
        if not enabled or enabled['value'] != '1':
            flash("Certificates are currently disabled.", "error")
            return redirect(url_for("index"))
    cert, settings = fetch_certificate_by_code(code)
    if not cert:
        flash("Invalid certificate code.", "error")
        return redirect(url_for("index"))

    image_url = ensure_certificate_image(cert, settings, force=request.args.get("refresh") == "1")
    if not image_url:
        flash("Could not generate certificate. Ask admin to upload a valid template.", "error")
        return redirect(url_for("index"))

    return render_template(
        "certificate_image.html",
        cert=cert,
        image_url=image_url,
        certificate_code=code,
    )


# ── User Course Creation Routes ─────────────────────────────
@app.route("/my-courses")
def my_created_courses():
    if "user_id" not in session:
        flash("Please log in to view your courses.", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    with get_db() as conn:
        courses = conn.execute(
            "SELECT * FROM courses WHERE creator_id = ? AND creator_type = 'user' ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return render_template("user_my_courses.html", courses=courses)


@app.route("/create-course", methods=["GET", "POST"])
def user_create_course():
    if "user_id" not in session:
        flash("Please log in to create a course.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        thumbnail_url = request.form.get("thumbnail_url", "").strip()

        if not title:
            flash("Course title is required.", "error")
            return render_template("user_create_course.html")

        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO courses (title, description, thumbnail_url, creator_id, creator_type) VALUES (?, ?, ?, ?, ?)",
                (title, description, thumbnail_url if thumbnail_url else None, session["user_id"], "user"),
            )
            course_id = cursor.lastrowid
            conn.commit()

        # Automatically generate starting lessons
        auto_generate_lessons(course_id, title, description)
        flash("Course created successfully with automatic starting lessons!", "success")
        return redirect(url_for("user_manage_lessons", course_id=course_id))

    return render_template("user_create_course.html")


@app.route("/my-course/<int:course_id>/lessons", methods=["GET", "POST"])
def user_manage_lessons(course_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    with get_db() as conn:
        course = conn.execute(
            "SELECT * FROM courses WHERE id = ? AND creator_id = ? AND creator_type = 'user'",
            (course_id, user_id),
        ).fetchone()

    if not course:
        flash("Course not found or you don't have permission.", "error")
        return redirect(url_for("my_created_courses"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        video_url = convert_to_youtube_embed(request.form.get("video_url", "").strip())
        order_index = request.form.get("order_index", 0)

        if not title:
            flash("Lesson title is required.", "error")
        else:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO lessons (course_id, title, content, video_url, order_index) VALUES (?, ?, ?, ?, ?)",
                    (course_id, title, content, video_url if video_url else None, order_index),
                )
                conn.commit()
            flash("Lesson added to your course!", "success")
        # Redirect with anchor so browser scrolls to the existing lessons list
        return redirect(url_for("user_manage_lessons", course_id=course_id, _anchor="lessons"))

    with get_db() as conn:
        lessons = conn.execute(
            "SELECT * FROM lessons WHERE course_id = ? ORDER BY order_index ASC",
            (course_id,),
        ).fetchall()

    return render_template("user_manage_lessons.html", course=course, lessons=lessons)


@app.route("/my-course/lesson/delete/<int:lesson_id>", methods=["POST"])
def user_delete_lesson(lesson_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    with get_db() as conn:
        lesson = conn.execute(
            """SELECT l.*, c.creator_id FROM lessons l
               JOIN courses c ON l.course_id = c.id
               WHERE l.id = ?""",
            (lesson_id,),
        ).fetchone()

        if lesson and lesson["creator_id"] == user_id:
            course_id = lesson["course_id"]
            conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
            conn.commit()
            flash("Lesson deleted.", "success")
            return redirect(url_for("user_manage_lessons", course_id=course_id, _anchor="lessons"))

    flash("Lesson not found.", "error")
    return redirect(url_for("my_created_courses"))


# Initialize database when the module is imported (required for Vercel/WSGI deployments)
init_db()

if __name__ == "__main__":
    app.run(debug=True)
