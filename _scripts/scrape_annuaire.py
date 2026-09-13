#!/usr/bin/env python3
"""Scrape TOUTES les fiches éleveurs de l'annuaire chien.com dans la table `annonces`.

Parcourt les ~773 pages `/adresse/1-0-0-0-0-elevage-de-chiens-{page}.php`,
collecte les URLs de profils (~15 474 au total), puis appelle scraper.fetch_profile()
pour chacun. Insère dans _data/annonces.db (table `annonces`).

Idempotent (INSERT OR IGNORE sur PK source_url), Ctrl-C safe (commit par row).

Usage:
    python3 _scripts/scrape_annuaire.py                    # scrape complet, delay 0.8s
    python3 _scripts/scrape_annuaire.py --limit-pages 3    # test rapide (60 profils)
    python3 _scripts/scrape_annuaire.py --delay 1.5        # override délai
    python3 _scripts/scrape_annuaire.py --start-page 400   # reprend à la page 400
"""
from __future__ import annotations

import argparse
import re
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
BASE = "https://www.chien.com"
LISTING_URL = BASE + "/adresse/1-0-0-0-0-elevage-de-chiens-{page}.php"

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

_INSERT = """INSERT OR IGNORE INTO annonces (
    source_url, name, race, race_slug, phone, email, website, siren, acaced,
    statut, ville, code_postal, departement, description, photo_url, scraped_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

_PROFILE_RE = re.compile(r"/adresse/elevage-[^/]+/[^/]+-\d+\.php")
_stop = False


def _sig(sig, frame):
    global _stop
    _stop = True
    print("\n[signal] arrêt propre après la fiche en cours...", flush=True)


def _init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def fetch_listing_urls(session, page: int) -> list[str]:
    """Retourne les URLs de profils depuis une page de listing."""
    r = session.get(LISTING_URL.format(page=page), timeout=30)
    if r.status_code != 200:
        return []
    hrefs = _PROFILE_RE.findall(r.text)
    return list(dict.fromkeys(BASE + h if not h.startswith("http") else h for h in hrefs))


def detect_max_page(session) -> int:
    """Fetch page 1 et extrait la pagination max."""
    r = session.get(LISTING_URL.format(page=1), timeout=30)
    pages = re.findall(r"/adresse/1-0-0-0-0-elevage-de-chiens-(\d+)\.php", r.text)
    return max((int(p) for p in pages), default=1)


def main():
    ap = argparse.ArgumentParser(description="Scrape l'annuaire éleveurs chien.com.")
    ap.add_argument("--delay", type=float, default=0.8, help="Délai entre requêtes (défaut 0.8s)")
    ap.add_argument("--limit-pages", type=int, default=None, help="Nb max de pages listing (test)")
    ap.add_argument("--start-page", type=int, default=1, help="Page listing de départ (reprise)")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    conn = _init_db()
    seen = {r[0] for r in conn.execute("SELECT source_url FROM annonces")}
    print(f"DB           : {DB_PATH}", flush=True)
    print(f"Déjà en DB   : {len(seen)} fiches", flush=True)

    s = scraper._get_session()
    max_page = detect_max_page(s)
    end_page = min(max_page, args.limit_pages + args.start_page - 1) if args.limit_pages else max_page
    print(f"Pagination   : {args.start_page} → {end_page} (max annuaire {max_page})", flush=True)
    time.sleep(args.delay)

    inserted = 0
    skipped = 0
    errors = 0
    profiles_seen_this_run = 0

    for page in range(args.start_page, end_page + 1):
        if _stop:
            break

        try:
            urls = fetch_listing_urls(s, page)
        except Exception as e:
            print(f"  ! listing p{page} erreur : {e}", flush=True)
            errors += 1
            time.sleep(args.delay)
            continue

        if not urls:
            print(f"  page {page} vide", flush=True)
            time.sleep(args.delay)
            continue

        print(f"[page {page}/{end_page}] {len(urls)} profils | "
              f"total DB {len(seen)+inserted} | +{inserted} | skip {skipped} | err {errors}",
              flush=True)
        time.sleep(args.delay)

        for url in urls:
            if _stop:
                break
            profiles_seen_this_run += 1

            if url in seen:
                skipped += 1
                continue

            try:
                p = scraper.fetch_profile(url, strict_race=False)
            except Exception as e:
                print(f"    ! {url} : {e}", flush=True)
                errors += 1
                time.sleep(args.delay)
                continue

            if not p:
                errors += 1
                time.sleep(args.delay)
                continue

            now = datetime.now(timezone.utc).isoformat()
            try:
                conn.execute(_INSERT, (
                    p.get("source_url") or url,
                    p.get("name", ""), p.get("race", ""), p.get("race_slug", ""),
                    p.get("phone", ""), p.get("email", ""), p.get("website", ""),
                    p.get("siren", ""), p.get("acaced", ""), p.get("statut", ""),
                    p.get("ville", ""), p.get("code_postal", ""), p.get("departement", ""),
                    p.get("description", ""), p.get("photo_url", ""),
                    now,
                ))
                conn.commit()
                inserted += 1
                seen.add(url)
            except Exception as e:
                print(f"    ! insert {url} : {e}", flush=True)
                errors += 1

            time.sleep(args.delay)

    total = conn.execute("SELECT COUNT(*) FROM annonces").fetchone()[0]
    with_phone = conn.execute("SELECT COUNT(*) FROM annonces WHERE phone != ''").fetchone()[0]
    print(f"\n=== Terminé ===", flush=True)
    print(f"Pages parcourues : {page - args.start_page + 1}", flush=True)
    print(f"Profils vus      : {profiles_seen_this_run}", flush=True)
    print(f"Insérés          : {inserted}", flush=True)
    print(f"Déjà connus      : {skipped}", flush=True)
    print(f"Erreurs          : {errors}", flush=True)
    print(f"Total en DB      : {total} (avec phone : {with_phone})", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
