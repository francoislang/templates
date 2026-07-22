#!/usr/bin/env python3
"""Scrape toutes les annonces chien.com dans _data/annonces.db.

Idempotent : relance = reprend là où on s'est arrêté (dedup par source_url).
Ctrl-C safe : commit après chaque ligne.

Usage:
    python3 _scripts/scrape_all.py
    python3 _scripts/scrape_all.py --max-pages 100
    python3 _scripts/scrape_all.py --start-page 42
"""
import argparse
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import scraper

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "annonces.db"
STOP_AFTER_EMPTY_PAGES = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS annonces (
    source_url  TEXT PRIMARY KEY,
    name        TEXT,
    race        TEXT,
    race_slug   TEXT,
    phone       TEXT,
    email       TEXT,
    website     TEXT,
    siren       TEXT,
    acaced      TEXT,
    statut      TEXT,
    ville       TEXT,
    code_postal TEXT,
    departement TEXT,
    description TEXT,
    photo_url   TEXT,
    scraped_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_race ON annonces(race);
CREATE INDEX IF NOT EXISTS idx_dept ON annonces(departement);
"""

_INSERT = """
INSERT OR IGNORE INTO annonces (
    source_url, name, race, race_slug, phone, email, website,
    siren, acaced, statut, ville, code_postal, departement,
    description, photo_url, scraped_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_stop = False


def _sigint_handler(signum, frame):
    global _stop
    _stop = True
    print("\n[Ctrl-C] arrêt après le profil en cours...")


def _init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _existing_urls(conn):
    return {row[0] for row in conn.execute("SELECT source_url FROM annonces")}


def main():
    ap = argparse.ArgumentParser(description="Scrape toutes les annonces chien.com dans SQLite.")
    ap.add_argument("--max-pages", type=int, default=None,
                    help="Limite du nombre de pages (defaut: pas de limite)")
    ap.add_argument("--start-page", type=int, default=1)
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _sigint_handler)

    conn = _init_db()
    seen = _existing_urls(conn)
    print(f"DB : {DB_PATH}")
    print(f"Annonces déjà présentes : {len(seen)}")

    inserted = 0
    skipped_invalid = 0
    empty_streak = 0
    page = args.start_page

    while not _stop:
        if args.max_pages is not None and page >= args.start_page + args.max_pages:
            print(f"--max-pages atteint (page {page - 1})")
            break

        urls = scraper.fetch_listing_page(page)

        if not urls:
            print(f"Page {page}: 0 URL — fin du listing")
            break

        new_urls = [u for u in urls if u not in seen]

        if not new_urls:
            empty_streak += 1
            print(f"Page {page}: {len(urls)} URLs, 0 nouvelle "
                  f"(streak {empty_streak}/{STOP_AFTER_EMPTY_PAGES})")
            if empty_streak >= STOP_AFTER_EMPTY_PAGES:
                print("Fin : plus de nouvelles URLs")
                break
        else:
            empty_streak = 0
            print(f"Page {page}: {len(urls)} URLs, {len(new_urls)} nouvelles")

        for url in new_urls:
            if _stop:
                break

            profile = scraper.fetch_profile(url, strict_race=False)
            seen.add(url)

            if not profile:
                skipped_invalid += 1
                time.sleep(scraper.DELAY)
                continue

            now = datetime.now(timezone.utc).isoformat()
            conn.execute(_INSERT, (
                profile["source_url"],
                profile.get("name", ""),
                profile.get("race"),
                profile.get("race_slug", ""),
                profile.get("phone", ""),
                profile.get("email", ""),
                profile.get("website", ""),
                profile.get("siren", ""),
                profile.get("acaced", ""),
                profile.get("statut", ""),
                profile.get("ville", ""),
                profile.get("code_postal", ""),
                profile.get("departement", ""),
                profile.get("description", ""),
                profile.get("photo_url", ""),
                now,
            ))
            conn.commit()
            inserted += 1

            if inserted % 20 == 0:
                total = conn.execute("SELECT COUNT(*) FROM annonces").fetchone()[0]
                print(f"  → {inserted} insérés cette session | {total} total en DB | "
                      f"{skipped_invalid} URLs invalides ignorées")
            time.sleep(scraper.DELAY)

        page += 1
        time.sleep(2)

    total = conn.execute("SELECT COUNT(*) FROM annonces").fetchone()[0]
    print(f"\nTerminé. Insérés cette session : {inserted}. Total DB : {total}. "
          f"URLs invalides : {skipped_invalid}.")
    conn.close()


if __name__ == "__main__":
    main()
