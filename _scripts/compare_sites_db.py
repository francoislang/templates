#!/usr/bin/env python3
"""Compare les sites déjà générés dans le repo avec les données de la DB `annonces`.

Pour chaque dossier de site :
- Lit index.html et extrait nom / tel / email / SIREN / ville
- Cherche la row correspondante en DB (par slug du nom)
- Rapporte les correspondances / différences / manquants

Usage:
    python3 _scripts/compare_sites_db.py
    python3 _scripts/compare_sites_db.py --verbose   # affiche chaque site
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "annonces.db"

# Dossiers exclus (non-sites)
EXCLUDE = {"_scripts", "_templates", "_data", "node_modules", ".git", ".claude"}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def find_site_dirs(root: Path) -> list[Path]:
    return sorted(d for d in root.iterdir()
                  if d.is_dir() and d.name not in EXCLUDE
                  and not d.name.startswith(".")
                  and (d / "index.html").exists())


def extract_from_html(html: str) -> dict:
    """Extrait les champs du HTML généré."""
    d = {}

    # Nom : og:title, h1, ou title
    for pat in [
        r'<meta\s+property="og:title"\s+content="([^"]+)"',
        r'<title>([^<]+)</title>',
        r'<h1[^>]*>([^<]+)</h1>',
    ]:
        m = re.search(pat, html, re.I)
        if m:
            name = re.sub(r"\s+", " ", m.group(1)).strip()
            # Nettoie suffixes courants
            name = re.sub(r"\s*[-|·].*$", "", name).strip()
            d["title"] = name
            break

    # Téléphone : tel: link (prioritaire)
    m = re.search(r'href="tel:([^"]+)"', html)
    if m:
        d["phone"] = m.group(1).strip()
    else:
        # fallback: pattern texte
        m = re.search(r"\b0[1-9](?:[\s.\-]\d{2}){4}\b", html)
        if m:
            d["phone"] = m.group(0).strip()

    # Email : mailto:
    m = re.search(r'href="mailto:([^"?"]+)"', html)
    if m:
        d["email"] = m.group(1).strip().lower()

    # SIREN
    m = re.search(r"SIREN[^\d]{0,10}(\d{9})", html)
    if m:
        d["siren"] = m.group(1)

    # Ville : cherche patterns "à VILLE" ou meta location
    m = re.search(r'<meta\s+property="og:locality"\s+content="([^"]+)"', html)
    if m:
        d["ville"] = m.group(1).strip()

    return d


def normalize_phone(p: str) -> str:
    return re.sub(r"[^\d+]", "", p or "")


def load_db(conn):
    """Retourne dict slug(name) -> row."""
    rows = list(conn.execute("SELECT name, phone, email, siren, ville, source_url FROM annonces"))
    by_slug = {}
    for r in rows:
        s = slugify(r[0])
        # Garde le premier match ; ajoute les doublons dans une liste
        by_slug.setdefault(s, []).append({
            "name": r[0], "phone": r[1], "email": r[2],
            "siren": r[3], "ville": r[4], "source_url": r[5],
        })
    return by_slug


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    db_by_slug = load_db(conn)
    sites = find_site_dirs(REPO_ROOT)

    print(f"Sites dans le repo : {len(sites)}")
    print(f"Rows en DB (unique slugs) : {len(db_by_slug)}\n")

    stats = {"matched": 0, "not_in_db": 0, "phone_ok": 0, "phone_diff": 0,
             "phone_missing_db": 0, "phone_missing_site": 0,
             "siren_ok": 0, "siren_diff": 0}
    mismatches = []
    missing = []

    for site_dir in sites:
        slug = site_dir.name
        html = (site_dir / "index.html").read_text(errors="ignore")
        site_data = extract_from_html(html)
        db_rows = db_by_slug.get(slug)

        if not db_rows:
            stats["not_in_db"] += 1
            missing.append((slug, site_data.get("title", "?"), site_data.get("phone", "")))
            continue

        stats["matched"] += 1
        # Prend la row la plus complète (avec téléphone)
        db_row = next((r for r in db_rows if r["phone"]), db_rows[0])

        p_site = normalize_phone(site_data.get("phone", ""))
        p_db   = normalize_phone(db_row["phone"])

        if p_site and p_db:
            if p_site == p_db:
                stats["phone_ok"] += 1
            else:
                stats["phone_diff"] += 1
                mismatches.append((slug, "phone", site_data.get("phone"), db_row["phone"]))
        elif p_db and not p_site:
            stats["phone_missing_site"] += 1
        elif p_site and not p_db:
            stats["phone_missing_db"] += 1

        s_site = site_data.get("siren", "")
        s_db   = (db_row["siren"] or "").strip()
        if s_site and s_db:
            if s_site == s_db:
                stats["siren_ok"] += 1
            else:
                stats["siren_diff"] += 1
                mismatches.append((slug, "siren", s_site, s_db))

        if args.verbose:
            print(f"[{slug}]")
            print(f"  site : name={site_data.get('title','')!r:40} "
                  f"phone={site_data.get('phone','')!r} siren={site_data.get('siren','')!r}")
            print(f"  db   : name={db_row['name']!r:40} "
                  f"phone={db_row['phone']!r} siren={db_row['siren']!r}")

    print("=== Statistiques ===")
    for k, v in stats.items():
        print(f"  {k:22s} {v}")

    if missing:
        print(f"\n=== {len(missing)} sites SANS row en DB (ordre alphabétique) ===")
        for slug, name, phone in missing:
            print(f"  {slug:40s} html_name={name!r:35} html_phone={phone!r}")

    if mismatches:
        print(f"\n=== {len(mismatches)} mismatches valeur ===")
        for slug, field, s_val, d_val in mismatches:
            print(f"  {slug:40s} {field:8s} site={s_val!r:20} db={d_val!r}")


if __name__ == "__main__":
    main()
