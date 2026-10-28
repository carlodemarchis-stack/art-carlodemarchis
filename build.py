#!/usr/bin/env python3
"""Render the static site from the studio database into docs/ (GitHub Pages).

  python3 build.py            full build (images are cached; only new/changed sources are resized)
  python3 build.py --no-images  skip image derivatives (fast template-only rebuild)

Needs: python3 with jinja2 (system python has it) and macOS `sips` for image resizing.
"""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "studio"))
import studio  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
IMG = os.path.join(DOCS, "img")
LARGE, THUMB = 2000, 900
QUALITY = "82"
NO_IMAGES = "--no-images" in sys.argv


# ---------------------------------------------------------------- images
def sips_dims(path):
    r = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", path], capture_output=True, text=True)
    m = re.findall(r"pixel(Width|Height): (\d+)", r.stdout)
    d = {k: int(v) for k, v in m}
    return d.get("Width", 0), d.get("Height", 0)


def derive(src, dst, maxpx):
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    r = subprocess.run(["sips", "-Z", str(maxpx), "-s", "format", "jpeg", "-s", "formatOptions", QUALITY,
                        src, "--out", dst], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst):
        print(f"  ! sips could not convert {src}: {r.stderr.strip().splitlines()[0] if r.stderr.strip() else 'unknown error'}")
        return False
    return True


def process_images(images):
    """Add url/thumb/w/h to every image record; returns the set of files kept."""
    keep, made = set(), 0
    for im in images:
        src = im["path"]
        if not os.path.isfile(src):
            print(f"  ! missing source, skipped: {src}")
            im["missing"] = True
            continue
        key = f"{im['id']}-{hashlib.sha1(src.encode()).hexdigest()[:6]}"
        folder = os.path.join(IMG, im["owner_type"])
        large, thumb = os.path.join(folder, key + ".jpg"), os.path.join(folder, key + "-s.jpg")
        if not NO_IMAGES:
            made += derive(src, large, LARGE)
            derive(src, thumb, THUMB)
        if not os.path.exists(large):
            im["missing"] = True
            continue
        im["w"], im["h"] = sips_dims(large)
        im["url"] = f"/img/{im['owner_type']}/{key}.jpg"
        im["thumb"] = f"/img/{im['owner_type']}/{key}-s.jpg"
        im["name"] = os.path.basename(src)
        keep.update({large, thumb})
    if not NO_IMAGES:
        for dp, _, fn in os.walk(IMG):
            for f in fn:
                full = os.path.join(dp, f)
                if full not in keep:
                    os.remove(full)
    print(f"  images: {len(keep)//2} in use, {made} newly resized")


# ---------------------------------------------------------------- text helpers
REDACT = re.compile("▇+")


def redact(s):
    """'▇▇▇' runs become black bars (the redaction motif of the prompt titles)."""
    out, pos = [], 0
    s = str(s)
    for m in REDACT.finditer(s):
        out.append(html.escape(s[pos:m.start()]))
        out.append(f'<span class="redact" style="--n:{len(m.group())}" aria-label="redacted"></span>')
        pos = m.end()
    out.append(html.escape(s[pos:]))
    return Markup("".join(out))


INLINE = [(re.compile(r"\*\*(.+?)\*\*"), r"<strong>\1</strong>"),
          (re.compile(r"\[(.+?)\]\((https?://[^)\s]+)\)"), r'<a href="\2" rel="noopener">\1</a>')]


def md(text):
    """Tiny markdown: blank-line paragraphs, '- ' bullets, '## ' headings, **bold**, [links](url)."""
    blocks, out = re.split(r"\n\s*\n", (text or "").strip()), []
    for b in blocks:
        lines = [l.rstrip() for l in b.split("\n") if l.strip()]
        if not lines:
            continue
        if all(l.lstrip().startswith("- ") for l in lines):
            out.append("<ul>" + "".join(f"<li>{inline(l.lstrip()[2:])}</li>" for l in lines) + "</ul>")
        elif lines[0].startswith("## "):
            out.append(f"<h3>{inline(lines[0][3:])}</h3>" + (f"<p>{inline(' '.join(lines[1:]))}</p>" if len(lines) > 1 else ""))
        else:
            out.append(f"<p>{inline(' '.join(l.strip() for l in lines))}</p>")
    return Markup("\n".join(out))


def inline(s):
    s = html.escape(s)
    for rx, rep in INLINE:
        s = rx.sub(rep, s)
    return s


MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def fmt_dates(start, end):
    def parse(s):
        try:
            y, m, d = (s + "-00-00").split("-")[:3]
            return int(y), int(m), int(d)
        except ValueError:
            return None
    a, b = parse(start or ""), parse(end or "")
    if not a:
        return ""
    if not b or b == a:
        return f"{a[2]} {MONTHS[a[1]]} {a[0]}" if a[2] else (f"{MONTHS[a[1]]} {a[0]}" if a[1] else str(a[0]))
    if a[0] == b[0] and a[1] == b[1]:
        return f"{a[2]}–{b[2]} {MONTHS[a[1]]} {a[0]}"
    if a[0] == b[0]:
        return f"{a[2]} {MONTHS[a[1]]} – {b[2]} {MONTHS[b[1]]} {a[0]}"
    return f"{a[2]} {MONTHS[a[1]]} {a[0]} – {b[2]} {MONTHS[b[1]]} {b[0]}"


