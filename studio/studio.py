#!/usr/bin/env python3
"""carlodemarchis studio — the local backend behind carlodemarchis-site.

A single-file, dependency-free (stdlib only) content server:

  python3 studio/studio.py serve [--port 8766]   admin UI + JSON API on 127.0.0.1
  python3 studio/studio.py build                  render the static site into docs/
  python3 studio/studio.py export                 dump the database to content.json
  python3 studio/studio.py import                 load content.json into the database
  python3 studio/studio.py seed                   (re)seed from the 2025 portfolio

The SQLite file studio/studio.db is the working copy; content.json is the
git-tracked snapshot (export runs automatically after every build).
"""
import hashlib
import json
import mimetypes
import os
import sqlite3
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB = os.path.join(HERE, "studio.db")
SCHEMA = os.path.join(HERE, "schema.sql")
CACHE = os.path.join(HERE, "cache")
CONTENT = os.path.join(ROOT, "content.json")
DOCS = os.path.join(ROOT, "docs")
SOURCES = os.path.join(ROOT, "sources")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".webp", ".gif"}

# Editable columns per table (id / timestamps are managed here).
TABLES = {
    "projects": ["slug", "title", "subtitle", "year", "kind", "palette", "status",
                 "excerpt", "statement", "links", "sort_order", "featured"],
    "books": ["slug", "title", "subtitle", "year", "project_id", "status", "buy_url",
              "buy_label", "isbn", "format", "pages", "description", "sort_order"],
    "events": ["slug", "title", "kind", "venue", "city", "start_date", "end_date",
               "status", "description", "url", "project_ids", "sort_order"],
    "images": ["owner_type", "owner_id", "path", "role", "caption", "sort_order"],
    "notes": ["owner_type", "owner_id", "body", "done"],
}
TIMESTAMPED = {"projects", "books", "events"}

DEFAULT_SETTINGS = {
    "site_name": "carlodemarchis",
    "tagline": "photography beyond photography",
    "artist_name": "Carlo De Marchis",
    "city": "Torino, Italia",
    "bio": "",
    "email": "",
    "instagram": "",
    "medium": "",
    "linkedin": "",
    "domain": "",            # e.g. carlodemarchis.it -> writes docs/CNAME
    "base_url": "",          # public URL used for OG tags, e.g. https://carlodemarchis.it
    "umami_website_id": "",  # leave empty for no analytics
    "umami_src": "https://m.aguywithascarf.com/script.js",
    "source_root": os.path.expanduser("~/Documents/_cdm/_carlo/Art"),
}


# ---------------------------------------------------------------- database
def connect():
    fresh = not os.path.exists(DB)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    with open(SCHEMA) as f:
        con.executescript(f.read())
    if fresh:
        con.executemany("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", DEFAULT_SETTINGS.items())
        con.commit()
    return con


def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def get_settings(con):
    s = dict(DEFAULT_SETTINGS)
    s.update({r["key"]: r["value"] for r in con.execute("SELECT key,value FROM settings")})
    return s


def export_data(con=None):
    """Everything the site builder needs, as plain dicts."""
    con = con or connect()
    data = {"settings": get_settings(con)}
    for t in TABLES:
        order = "sort_order, id" if t != "notes" else "id"
        data[t] = rows(con, f"SELECT * FROM {t} ORDER BY {order}")
    return data


