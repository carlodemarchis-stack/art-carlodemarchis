#!/usr/bin/env python3
"""Print an A4 portfolio PDF from the studio database: cover, one page per live project, closing page.
Every page carries the same footer (URL, QR, name) so the sheets can be handed out separately.

  python3 tools/portfolio_pdf.py            -> docs/handouts/carlodemarchis-portfolio.pdf
  python3 tools/portfolio_pdf.py --html     -> only write the HTML (open it in a browser to tweak)

Images are re-encoded from the hi-res sources into sources/portfolio-pdf/ (gitignored).
Printing uses headless Chrome; on this Mac it hangs after writing the file, so it runs under a perl alarm.
"""
import html
import os
import re
import subprocess
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "studio"))
import studio  # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "handouts")
IMG_DIR = os.path.join(ROOT, "sources", "portfolio-pdf")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
QR = os.path.join(OUT_DIR, "qr-pole.png")
SITE = "art.carlodemarchis.it"
Image.MAX_IMAGE_PIXELS = None


def jpeg(src, name, maxpx=2400, q=90):
    """Hi-res JPEG for print, cached by mtime. Returns (path, w, h)."""
    os.makedirs(IMG_DIR, exist_ok=True)
    out = os.path.join(IMG_DIR, name + ".jpg")
    if not (os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(src)):
        if src.lower().endswith((".heic", ".heif")):
            tmp = out + ".png"
            subprocess.run(["sips", "-s", "format", "png", src, "--out", tmp], capture_output=True)
            src = tmp
        im = Image.open(src)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        im.thumbnail((maxpx, maxpx), Image.LANCZOS)
        im.save(out, "JPEG", quality=q, optimize=True)
    with Image.open(out) as probe:
        w, h = probe.size
    return out, w, h


def md(text):
    """Same mini-markdown as the site: paragraphs, '- ' bullets, **bold**."""
    out = []
    inl = lambda t: re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(t))
    for b in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [l for l in b.split("\n") if l.strip()]
        if not lines:
            continue
        if all(l.lstrip().startswith("- ") for l in lines):
            out.append("<ul>" + "".join(f"<li>{inl(l.lstrip()[2:])}</li>" for l in lines) + "</ul>")
        else:
            out.append(f"<p>{inl(' '.join(l.strip() for l in lines))}</p>")
    return "\n".join(out)


def redact(title):
    return re.sub("▇+", lambda m: '<span class="redact" style="width:%.1fem"></span>' % (len(m.group()) * .62), html.escape(title))


CSS = """
@page{size:A4;margin:0}
html,body{margin:0;padding:0;background:#fff;color:#000;font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.page{width:210mm;height:297mm;box-sizing:border-box;padding:12mm 14mm 11mm;display:flex;flex-direction:column;overflow:hidden;page-break-after:always;position:relative}
.page:last-child{page-break-after:auto}
.top{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid #000;padding-bottom:2.5mm;flex:none}
.wordmark{font-weight:700;font-size:15pt;letter-spacing:-.03em}
.tag{font-size:8.5pt;color:#555;margin-left:8px}
.right{font-size:8.5pt;color:#555;text-transform:uppercase;letter-spacing:.1em}
.photo{margin:5mm 0 4.5mm;flex:none;display:flex;justify-content:center}
.photo img{display:block;max-width:100%;max-height:var(--ph,118mm);width:auto;height:auto}
h1{font-weight:700;font-size:26pt;letter-spacing:-.03em;line-height:1;margin:0 0 1.5mm;flex:none}
h2{font-weight:400;font-size:11.5pt;color:#333;margin:0 0 4mm;letter-spacing:-.01em;flex:none}
.meta{font-size:8pt;color:#666;text-transform:uppercase;letter-spacing:.1em;margin:0 0 2mm;flex:none}
.redact{display:inline-block;background:#000;height:.78em;vertical-align:-.04em;margin:0 .08em}
.text{column-count:2;column-gap:9mm;font-size:var(--fs,9.8pt);line-height:1.4;flex:1 1 auto;min-height:0;overflow:hidden}
.text p{margin:0 0 2.8mm}
.text p:first-child{font-weight:600}
.text ul{margin:0 0 2.8mm;padding-left:4mm}
.text li{margin:0 0 1mm}
.prints{margin:0;padding:3mm 0;font-size:9pt;color:#222;flex:none}
/* the shared footer: URL + QR + name on every sheet */
.foot{display:flex;align-items:center;gap:5mm;border-top:1px solid #000;padding-top:3mm;margin-top:auto;flex:none;font-size:8.5pt;color:#444;line-height:1.45}
.prints + .foot{margin-top:0}
.foot img{width:17mm;height:17mm;flex:none}
.foot .grow{flex:1}
.foot .url{font-weight:700;font-size:11pt;color:#000;letter-spacing:-.02em}
.foot .r{text-align:right}
/* cover */
.cover{background:#000;color:#fff;justify-content:flex-end}
.cover img.bg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.55;filter:grayscale(1)}
.cover .block{position:relative;padding:0 2mm 16mm}
.cover .name{font-weight:700;font-size:54pt;letter-spacing:-.05em;line-height:.95;margin:0}
.cover .tagline{font-weight:700;font-size:22pt;letter-spacing:-.03em;margin:4mm 0 10mm}
.cover .sub{font-size:11pt;color:#ddd;max-width:120mm;line-height:1.45}
.cover .yr{position:absolute;top:14mm;right:16mm;font-size:10pt;letter-spacing:.12em;text-transform:uppercase;color:#bbb}
.cover .foot{position:relative;border-top-color:#fff;color:#bbb}
.cover .foot .url{color:#fff}
.cover .foot img{background:#fff;padding:1mm;box-sizing:border-box}
/* closing */
.end .big{font-weight:700;font-size:30pt;letter-spacing:-.04em;line-height:1;margin:14mm 0 6mm;flex:none}
.end .cols{display:grid;grid-template-columns:1fr 1fr;gap:10mm;font-size:10pt;line-height:1.5;flex:none}
.end h3{font-size:9pt;text-transform:uppercase;letter-spacing:.1em;color:#666;margin:0 0 2mm}
.end ul{margin:0 0 6mm;padding-left:4mm}
"""

