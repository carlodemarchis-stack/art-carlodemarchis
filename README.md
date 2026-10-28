# carlodemarchis — photography beyond photography

Static portfolio site for Carlo De Marchis's visual-art work (projects, photobooks,
exhibitions) plus **studio**, a local backend to track all of it.

```
carlodemarchis-site/
├── studio/            local backend: SQLite + admin UI + JSON API (stdlib only)
│   ├── studio.py      serve | build | export | import | seed
│   ├── admin.html     the admin interface (http://127.0.0.1:8766/)
│   ├── schema.sql     tables: settings, projects, books, events, images, notes
│   ├── seed.py        loads the 2025 portfolio + newer colour work (drafts)
│   └── studio.db      working database (gitignored)
├── content.json       git-tracked snapshot of the database (written on every build)
├── build.py           renders docs/ with jinja2 + resizes images with macOS sips
├── templates/         jinja2 templates (base, index, projects, project, books, events, about, 404)
├── static/            style.css, site.js (lightbox), favicon.svg → copied into docs/
├── sources/           hi-res media copied out of the Keynote portfolio (gitignored)
└── docs/              the generated site — what GitHub Pages serves
```

## Daily use

```bash
python3 studio/studio.py serve        # admin UI at http://127.0.0.1:8766/  (site preview at /site/)
```

In the admin: edit projects / photobooks / events, add images straight from
`~/Documents/_cdm/_carlo/Art` (file picker, previews), set the cover, reorder,
caption, keep per-record notes & to-dos, then **Build site**.

`Build` = `python3 build.py`: resizes every referenced image (2000 px large,
900 px thumb, JPEG 82, cached — only new or changed sources are processed),
renders the pages, writes `docs/sitemap.xml`, `.nojekyll`, `CNAME` (if a domain
is set) and refreshes `content.json`. Then:

```bash
git add -A && git commit -m "content: …" && git push
```

GitHub Pages is configured to serve the `docs/` folder of `main`.

## Content model

| table    | what                                                            | visibility rule                      |
|----------|-----------------------------------------------------------------|--------------------------------------|
| projects | series / photobook / installation / video; palette bw or color  | `published` and `wip` are shown; `draft` hidden |
| books    | photobooks, linked to a project, with a buy link                | everything except `draft`            |
| events   | exhibitions, fairs, talks, launches                             | `upcoming` and `past`; `planned` hidden |
| images   | one row per image: hi-res source path + role (cover/gallery/hero/portrait) | — |
| notes    | free-form to-dos attached to any record (or the site)           | never published                      |

Titles may contain `▇` characters: runs of them render as black redaction bars
(the signature of the prompt titles, e.g. *A black and white portrait of ▇▇▇ in the style of ▇▇▇*).

Statements use a tiny markdown: blank line = paragraph, `- ` = bullet,
`## ` = heading, `**bold**`, `[link](https://…)`.

## Re-seeding

`python3 studio/studio.py seed` wipes the database and reloads the portfolio.
Only do that before you have started editing in the admin — after that,
`content.json` is your backup (`python3 studio/studio.py import` restores it).

## Analytics

Leave `umami_website_id` empty for no tracking. If set, the Umami snippet is
added with the standard `?noumami` opt-out line.

## Requirements

macOS (uses `sips`), system `python3` with `jinja2` (present on this Mac). No
other dependencies, no node, no build tool.
