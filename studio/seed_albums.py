#!/usr/bin/env python3
"""Add the released album covers from ~/Documents/_cdm/_carlo/Art/AI music.

Layout expected:  AI music/<Artist>/Released/<Title>/Cover/Cover/*.jpeg|png   (final covers)
             or:  AI music/<Artist>/Released/<Title>/Cover/<Title>/*.jpeg|png (Keynote export)

Idempotent: a title that already exists (same slug) is left untouched, so it is
safe to re-run after adding a new release. Year = file date of the cover (check it).
"""
import glob
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import studio

MUSIC = os.path.expanduser("~/Documents/_cdm/_carlo/Art/AI music")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    con = studio.connect()
    existing = {r[0] for r in con.execute("SELECT slug FROM albums")}
    seen_covers = set()
    order = (con.execute("SELECT coalesce(max(sort_order),0) FROM albums").fetchone()[0] or 0) + 10
    added = 0
    for d in sorted(glob.glob(os.path.join(MUSIC, "*", "Released", "*", ""))):
        artist, _, title = d.rstrip("/").split(os.sep)[-3:]
        cov = os.path.join(d, "Cover")
        files = sorted(glob.glob(os.path.join(cov, "Cover", "*.jp*g")) + glob.glob(os.path.join(cov, "Cover", "*.png")))
        if not files:
            files = sorted(glob.glob(os.path.join(cov, title, "*.jp*g")) + glob.glob(os.path.join(cov, title, "*.png")))
        if not files:
            print(f"  ! no final cover for {artist} / {title}")
            continue
        key = (os.path.getsize(files[0]), os.path.basename(files[0]), artist)
        if key in seen_covers:          # e.g. "City Vibes" and "City Vibes - Album" share one cover
            print(f"  - skipped duplicate cover: {artist} / {title}")
            continue
        seen_covers.add(key)
        clean_title = re.sub(r"\s*-\s*album$", "", title, flags=re.I)
        slug = slugify(f"{artist}-{clean_title}")
        if slug in existing:
            continue
        year = time.strftime("%Y", time.localtime(os.path.getmtime(files[0])))
        kind = "album" if title.lower().endswith("album") or len(files) > 3 else "single"
        cur = con.execute("INSERT INTO albums(slug,artist,title,year,kind,status,sort_order) VALUES(?,?,?,?,?,?,?)",
                          (slug, artist, clean_title, year, kind, "released", order))
        aid = cur.lastrowid
        for i, f in enumerate(files):
            con.execute("INSERT INTO images(owner_type,owner_id,path,role,caption,sort_order) VALUES('album',?,?,?,?,?)",
                        (aid, f, "cover" if i == 0 else "gallery", "" if i == 0 else "back / alternate", i))
        con.execute("INSERT INTO notes(owner_type,owner_id,body) VALUES('album',?,?)",
                    (aid, "Year taken from the cover file date and kind guessed — check both; add the listen link."))
        order += 10
        added += 1
        print(f"  + {artist} / {clean_title} ({year}, {len(files)} file(s))")
    con.commit()
    print("albums added:", added)


if __name__ == "__main__":
    main()
