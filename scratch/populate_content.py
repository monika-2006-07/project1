import sqlite3
import os

DB_PATH = "users.db"

def populate_content():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Sample lessons for Python (Course ID 1)
    python_lessons = [
        ("1. Getting Started with Python", 
         """<h3>What is Python?</h3>
<p>Python is a high-level, interpreted, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation.</p>
<p>Python is dynamically-typed and garbage-collected. It supports multiple programming paradigms, including structured, object-oriented and functional programming.</p>
<h4>Why Python?</h4>
<ul>
  <li>Easy to learn and read</li>
  <li>Large community and libraries</li>
  <li>Versatile (Web, Data Science, AI, Automation)</li>
</ul>
<pre><code>print("Hello World!")</code></pre>""", 
         "https://www.youtube.com/embed/kqtD5dpn9C8", 10),
        
        ("2. Python Variables & Data Types", 
         """<h3>Variables in Python</h3>
<p>Variables are containers for storing data values. In Python, a variable is created the moment you first assign a value to it.</p>
<pre><code>x = 5
y = "John"
print(x)
print(y)</code></pre>
<h4>Standard Data Types</h4>
<ul>
  <li><strong>Numbers:</strong> int, float, complex</li>
  <li><strong>Strings:</strong> str</li>
  <li><strong>Sequences:</strong> list, tuple, range</li>
  <li><strong>Mappings:</strong> dict</li>
  <li><strong>Sets:</strong> set, frozenset</li>
  <li><strong>Boolean:</strong> bool</li>
</ul>""", 
         "https://www.youtube.com/embed/VvXhN-XFvFA", 20),
    ]

    # Sample lessons for Fullstack (Course ID 3)
    fullstack_lessons = [
        ("1. The Modern Web Architecture", 
         """<h3>How the Web Works</h3>
<p>In a nutshell, the web is a client-server system. Your browser (client) makes a request to a server, which then sends back the files needed to render the page.</p>
<h4>The Three Pillars of Frontend</h4>
<ol>
  <li><strong>HTML:</strong> The structure of the page.</li>
  <li><strong>CSS:</strong> The style and layout.</li>
  <li><strong>JavaScript:</strong> The interactivity and logic.</li>
</ol>
<p>A Fullstack developer handles both this Frontend and the Backend (Server, Database, API).</p>""", 
         "https://www.youtube.com/embed/5UaT9V_35Y8", 10),
        
        ("2. HTML5: Semantic Structure", 
         """<h3>HTML Basics</h3>
<p>HTML stands for HyperText Markup Language. It is the standard markup language for documents designed to be displayed in a web browser.</p>
<pre><code>&lt;!DOCTYPE html&gt;
&lt;html&gt;
&lt;head&gt;
  &lt;title&gt;Page Title&lt;/title&gt;
&lt;/head&gt;
&lt;body&gt;
  &lt;h1&gt;This is a Heading&lt;/h1&gt;
  &lt;p&gt;This is a paragraph.&lt;/p&gt;
&lt;/body&gt;
&lt;/html&gt;</code></pre>""", 
         "https://www.youtube.com/embed/kUMe1FH4CHE", 20),
    ]

    # Insert Python lessons
    for title, content, video, order in python_lessons:
        cursor.execute("SELECT id FROM lessons WHERE course_id = 1 AND title = ?", (title,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO lessons (course_id, title, content, video_url, order_index) VALUES (?, ?, ?, ?, ?)",
                         (1, title, content, video, order))

    # Insert Fullstack lessons
    for title, content, video, order in fullstack_lessons:
        cursor.execute("SELECT id FROM lessons WHERE course_id = 3 AND title = ?", (title,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO lessons (course_id, title, content, video_url, order_index) VALUES (?, ?, ?, ?, ?)",
                         (3, title, content, video, order))

    conn.commit()
    conn.close()
    print("Sample content added successfully!")

if __name__ == "__main__":
    populate_content()
