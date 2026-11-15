#!/usr/bin/env python3
# path: ephemeral_paste/server.py
# context: Python 3.15 / ephemeral_paste / secure self-destructing pastebin
import sys
import os
import time
import secrets
import sqlite3
import json
import html
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pastes.db")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pastes (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL,
                burn_on_read INTEGER NOT NULL DEFAULT 0,
                views INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()

def cleanup_loop():
    while True:
        try:
            now = time.time()
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("DELETE FROM pastes WHERE expires_at IS NOT NULL AND expires_at < ?", (now,))
                conn.commit()
        except Exception:
            pass
        time.sleep(60)

class PasteHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def send_json(self, status: int, data: dict):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            index_path = os.path.join(STATIC_DIR, "index.html")
            with open(index_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if self.path.startswith('/p/'):
            paste_id = self.path[3:].split('?')[0]
            self.serve_paste(paste_id)
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def serve_paste(self, paste_id: str):
        now = time.time()
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT content, burn_on_read, expires_at FROM pastes WHERE id = ?", (paste_id,))
            row = cursor.fetchone()

            if not row:
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(b"<h1>404 - Secret Not Found or Already Burned</h1>")
                return

            content, burn_on_read, expires_at = row

            if expires_at and now > expires_at:
                cursor.execute("DELETE FROM pastes WHERE id = ?", (paste_id,))
                conn.commit()
                self.send_response(410)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(b"<h1>410 - This paste has expired</h1>")
                return

            if burn_on_read:
                cursor.execute("DELETE FROM pastes WHERE id = ?", (paste_id,))
                conn.commit()
                burn_warning = "<p style='color:#ef4444; font-weight:bold;'>🔥 This secret was burned upon reading and is now permanently deleted.</p>"
            else:
                cursor.execute("UPDATE pastes SET views = views + 1 WHERE id = ?", (paste_id,))
                conn.commit()
                burn_warning = ""

        escaped = html.escape(content)
        page = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Secure Paste - {paste_id}</title>
    <style>
        body {{ background:#090d16; color:#f3f4f6; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding:40px; display:flex; justify-content:center; }}
        .box {{ max-width:800px; width:100%; background:#121824; border:1px solid #232c3d; border-radius:8px; padding:24px; }}
        pre {{ background:#0b0f19; padding:16px; border-radius:6px; overflow-x:auto; font-family:Consolas, monospace; border:1px solid #232c3d; }}
        a {{ color:#6366f1; text-decoration:none; display:inline-block; margin-top:16px; }}
    </style>
</head>
<body>
    <div class="box">
        <h2>🔒 Decrypted Paste View</h2>
        {burn_warning}
        <pre>{escaped}</pre>
        <a href="/">← Create a new secret</a>
    </div>
</body>
</html>"""
        encoded = page.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        if self.path == '/api/paste':
            content_len = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_len).decode('utf-8')
            try:
                data = json.loads(raw_body)
            except Exception:
                self.send_json(400, {"error": "Invalid JSON"})
                return

            text = data.get("content", "").strip()
            if not text:
                self.send_json(400, {"error": "Content cannot be empty"})
                return

            ttl_val = data.get("ttl", "burn")
            burn_on_read = (ttl_val == "burn")
            now = time.time()
            expires_at = None if burn_on_read else (now + float(ttl_val))

            paste_id = secrets.token_urlsafe(8)
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute(
                    "INSERT INTO pastes (id, content, created_at, expires_at, burn_on_read) VALUES (?, ?, ?, ?, ?)",
                    (paste_id, text, now, expires_at, 1 if burn_on_read else 0)
                )
                conn.commit()

            host = self.headers.get('Host', '127.0.0.1:8080')
            full_url = f"http://{host}/p/{paste_id}"

            self.send_json(201, {"id": paste_id, "url": full_url, "burn": burn_on_read})
            return

        self.send_json(404, {"error": "Endpoint not found"})

def run_server(port: int = 8080):
    init_db()
    t = threading.Thread(target=cleanup_loop, daemon=True)
    t.start()

    server = HTTPServer(('127.0.0.1', port), PasteHandler)
    print(f"\n[🔒] Ephemeral Paste running at: http://127.0.0.1:{port}/")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server stopped.")
    finally:
        server.server_close()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port)
