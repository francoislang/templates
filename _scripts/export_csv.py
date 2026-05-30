#!/usr/bin/env python3
"""
Exporte les resultats du scraping en CSV pour analyse dans Excel/Google Sheets.

Usage:
    python _scripts/export_csv.py                    # scrape + export
    python _scripts/export_csv.py --pages 3          # 3 pages de listing
    python _scripts/export_csv.py --max 5            # max 5 eleveurs
    python _scripts/export_csv.py --output prospects.csv
"""
import sys
import os
import csv
import argparse

sys.path.insert(0, os.path.dirname(__file__))

import scraper


def export_to_csv(profiles: list[dict], output_path: str) -> None:
    """Exporte les profils en CSV."""
    fieldnames = [
        "nom", "race", "telephone", "email", "site_web",
        "siren", "acaced", "statut", "ville", "code_postal",
        "departement", "description_courte", "photo_url", "source_url",
    ]

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=",")
        writer.writeheader()

        for p in profiles:
            desc = p.get("description", "")
            writer.writerow({
                "nom": p.get("name", ""),
                "race": ", ".join(p.get("races", [])),
                "telephone": p.get("phone", ""),
                "email": p.get("email", ""),
                "site_web": p.get("website", ""),
                "siren": p.get("siren", ""),
                "acaced": p.get("acaced", ""),
                "statut": p.get("statut", ""),
                "ville": p.get("ville", ""),
                "code_postal": p.get("code_postal", ""),
                "departement": p.get("departement", ""),
                "description_courte": desc[:200] if desc else "",
                "photo_url": p.get("photo_url", ""),
                "source_url": p.get("source_url", ""),
            })

    print(f"✅ {len(profiles)} eleveurs exportes dans {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape chien.com et exporte en CSV"
    )
    parser.add_argument(
        "--pages", type=int, default=5,
        help="Nombre de pages a parcourir (defaut: 5)"
    )
    parser.add_argument(
        "--max", type=int, default=10,
        help="Nombre max d'eleveurs (defaut: 10)"
    )
    parser.add_argument(
        "--output", type=str, default="prospects.csv",
        help="Fichier CSV de sortie (defaut: prospects.csv)"
    )
    parser.add_argument(
        "--start-page", type=int, default=1,
        help="Page de depart (defaut: 1)"
    )

    args = parser.parse_args()

    print(f"🔍 Scraping de {args.pages} pages (max {args.max} eleveurs)...")
    profiles = scraper.scrape(
        pages=args.pages,
        max_results=args.max,
        start_page=args.start_page,
    )

    if not profiles:
        print("ℹ️ Aucun profil trouve.")
        return

    export_to_csv(profiles, args.output)

    # Resume
    races = {}
    for p in profiles:
        race = p["races"][0] if p.get("races") else "Inconnue"
        races[race] = races.get(race, 0) + 1

    print(f"\n📊 Resume par race :")
    for race, count in sorted(races.items(), key=lambda x: -x[1]):
        print(f"   {race}: {count}")


if __name__ == "__main__":
    main()