FIT_JS = """
document.querySelectorAll('.page.project').forEach(function (pg) {
  var text = pg.querySelector('.text'), fs = 9.8, ph = 118;
  function over() { return text.scrollHeight > text.clientHeight + 1; }
  while (over() && fs > 7.2) { fs -= 0.2; pg.style.setProperty('--fs', fs.toFixed(1) + 'pt'); }
  while (over() && ph > 70) { ph -= 5; pg.style.setProperty('--ph', ph + 'mm'); }
  if (over()) pg.dataset.overflow = '1';
});
"""


def footer(s, path="", note="Scan for all the projects, photobooks, album covers and upcoming exhibitions."):
    qr = f'<img src="file://{QR}">' if os.path.exists(QR) else ""
    return (f'<div class="foot">{qr}<div class="grow"><div class="url">{SITE}{html.escape(path)}</div>'
            f'<div>{html.escape(note)}</div></div>'
            f'<div class="r">{html.escape(s["artist_name"])}<br>{html.escape(s["city"])}<br>all images AI-generated</div></div>')


def main():
    data = studio.export_data()
    s = data["settings"]
    imgs = data["images"]
    projects = [p for p in data["projects"] if p["status"] in ("published", "wip")]
    books = [b for b in data["books"] if b["status"] != "draft"]
    events = sorted([e for e in data["events"] if e["status"] in ("upcoming", "past")], key=lambda e: e["start_date"], reverse=True)

    def pick(kind, oid):
        ims = sorted([i for i in imgs if i["owner_type"] == kind and i["owner_id"] == oid], key=lambda i: (i["sort_order"], i["id"]))
        hero = next((i for i in ims if i["role"] == "hero"), None)
        cover = next((i for i in ims if i["role"] == "cover"), ims[0] if ims else None)
        return hero or cover

    pages = []
    # cover
    bg = next((i for i in imgs if i["owner_type"] == "site" and i["role"] == "hero"), None)
    bg_path = jpeg(bg["path"], "cover-bg", 2400, 85)[0] if bg else ""
    pages.append(f'''<section class="page cover">{f'<img class="bg" src="file://{bg_path}">' if bg_path else ''}
      <div class="yr">Portfolio · 2026</div>
      <div class="block"><h1 class="name">{html.escape(s["site_name"])}</h1>
      <div class="tagline">{html.escape(s["tagline"])}</div>
      <div class="sub">AI-generated black & white photography for storytelling and social provocation — and new work in colour. Projects, photobooks, album covers, exhibitions.</div></div>
      {footer(s)}</section>''')
    # one page per project
    for n, p in enumerate(projects, 1):
        im = pick("project", p["id"])
        photo = ""
        if im and os.path.isfile(im["path"]):
            path, w, h = jpeg(im["path"], f"p-{p['slug']}", 2400, 90)
            photo = f'<div class="photo"><img src="file://{path}" width="{w}" height="{h}"></div>'
        kind = "special project" if p["kind"] == "commission" else p["kind"].replace("_", " ")
        pal = "colour" if p["palette"] == "color" else "black & white"
        wip = " · work in progress" if p["status"] == "wip" else ""
        prints = "" if p["kind"] in ("commission", "installation") or not s.get("prints_note") else f'<p class="prints">{html.escape(s["prints_note"])}</p>'
        statement = md(p["statement"]) or (f'<p>{html.escape(p["excerpt"])}</p>' if p["excerpt"] else "")
        pages.append(f'''<section class="page project" data-slug="{p["slug"]}">
      <div class="top"><div><span class="wordmark">{html.escape(s["site_name"])}</span><span class="tag">{html.escape(s["tagline"])}</span></div><div class="right">{n:02d} / {len(projects):02d}</div></div>
      {photo}
      <div class="meta">{html.escape(p["year"])} · {kind} · {pal}{wip}</div>
      <h1>{redact(p["title"])}</h1>
      {f'<h2>{html.escape(p["subtitle"])}</h2>' if p["subtitle"] else ''}
      <div class="text">{statement}</div>
      {prints}
      {footer(s, f"/projects/{p['slug']}/", "Scan for this project, the other series, photobooks and upcoming exhibitions.")}</section>''')
    # closing page
    up = [e for e in events if e["status"] == "upcoming"]
    past = [e for e in events if e["status"] == "past"]

    def ev(e):
        when = e["start_date"][:4] if e["start_date"] else ""
        return f'<li><b>{html.escape(e["title"])}</b><br>{html.escape(e["venue"])}{", " if e["venue"] and e["city"] else ""}{html.escape(e["city"])} · {when}</li>'

    pages.append(f'''<section class="page end">
      <div class="top"><div><span class="wordmark">{html.escape(s["site_name"])}</span><span class="tag">{html.escape(s["tagline"])}</span></div><div class="right">more</div></div>
      <div class="big">Photobooks, covers, exhibitions.</div>
      <div class="cols"><div><h3>Photobooks</h3><ul>{''.join(f'<li>{redact(b["title"])} · {html.escape(b["year"])}{" · private edition" if b["status"] == "private" else ""}</li>' for b in books)}</ul>
        <h3>Album covers</h3><p>Cover art for the music released as Abe Murakami, An Ignorant Soul, 100 Operai Elettrici, Nuru Odu Awiro and The Night I Swam.</p>
        <p>{html.escape(s.get("prints_note", ""))}</p></div>
        <div>{f'<h3>Upcoming</h3><ul>{"".join(ev(e) for e in up)}</ul>' if up else ''}<h3>Exhibitions</h3><ul>{''.join(ev(e) for e in past)}</ul></div></div>
      {footer(s)}</section>''')

    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(s["site_name"])} — portfolio</title>'
           f'<style>{CSS}</style></head><body>{"".join(pages)}<script>{FIT_JS}</script></body></html>')
    os.makedirs(OUT_DIR, exist_ok=True)
    html_path = os.path.join(OUT_DIR, "carlodemarchis-portfolio.html")
    open(html_path, "w").write(doc)
    print(f"html: {html_path}  ({len(projects)} projects)")
    if "--html" in sys.argv:
        return
    pdf = os.path.join(OUT_DIR, "carlodemarchis-portfolio.pdf")
    if os.path.exists(pdf):
        os.remove(pdf)
    prof = os.path.join(studio.CACHE, "chrome-print")
    subprocess.run(["perl", "-e", "alarm 90; exec @ARGV", CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
                    f"--user-data-dir={prof}", "--no-pdf-header-footer", "--virtual-time-budget=8000",
                    f"--print-to-pdf={pdf}", f"file://{html_path}"], capture_output=True)
    if not os.path.exists(pdf):
        sys.exit("Chrome did not write the PDF")
    import pypdf
    n = len(pypdf.PdfReader(pdf).pages)
    print(f"pdf: {pdf}  pages: {n}  ({os.path.getsize(pdf) // 1024} KB)")
    if n != len(projects) + 2:
        print(f"  ! expected {len(projects) + 2} pages — a project page overflowed")


if __name__ == "__main__":
    main()
