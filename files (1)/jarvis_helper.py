"""
JARVIS Local Helper — runs on your Windows machine and gives the JARVIS web app
real control: opening apps, opening/searching files and folders, and running
your own whitelisted scripts.

HOW IT WORKS
------------
This starts a small web server on http://localhost:8765 that ONLY your own
computer can reach (it does not accept connections from other machines on
your network). JARVIS (running in your browser) sends it requests; this
script does the actual work and reports back.

SECURITY — READ THIS
---------------------
- A SECRET TOKEN protects this server. Anyone (any webpage, any script) that
  knows the token can ask this server to open programs, browse your files,
  or run scripts from the whitelisted folder. Keep the token private the
  same way you'd keep a password private.
- Change JARVIS_TOKEN below to your own random string before running this
  for real. Then paste that same token into JARVIS's settings panel.
- "Run script" only runs files that already exist inside the ./jarvis_scripts
  folder next to this file — it will NOT run arbitrary commands sent from
  the browser. Only put scripts in that folder that you wrote and trust.
- This server only listens on 127.0.0.1 (localhost), so it is not reachable
  from other devices on your network or the internet.

SETUP
-----
1. Install Python 3 from python.org if you don't already have it
   (tick "Add Python to PATH" during install).
2. Change JARVIS_TOKEN below to something private.
3. Open Command Prompt in this file's folder and run:
       python jarvis_helper.py
4. Leave that window open — it needs to keep running while you use JARVIS.
5. In JARVIS, open Settings (⚙) and enter:
       Helper URL:   http://localhost:8765
       Helper Token: (the same token you set below)

WHAT YOU CAN SAY TO JARVIS ONCE THIS IS RUNNING
------------------------------------------------
  "open app notepad"
  "open app chrome"
  "open folder C:\\Users\\you\\Documents"
  "open file C:\\Users\\you\\Documents\\notes.txt"
  "find file resume"                (searches your user folder)
  "run script backup.bat"           (must exist in .\\jarvis_scripts)
"""

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ============================================================
# EDIT THIS — set your own private token before running for real
# ============================================================
JARVIS_TOKEN = "changeme-to-your-own-secret"

PORT = 8765
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_scripts")
SEARCH_ROOT_DEFAULT = os.path.expanduser("~")
MAX_SEARCH_RESULTS = 20
MAX_FILES_SCANNED = 20000  # safety cap so a search can't run forever

# Common app name -> Windows launch command. Add your own here freely.
APP_ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "task manager": "taskmgr.exe",
    "control panel": "control.exe",
    "settings": "start ms-settings:",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "firefox": "firefox",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "spotify": "spotify",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
}


def ensure_scripts_dir():
    if not os.path.isdir(SCRIPTS_DIR):
        os.makedirs(SCRIPTS_DIR)
        readme = os.path.join(SCRIPTS_DIR, "README.txt")
        with open(readme, "w") as f:
            f.write(
                "Put .bat, .ps1, or .py scripts you've written and trust in this folder.\n"
                "Ask JARVIS to \"run script <filename>\" to execute one.\n"
                "Only scripts placed here by you can be run this way.\n"
            )


def open_app(name):
    key = name.strip().lower()
    cmd = APP_ALIASES.get(key)
    if cmd is None:
        # fall back to trying the raw name as a command (e.g. an exe on PATH)
        cmd = key
    try:
        if cmd.startswith("start "):
            subprocess.Popen(cmd, shell=True)
        else:
            subprocess.Popen(cmd, shell=True)
        return True, f"Launched {name}."
    except Exception as e:
        return False, f"Couldn't launch {name}: {e}"


def open_path(path):
    if not os.path.exists(path):
        return False, f"That path doesn't exist: {path}"
    try:
        os.startfile(path)  # Windows-only: opens file/folder with default handler
        return True, f"Opened {path}."
    except Exception as e:
        return False, f"Couldn't open {path}: {e}"


def search_files(query, root=None):
    root = root or SEARCH_ROOT_DEFAULT
    if not os.path.isdir(root):
        return False, f"Search folder doesn't exist: {root}", []
    query_lower = query.lower()
    results = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # skip noisy system-ish folders for speed
        dirnames[:] = [d for d in dirnames if d.lower() not in
                        {"node_modules", ".git", "__pycache__", "$recycle.bin", "windows"}]
        for fname in filenames:
            scanned += 1
            if scanned > MAX_FILES_SCANNED:
                break
            if query_lower in fname.lower():
                results.append(os.path.join(dirpath, fname))
                if len(results) >= MAX_SEARCH_RESULTS:
                    return True, f"Found {len(results)} match(es).", results
        if scanned > MAX_FILES_SCANNED:
            break
    if results:
        return True, f"Found {len(results)} match(es).", results
    return True, "No matching files found.", []


def run_script(name):
    ensure_scripts_dir()
    safe_name = os.path.basename(name)  # prevent path traversal like ..\..\
    full_path = os.path.join(SCRIPTS_DIR, safe_name)
    if not os.path.isfile(full_path):
        return False, f"No script named '{safe_name}' found in jarvis_scripts folder."
    ext = os.path.splitext(safe_name)[1].lower()
    try:
        if ext == ".bat" or ext == ".cmd":
            subprocess.Popen(["cmd.exe", "/c", full_path], shell=False)
        elif ext == ".ps1":
            subprocess.Popen(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", full_path],
                shell=False,
            )
        elif ext == ".py":
            subprocess.Popen([sys.executable, full_path], shell=False)
        else:
            return False, f"Unsupported script type: {ext}"
        return True, f"Running {safe_name}."
    except Exception as e:
        return False, f"Couldn't run {safe_name}: {e}"


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Jarvis-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_token(self):
        token = self.headers.get("X-Jarvis-Token", "")
        return token == JARVIS_TOKEN

    def do_OPTIONS(self):
        self._send_json(200, {"ok": True})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/status":
            self._send_json(200, {"status": "online", "app": "jarvis-helper"})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if not self._check_token():
            self._send_json(401, {"error": "invalid or missing token"})
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            data = {}

        if parsed.path == "/open-app":
            ok, msg = open_app(data.get("name", ""))
            self._send_json(200 if ok else 500, {"ok": ok, "message": msg})

        elif parsed.path == "/open-path":
            ok, msg = open_path(data.get("path", ""))
            self._send_json(200 if ok else 500, {"ok": ok, "message": msg})

        elif parsed.path == "/search-files":
            ok, msg, results = search_files(data.get("query", ""), data.get("root"))
            self._send_json(200 if ok else 500, {"ok": ok, "message": msg, "results": results})

        elif parsed.path == "/run-script":
            ok, msg = run_script(data.get("name", ""))
            self._send_json(200 if ok else 500, {"ok": ok, "message": msg})

        else:
            self._send_json(404, {"error": "unknown endpoint"})

    def log_message(self, format, *args):
        # quieter console output
        sys.stderr.write("[jarvis-helper] " + (format % args) + "\n")


def main():
    if JARVIS_TOKEN == "changeme-to-your-own-secret":
        print("=" * 60)
        print("WARNING: You're still using the default token.")
        print("Edit JARVIS_TOKEN near the top of this file before relying on this.")
        print("=" * 60)
    ensure_scripts_dir()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"JARVIS helper running at http://localhost:{PORT}")
    print(f"Scripts folder: {SCRIPTS_DIR}")
    print("Leave this window open while using JARVIS. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down JARVIS helper.")


if __name__ == "__main__":
    main()
