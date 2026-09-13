#!/usr/bin/env python3
"""Regenere un ou plusieurs sites de demo deja produits.

Utile apres une correction du generateur : le pipeline normal ignore les
prospects deja traites, et generate_demo_site() s'arrete si le fichier existe.

Le profil est reconstruit depuis _data/annonces.db, en regroupant toutes les
lignes du meme eleveur (une par race) comme le fait le pipeline.

Usage:
    python3 _scripts/regenerate.py --list
    python3 _scripts/regenerate.py du-chalet-de-la-faucille
    python3 _scripts/regenerate.py du-chalet-de-la-faucille de-la-vallee-caid
    python3 _scripts/regenerate.py --all-since 2026-09-13
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pipeline
from pipeline import DB_PATH, REPO_ROOT


def profil_depuis_slug(conn, slug):
    """Reconstruit le profil complet d'un eleveur a partir de son slug de site."""
    base = conn.execute(
        "SELECT * FROM annonces WHERE site_slug = ? LIMIT 1", (slug,)).fetchone()
    if base is None:
        # repli : retrouver par slug calcule sur le nom
        for row in conn.execute("SELECT * FROM annonces WHERE name IS NOT NULL AND name != ''"):
            if pipeline.slugify(row["name"]) == slug:
                base = row
                break
    if base is None:
        return None

    cle = pipeline._key_phone(base["phone"]) or pipeline._key_name(base["name"])
    lignes = [r for r in conn.execute("SELECT * FROM annonces WHERE name IS NOT NULL")
              if (pipeline._key_phone(r["phone"]) or pipeline._key_name(r["name"])) == cle]

    races = []
    for r in lignes:
        if r["race"] and r["race"] not in races:
            races.append(r["race"])

    def premier(champ):
        for r in lignes:
            if r[champ]:
                return r[champ]
        return ""

    return {
        "source_url": base["source_url"],
        "source_urls": [r["source_url"] for r in lignes],
        "name": base["name"],
        "races": races or ["Inconnue"],
        "phone": premier("phone"),
        "email": premier("email"),
        "website": premier("website"),
        "siren": premier("siren"),
        "ville": premier("ville"),
        "code_postal": premier("code_postal"),
        "departement": premier("departement"),
        "description": premier("description"),
        "photo_url": premier("photo_url"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slugs", nargs="*", help="slugs des sites a regenerer")
    ap.add_argument("--list", action="store_true", help="liste les sites regenerables")
    ap.add_argument("--all-since", metavar="AAAA-MM-JJ",
                    help="regenere tous les sites traites a partir de cette date")
    ap.add_argument("--no-commit", action="store_true", help="ne pas commiter")
    args = ap.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    if args.list:
        for r in conn.execute(
                "SELECT site_slug, name, processed_at FROM annonces "
                "WHERE site_slug IS NOT NULL AND site_slug != '' ORDER BY processed_at DESC"):
            print(f"  {r['site_slug']:45} {r['name']}  ({(r['processed_at'] or '')[:10]})")
        return

    slugs = list(args.slugs)
    if args.all_since:
        slugs += [r["site_slug"] for r in conn.execute(
            "SELECT DISTINCT site_slug FROM annonces WHERE site_slug IS NOT NULL "
            "AND site_slug != '' AND processed_at >= ?", (args.all_since,))]
    slugs = [s for s in dict.fromkeys(slugs) if s]

    if not slugs:
        print("Aucun slug. Utilise --list pour voir les sites disponibles.")
        return

    regeneres = []
    for slug in slugs:
        prof = profil_depuis_slug(conn, slug)
        if prof is None:
            print(f"❌ {slug} : introuvable en base")
            continue
        print(f"\n🔄 {prof['name']} — {', '.join(prof['races'])} — {prof['phone']}")
        url = pipeline.generate_demo_site(prof, force=True)
        if url:
            print(f"   ✅ {url}")
            regeneres.append(slug)
        else:
            print("   ❌ echec de generation")

    conn.close()

    if regeneres and not args.no_commit:
        subprocess.run(["git", "-C", str(REPO_ROOT), "add", "--"]
                       + [f"{s}/index.html" for s in regeneres], check=False)
        subprocess.run(["git", "-C", str(REPO_ROOT), "commit", "-m",
                        f"Regenere {len(regeneres)} site(s) : {', '.join(regeneres)}"], check=False)
        subprocess.run(["git", "-C", str(REPO_ROOT), "push", "origin", "main"], check=False)
        print(f"\n📤 {len(regeneres)} site(s) regenere(s) et pousse(s)")


if __name__ == "__main__":
    main()
