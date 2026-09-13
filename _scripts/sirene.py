#!/usr/bin/env python3
"""Construit une base de prospects depuis l'API Recherche d'entreprises (data.gouv.fr).

Source ouverte, gratuite, sans clé : https://recherche-entreprises.api.gouv.fr
Remplit la table `sirene` de _data/annonces.db.

ATTENTION : SIRENE ne contient NI telephone, NI email, NI site web.
Ce script produit la liste de depart (qui existe, ou, quelle taille, quelle
anciennete). L'enrichissement contact est une deuxieme etape (Google Places,
scraping cible, etc.).

Usage:
    python3 _scripts/sirene.py --naf 33.15Z
    python3 _scripts/sirene.py --naf 33.15Z --naf 30.12Z --effectif-min 1
    python3 _scripts/sirene.py --naf 33.15Z --departements 06,83,13,34,29,56,44,85,17
    python3 _scripts/sirene.py --naf 33.15Z --stats
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import json
from datetime import datetime, timezone
from pathlib import Path

API = "https://recherche-entreprises.api.gouv.fr/search"
REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "annonces.db"
PER_PAGE = 25
DELAY = 0.25  # l'API publique est limitee en req/s -- ne pas descendre plus bas

# Tranches d'effectif INSEE. NN = non renseigne, 00 = 0 salarie.
# Le coeur de cible (atelier tenu par son patron) = 01 a 21.
TRANCHES_AVEC_SALARIES = ["01", "02", "03", "11", "12", "21", "22"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS sirene (
    siren            TEXT PRIMARY KEY,
    nom              TEXT,
    enseigne         TEXT,
    naf              TEXT,
    naf_libelle      TEXT,
    nature_juridique TEXT,
    effectif         TEXT,
    date_creation    TEXT,
    dirigeant        TEXT,
    adresse          TEXT,
    code_postal      TEXT,
    ville            TEXT,
    departement      TEXT,
    latitude         REAL,
    longitude        REAL,
    siret_siege      TEXT,
    ca               INTEGER,
    -- champs remplis par l'etape d'enrichissement, vides a ce stade
    telephone        TEXT,
    site_web         TEXT,
    email            TEXT,
    enrichi_at       TEXT,
    fetched_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sirene_naf  ON sirene(naf);
CREATE INDEX IF NOT EXISTS idx_sirene_dept ON sirene(departement);
CREATE INDEX IF NOT EXISTS idx_sirene_site ON sirene(site_web);
"""

_INSERT = """INSERT OR IGNORE INTO sirene (
    siren, nom, enseigne, naf, naf_libelle, nature_juridique, effectif,
    date_creation, dirigeant, adresse, code_postal, ville, departement,
    latitude, longitude, siret_siege, ca, fetched_at
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""


def _get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "prospection/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as exc:  # 429 / timeout -> backoff
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    return {}


def _dirigeant(item: dict) -> str:
    for d in (item.get("dirigeants") or []):
        nom = " ".join(
            x for x in [d.get("prenoms"), d.get("nom")] if x
        ).strip()
        if nom:
            return nom
        if d.get("denomination"):
            return d["denomination"]
    return ""


def _row(item: dict, now: str) -> tuple:
    s = item.get("siege") or {}
    fin = item.get("finances") or {}
    ca = None
    if fin:
        derniere = sorted(fin.keys())[-1]
        ca = (fin[derniere] or {}).get("ca")
    enseignes = s.get("liste_enseignes") or []
    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return (
        item.get("siren"),
        item.get("nom_complet"),
        enseignes[0] if enseignes else None,
        item.get("activite_principale"),
        None,
        item.get("nature_juridique"),
        item.get("tranche_effectif_salarie"),
        item.get("date_creation"),
        _dirigeant(item),
        s.get("adresse"),
        s.get("code_postal"),
        s.get("libelle_commune"),
        s.get("departement"),
        _f(s.get("latitude")),
        _f(s.get("longitude")),
        s.get("siret"),
        ca,
        now,
    )


def collect(conn, naf: str, departement: str | None, effectif_min: bool) -> int:
    """Pagine l'API pour un couple (naf, departement). Retourne le nb insere."""
    base = {
        "activite_principale": naf,      # format avec point : 33.15Z
        "etat_administratif": "A",       # entreprises actives uniquement
        "per_page": PER_PAGE,
    }
    if departement:
        base["departement"] = departement
    if effectif_min:
        base["tranche_effectif_salarie"] = ",".join(TRANCHES_AVEC_SALARIES)

    first = _get(dict(base, page=1))
    total = first.get("total_results", 0)
    pages = first.get("total_pages", 0)
    label = f"{naf}" + (f" dept {departement}" if departement else "")
    print(f"  {label}: {total} resultats / {pages} pages")

    # L'API plafonne la pagination profonde : au-dela, decouper par departement.
    if pages > 400:
        print("    /!\\ trop de pages -- relance avec --departements pour decouper")

    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    page = 1
    while page <= pages:
        data = first if page == 1 else _get(dict(base, page=page))
        results = data.get("results") or []
        if not results:
            break
        rows = [_row(it, now) for it in results]
        cur = conn.executemany(_INSERT, rows)
        conn.commit()
        inserted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        page += 1
        time.sleep(DELAY)
    return inserted


def stats(conn, naf_filter=None):
    where = ""
    args = []
    if naf_filter:
        where = " WHERE naf IN (%s)" % ",".join("?" * len(naf_filter))
        args = naf_filter
    total = conn.execute(f"SELECT COUNT(*) FROM sirene{where}", args).fetchone()[0]
    print(f"\n{total} entreprises en base")
    print("\nPar effectif :")
    for eff, n in conn.execute(
        f"SELECT COALESCE(effectif,'NN'), COUNT(*) FROM sirene{where} "
        "GROUP BY 1 ORDER BY 2 DESC", args
    ):
        print(f"  {eff:>4} : {n}")
    print("\nTop 15 departements :")
    for dept, n in conn.execute(
        f"SELECT departement, COUNT(*) FROM sirene{where} "
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 15", args
    ):
        print(f"  {dept} : {n}")
    enrichis = conn.execute(
        f"SELECT COUNT(*) FROM sirene{where}" + (" AND" if where else " WHERE") +
        " enrichi_at IS NOT NULL", args
    ).fetchone()[0]
    print(f"\nEnrichis (contact trouve) : {enrichis} / {total}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--naf", action="append", required=True,
                   help="code NAF avec le point, ex: 33.15Z (repetable)")
    p.add_argument("--departements", default=None,
                   help="liste separee par virgules, ex: 06,83,13,29,56")
    p.add_argument("--effectif-min", action="store_true",
                   help="ne garder que les entreprises avec au moins 1 salarie")
    p.add_argument("--stats", action="store_true", help="afficher les stats et sortir")
    args = p.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    if args.stats:
        stats(conn, args.naf)
        return

    depts = args.departements.split(",") if args.departements else [None]
    total = 0
    for naf in args.naf:
        print(f"\nNAF {naf}")
        for d in depts:
            total += collect(conn, naf, d, args.effectif_min)

    print(f"\n{total} nouvelles lignes inserees dans {DB_PATH}")
    stats(conn, args.naf)


if __name__ == "__main__":
    main()