def export_json():
    data = export_data()
    with open(CONTENT, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    print(f"exported {sum(len(v) for k, v in data.items() if k != 'settings')} rows -> {CONTENT}")


def import_json():
    with open(CONTENT) as f:
        data = json.load(f)
    con = connect()
    for t in TABLES:
        con.execute(f"DELETE FROM {t}")
        for r in data.get(t, []):
            cols = [c for c in r if c in TABLES[t] or c in ("id", "created_at", "updated_at")]
            con.execute(f"INSERT INTO {t}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                        [r[c] for c in cols])
    con.execute("DELETE FROM settings")
    con.executemany("INSERT INTO settings(key,value) VALUES(?,?)", data.get("settings", {}).items())
    con.commit()
    print("imported", CONTENT)


def run_build():
    p = subprocess.run([sys.executable, os.path.join(ROOT, "build.py")], capture_output=True, text=True, cwd=ROOT)
    return p.returncode, (p.stdout + p.stderr)


# ---------------------------------------------------------------- thumbnails
def thumb(path, w=480):
    """A cached JPEG preview of any local image, made with macOS `sips`."""
    os.makedirs(CACHE, exist_ok=True)
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = hashlib.sha1(f"{path}|{st.st_mtime}|{st.st_size}|{w}".encode()).hexdigest()
    out = os.path.join(CACHE, key + ".jpg")
    if not os.path.exists(out):
        r = subprocess.run(["sips", "-Z", str(w), "-s", "format", "jpeg", "-s", "formatOptions", "70",
                            path, "--out", out], capture_output=True)
        if r.returncode != 0 or not os.path.exists(out):
            return None
    return out


# ---------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    server_version = "studio/1.0"

    # -- helpers
    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, ctype=None):
        if not path or not os.path.isfile(path):
            return self.send_json({"error": "not found"}, 404)
        ctype = ctype or mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def log_message(self, fmt, *args):  # quieter log
        if "/thumb" not in (args[0] if args else ""):
            sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

    # -- routing
    def route(self):
        u = urllib.parse.urlparse(self.path)
        return u.path.rstrip("/") or "/", dict(urllib.parse.parse_qsl(u.query))

    def do_GET(self):
        path, q = self.route()
        con = connect()
        if path == "/":
            return self.send_file(os.path.join(HERE, "admin.html"), "text/html; charset=utf-8")
        if path == "/api/settings":
            return self.send_json(get_settings(con))
        if path == "/api/all":
            return self.send_json(export_data(con))
        if path == "/thumb":
            return self.send_file(thumb(q.get("path", ""), int(q.get("w", 480))), "image/jpeg")
        if path == "/api/browse":
            return self.browse(con, q.get("dir", ""))
        if path.startswith("/site"):          # /site/ is an alias of the built site's root
            path = path[len("/site"):] or "/"
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "api" and parts[1] in TABLES:
            t = parts[1]
            if len(parts) == 3:
                r = rows(con, f"SELECT * FROM {t} WHERE id=?", (int(parts[2]),))
                return self.send_json(r[0]) if r else self.send_json({"error": "not found"}, 404)
            where, args = "", []
            if "owner_type" in q and t in ("images", "notes"):
                where = "WHERE owner_type=? AND owner_id=?"
                args = [q["owner_type"], int(q.get("owner_id", 0))]
            order = "sort_order, id" if t != "notes" else "done, id DESC"
            return self.send_json(rows(con, f"SELECT * FROM {t} {where} ORDER BY {order}", args))
        # anything else: the built site in docs/ (root-relative URLs, exactly as GitHub Pages serves it)
        full = os.path.normpath(os.path.join(DOCS, path.lstrip("/") or "index.html"))
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not full.startswith(DOCS):
            return self.send_json({"error": "forbidden"}, 403)
        if os.path.isfile(full):
            return self.send_file(full)
        self.send_file(os.path.join(DOCS, "404.html"), "text/html; charset=utf-8")

    def do_POST(self):
        path, _ = self.route()
        con = connect()
        if path == "/api/build":
            code, log = run_build()
            return self.send_json({"ok": code == 0, "log": log})
        if path == "/api/export":
            export_json()
            return self.send_json({"ok": True})
        if path == "/api/images/reorder":
            ids = self.body_json().get("ids", [])
            for i, iid in enumerate(ids):
                con.execute("UPDATE images SET sort_order=? WHERE id=?", (i, int(iid)))
            con.commit()
            return self.send_json({"ok": True})
        parts = path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "api" and parts[1] in TABLES:
            t = parts[1]
            body = self.body_json()
            cols = [c for c in TABLES[t] if c in body]
            vals = [norm(body[c]) for c in cols]
            cur = con.execute(f"INSERT INTO {t}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals)
            con.commit()
            return self.send_json(rows(con, f"SELECT * FROM {t} WHERE id=?", (cur.lastrowid,))[0], 201)
        self.send_json({"error": "not found"}, 404)

    def do_PUT(self):
        path, _ = self.route()
        con = connect()
        if path == "/api/settings":
            body = self.body_json()
            con.executemany("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                            [(k, str(v)) for k, v in body.items()])
            con.commit()
            return self.send_json(get_settings(con))
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] in TABLES:
            t, iid = parts[1], int(parts[2])
            body = self.body_json()
            cols = [c for c in TABLES[t] if c in body]
            if not cols:
                return self.send_json({"error": "nothing to update"}, 400)
            sets = ", ".join(f"{c}=?" for c in cols)
            if t in TIMESTAMPED:
                sets += ", updated_at=datetime('now')"
            con.execute(f"UPDATE {t} SET {sets} WHERE id=?", [norm(body[c]) for c in cols] + [iid])
            con.commit()
            r = rows(con, f"SELECT * FROM {t} WHERE id=?", (iid,))
            return self.send_json(r[0]) if r else self.send_json({"error": "not found"}, 404)
        self.send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        path, _ = self.route()
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] in TABLES:
            t, iid = parts[1], int(parts[2])
            con = connect()
            con.execute(f"DELETE FROM {t} WHERE id=?", (iid,))
            if t in ("projects", "books", "events"):
                con.execute("DELETE FROM images WHERE owner_type=? AND owner_id=?", (t[:-1], iid))
                con.execute("DELETE FROM notes WHERE owner_type=? AND owner_id=?", (t[:-1], iid))
            con.commit()
            return self.send_json({"ok": True})
        self.send_json({"error": "not found"}, 404)

    def browse(self, con, d):
        """File picker: only inside the configured source root or ./sources."""
        roots = [os.path.abspath(get_settings(con)["source_root"]), SOURCES]
        d = os.path.abspath(d) if d else roots[0]
        if not any(d == r or d.startswith(r + os.sep) for r in roots):
            d = roots[0]
        dirs, files = [], []
        try:
            for name in sorted(os.listdir(d), key=str.lower):
                if name.startswith("."):
                    continue
                full = os.path.join(d, name)
                if os.path.isdir(full):
                    dirs.append(name)
                elif os.path.splitext(name)[1].lower() in IMAGE_EXT:
                    files.append({"name": name, "path": full, "size": os.path.getsize(full)})
        except OSError as e:
            return self.send_json({"error": str(e)}, 400)
        parent = os.path.dirname(d) if any(d != r and d.startswith(r) for r in roots) else ""
        self.send_json({"dir": d, "parent": parent, "roots": roots, "dirs": dirs, "files": files})


def norm(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return int(v)
    return v


def serve(port):
    connect()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"studio: http://127.0.0.1:{port}/   (site preview at /site/)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "serve":
        port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8766
        serve(port)
    elif cmd == "build":
        code, log = run_build()
        print(log)
        sys.exit(code)
    elif cmd == "export":
        export_json()
    elif cmd == "import":
        import_json()
    elif cmd == "seed":
        sys.path.insert(0, HERE)
        import seed  # noqa
        seed.main()
    elif cmd == "init":
        connect()
        print("ok", DB)
    else:
        print(__doc__)
