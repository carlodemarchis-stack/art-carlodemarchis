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
from PIL import Image, ImageOps

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "studio"))
import studio  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
IMG = os.path.join(DOCS, "img")
SIZES = {"url": 2000, "medium": 1200, "thumb": 900, "small": 480}   # key -> longest side (px)
SUFFIX = {"url": "", "medium": "-m", "thumb": "-s", "small": "-xs"}
WEBP_QUALITY = 82
OG_SIZE, OG_QUALITY = 1200, 85            # a JPEG copy of cover/hero images for og:image (LinkedIn/X do not read WebP)
Image.MAX_IMAGE_PIXELS = None
NO_IMAGES = "--no-images" in sys.argv


# ---------------------------------------------------------------- images
def load_source(src):
    """Open any source with Pillow; HEIC goes through sips -> PNG first (Pillow has no HEIF decoder here)."""
    if src.lower().endswith((".heic", ".heif")):
        tmp = os.path.join(studio.CACHE, "heic-" + hashlib.sha1(src.encode()).hexdigest()[:10] + ".png")
        if not os.path.exists(tmp) or os.path.getmtime(tmp) < os.path.getmtime(src):
            os.makedirs(studio.CACHE, exist_ok=True)
            r = subprocess.run(["sips", "-s", "format", "png", src, "--out", tmp], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip())
        src = tmp
    im = Image.open(src)
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")
    return im


def derive_all(src, targets):
    """targets: {path: longest_side}. Decode once, write every missing/stale file. Returns number written."""
    stale = {p: n for p, n in targets.items()
             if not (os.path.exists(p) and os.path.getmtime(p) >= os.path.getmtime(src))}
    if not stale:
        return 0
    try:
        im = load_source(src)
    except Exception as e:  # unreadable / iCloud-evicted file: warn, the record is skipped
        print(f"  ! cannot read {src}: {e}")
        return 0
    os.makedirs(os.path.dirname(next(iter(stale))), exist_ok=True)
    for path, n in sorted(stale.items(), key=lambda kv: -kv[1]):   # largest first, each from the full decode
        out = im.copy()
        out.thumbnail((n, n), Image.LANCZOS)
        if path.endswith(".webp"):
            out.save(path, "WEBP", quality=WEBP_QUALITY, method=5)
        else:
            out.save(path, "JPEG", quality=OG_QUALITY, optimize=True, progressive=True)
    return len(stale)


def process_images(images):
    """Add url/medium/thumb/small (WebP) + og (JPEG, covers/heroes only) + w/h to every record; returns files kept."""
    keep, made = set(), 0
    for im in images:
        src = im["path"]
        if not os.path.isfile(src):
            print(f"  ! missing source, skipped: {src}")
            im["missing"] = True
            continue
        key = f"{im['id']}-{hashlib.sha1(src.encode()).hexdigest()[:6]}"
        folder = os.path.join(IMG, im["owner_type"])
        files = {k: os.path.join(folder, f"{key}{SUFFIX[k]}.webp") for k in SIZES}
        targets = {files[k]: SIZES[k] for k in SIZES}
        og = None
        if im["role"] in ("cover", "hero"):
            og = os.path.join(folder, f"{key}-og.jpg")
            targets[og] = OG_SIZE
        if not NO_IMAGES:
            made += derive_all(src, targets)
        if not os.path.exists(files["url"]):
            im["missing"] = True
            continue
        with Image.open(files["url"]) as probe:
            im["w"], im["h"] = probe.size
        for k in SIZES:
            im[k] = f"/img/{im['owner_type']}/{key}{SUFFIX[k]}.webp"
        im["og"] = f"/img/{im['owner_type']}/{key}-og.jpg" if og and os.path.exists(og) else im["url"]
        im["name"] = os.path.basename(src)
        keep.update(targets)
    if not NO_IMAGES:
        for dp, _, fn in os.walk(IMG):
            for f in fn:
                full = os.path.join(dp, f)
                if full not in keep:
                    os.remove(full)
    print(f"  images: {len(images) - sum(1 for i in images if i.get('missing'))} in use, {made} files written")


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


def bar_when(start, time_text):
    """'Thursday 29 October, from 7 pm' for the This-week bar."""
    try:
        d = date(*[int(x) for x in start.split("-")[:3]])
    except (ValueError, TypeError):
        return time_text
    out = f"{d.strftime('%A')} {d.day} {MONTHS[d.month]}"
    return f"{out}, {time_text}" if time_text else out


def img(im, sizes, alt="", eager=False, cls="", full=False):
    """<img> with srcset: 480 / 900 / 1200 px, plus 2000 px only when full=True (page heroes).
    The browser picks the smallest file that fills `sizes` at its pixel density; the lightbox always opens the 2000 px file."""
    if not im:
        return ""
    cands = f'{im["small"]} 480w, {im["thumb"]} 900w, {im["medium"]} 1200w' + (f', {im["url"]} 2000w' if full else "")
    return Markup(
        f'<img{" class=" + chr(34) + cls + chr(34) if cls else ""} src="{im["thumb"]}" srcset="{cands}" sizes="{sizes}" '
        f'width="{im["w"]}" height="{im["h"]}" alt="{html.escape(str(alt))}" '
        f'loading="{"eager" if eager else "lazy"}"{" fetchpriority=" + chr(34) + "high" + chr(34) if eager else ""} decoding="async">')


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
        rec["hero"] = next((i for i in ims if i["role"] == "hero"), rec["cover"])   # page-top image; cover is for lists
        rec["gallery"] = [i for i in ims if i["role"] not in ("cover", "hero", "alt")] or ims
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
        e["when_bar"] = bar_when(e["start_date"], e.get("time", ""))
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
    portraits = [i for i in site_imgs if i["role"] == "portrait"]     # first one is shown in b&w, the others in colour
    portrait = portraits[0] if portraits else None
    # home mosaic: featured projects (2 = shown first, 1 = in the rotation pool), two b&w + two colour tiles
    feat = sorted([p for p in projects if p["featured"] and p["cover"]], key=lambda p: (-p["featured"], p["sort_order"]))
    def tile(p):
        c = p["hero"] or p["cover"]     # the project's own page image, never the list thumbnail (e.g. an album cover)
        return {"slug": p["slug"], "title": plain(p["title"]), "url": f"/projects/{p['slug']}/", "thumb": c["thumb"], "w": c["w"], "h": c["h"]}
    pool = {"bw": [tile(p) for p in feat if p["palette"] != "color"], "color": [tile(p) for p in feat if p["palette"] == "color"]}
    tiles = [t for pair in zip(pool["bw"][:2], pool["color"][:2]) for t in pair] or [tile(p) for p in projects if p["cover"]][:4]
    hero = [p["cover"] for p in feat][:1] or [p["cover"] for p in projects if p["cover"]][:1]   # for og:image
    hero_bg = next((i for i in site_imgs if i["role"] == "hero"), None)                       # home backdrop (landscape)

    env = Environment(loader=FileSystemLoader(os.path.join(ROOT, "templates")),
                      autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
    env.filters.update(redact=redact, md=md, plain=plain)
    env.globals["img"] = img
    base = s.get("base_url", "").rstrip("/")
    ctx = dict(site=s, base=base, projects=projects, books=books, events=events, hero=hero, hero_bg=hero_bg, tiles=tiles, pool_json=json.dumps(pool), albums=albums, artists=artists,
               portrait=portrait, portraits=portraits, year=date.today().year, bio=md(s.get("bio", "")))

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
