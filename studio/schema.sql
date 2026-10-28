-- carlodemarchis studio — local content database
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS projects (
  id         INTEGER PRIMARY KEY,
  slug       TEXT UNIQUE NOT NULL,
  title      TEXT NOT NULL,
  subtitle   TEXT NOT NULL DEFAULT '',
  year       TEXT NOT NULL DEFAULT '',
  kind       TEXT NOT NULL DEFAULT 'series',      -- series | photobook | installation | video
  palette    TEXT NOT NULL DEFAULT 'bw',          -- bw | color
  status     TEXT NOT NULL DEFAULT 'draft',       -- draft | wip | published
  excerpt    TEXT NOT NULL DEFAULT '',
  statement  TEXT NOT NULL DEFAULT '',
  links      TEXT NOT NULL DEFAULT '[]',          -- JSON [{label,url}]
  sort_order INTEGER NOT NULL DEFAULT 0,
  featured   INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS books (
  id          INTEGER PRIMARY KEY,
  slug        TEXT UNIQUE NOT NULL,
  title       TEXT NOT NULL,
  subtitle    TEXT NOT NULL DEFAULT '',
  year        TEXT NOT NULL DEFAULT '',
  project_id  INTEGER,
  status      TEXT NOT NULL DEFAULT 'draft',      -- draft | coming | available | sold_out
  buy_url     TEXT NOT NULL DEFAULT '',
  buy_label   TEXT NOT NULL DEFAULT 'Buy on Amazon',
  isbn        TEXT NOT NULL DEFAULT '',
  format      TEXT NOT NULL DEFAULT '',
  pages       TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY,
  slug        TEXT UNIQUE NOT NULL,
  title       TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'exhibition', -- exhibition | fair | talk | book_launch | residency
  venue       TEXT NOT NULL DEFAULT '',
  city        TEXT NOT NULL DEFAULT '',
  start_date  TEXT NOT NULL DEFAULT '',           -- YYYY-MM-DD
  end_date    TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'planned',    -- planned | upcoming | past | cancelled
  description TEXT NOT NULL DEFAULT '',
  url         TEXT NOT NULL DEFAULT '',
  project_ids TEXT NOT NULL DEFAULT '[]',         -- JSON [project id, ...]
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per image used anywhere. `path` is the hi-res source on this Mac;
-- build.py derives web sizes from it. owner_type: project | book | event | site
CREATE TABLE IF NOT EXISTS images (
  id         INTEGER PRIMARY KEY,
  owner_type TEXT NOT NULL,
  owner_id   INTEGER NOT NULL DEFAULT 0,
  path       TEXT NOT NULL,
  role       TEXT NOT NULL DEFAULT 'gallery',     -- cover | gallery | hero | portrait
  caption    TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS images_owner ON images(owner_type, owner_id);

-- Free-form tracking notes / to-dos attached to any record (or to the site).
CREATE TABLE IF NOT EXISTS notes (
  id         INTEGER PRIMARY KEY,
  owner_type TEXT NOT NULL,
  owner_id   INTEGER NOT NULL DEFAULT 0,
  body       TEXT NOT NULL,
  done       INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