def plain(s):
    return REDACT.sub("___", str(s))


# ---------------------------------------------------------------- build
def main():
    print("build: reading studio.db")
    data = studio.export_data()
    s = data["settings"]
    # only images of records that will actually appear on the site are processed
    visible = {("project", p["id"]) for p in data["projects"] if p["status"] in ("published", "wip")}
    visible |= {("book", b["id"]) for b in data["books"] if b["status"] != "draft"}
    visible |= {("event", e["id"]) for e in data["events"] if e["status"] in ("upcoming", "past")}
    visible |= {("album", a["id"]) for a in data.get("albums", []) if a["status"] == "released"}
    images = [i for i in data["images"] if i["owner_type"] == "site" or (i["owner_type"], i["owner_id"]) in visible]
    os.makedirs(IMG, exist_ok=True)
    process_images(images)
    images = [i for i in images if not i.get("missing")]

    def imgs_for(kind, oid):
        return sorted([i for i in images if i["owner_type"] == kind and i["owner_id"] == oid],
                      key=lambda i: (i["sort_order"], i["id"]))

    def with_images(rec, kind):
        ims = imgs_for(kind, rec["id"])
        rec["images"] = ims
        rec["cover"] = next((i for i in ims if i["role"] == "cover"), ims[0] if ims else None)
        rec["gallery"] = [i for i in ims if i["role"] != "cover"] or ims
        return rec

    projects = [with_images(p, "project") for p in data["projects"] if p["status"] in ("published", "wip")]
    for p in projects:
        try:
            p["links"] = json.loads(p["links"] or "[]")
        except json.JSONDecodeError:
            p["links"] = []
    by_id = {p["id"]: p for p in projects}
    books = [with_images(b, "book") for b in data["books"] if b["status"] != "draft"]
    for b in books:
        b["project"] = by_id.get(b["project_id"])
    for p in projects:
        p["books"] = [b for b in books if b["project_id"] == p["id"]]
    events = [with_images(e, "event") for e in data["events"] if e["status"] in ("upcoming", "past")]
    for e in events:
        try:
            ids = json.loads(e["project_ids"] or "[]")
        except json.JSONDecodeError:
            ids = []
        e["projects"] = [by_id[i] for i in ids if i in by_id]
        e["when"] = fmt_dates(e["start_date"], e["end_date"])
    events.sort(key=lambda e: e["start_date"], reverse=True)
    for p in projects:
        p["events"] = [e for e in events if p in e["projects"]]
    albums = [with_images(a, "album") for a in data.get("albums", []) if a["status"] == "released"]
    albums = [a for a in albums if a["cover"]]
    artists = []
    for a in albums:
        if a["artist"] not in artists:
            artists.append(a["artist"])
    site_imgs = imgs_for("site", 0)
    portrait = next((i for i in site_imgs if i["role"] == "portrait"), None)
    hero = [i for i in site_imgs if i["role"] == "hero"] or \
           [p["cover"] for p in projects if p["featured"] and p["cover"]] or \
           [p["cover"] for p in projects if p["cover"]][:8]

    env = Environment(loader=FileSystemLoader(os.path.join(ROOT, "templates")),
                      autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
    env.filters.update(redact=redact, md=md, plain=plain)
    base = s.get("base_url", "").rstrip("/")
    ctx = dict(site=s, base=base, projects=projects, books=books, events=events, hero=hero, albums=albums, artists=artists,
               portrait=portrait, year=date.today().year, bio=md(s.get("bio", "")))

    def render(tpl, out, **kw):
        path = os.path.join(DOCS, out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(env.get_template(tpl).render(**ctx, **kw))

    render("index.html", "index.html", page="home")
    for i, p in enumerate(projects):
        render("project.html", f"projects/{p['slug']}/index.html", page="projects", project=p,
               prev=projects[i - 1] if i else None, next=projects[i + 1] if i + 1 < len(projects) else None)
    render("projects.html", "projects/index.html", page="projects")
    for d in os.listdir(os.path.join(DOCS, "projects")):      # pages of projects no longer visible
        full = os.path.join(DOCS, "projects", d)
        if os.path.isdir(full) and d not in {p["slug"] for p in projects}:
            shutil.rmtree(full)
    render("books.html", "photobooks/index.html", page="books")
    render("events.html", "exhibitions/index.html", page="events")
    render("about.html", "about/index.html", page="about")
    render("covers.html", "covers/index.html", page="covers")
    render("404.html", "404.html", page="404")

    # static assets, GitHub Pages plumbing
    for f in os.listdir(os.path.join(ROOT, "static")):
        shutil.copy(os.path.join(ROOT, "static", f), DOCS)
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    cname = os.path.join(DOCS, "CNAME")
    if s.get("domain"):
        open(cname, "w").write(s["domain"].strip() + "\n")
    elif os.path.exists(cname):
        os.remove(cname)
    urls = ["/", "/projects/", "/photobooks/", "/exhibitions/", "/covers/", "/about/"] + [f"/projects/{p['slug']}/" for p in projects]
    with open(os.path.join(DOCS, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + "".join(f"  <url><loc>{base}{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    studio.export_json()
    print(f"build: {len(projects)} projects, {len(books)} books, {len(events)} events, {len(albums)} covers -> {DOCS}")


if __name__ == "__main__":
    main()
