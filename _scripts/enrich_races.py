#!/usr/bin/env python3
"""Enrichit la colonne `race` de `petites_annonces` en dérivant depuis l'URL ou le titre.

Ne touche pas les races déjà parsées. Ajoute une colonne `race_source` :
- 'parsed' : extrait du bloc structuré "Informations sur cette portée" au scrape
- 'url'    : slug de race chien.com trouvé dans l'URL de l'annonce
- 'title'  : matché sur le titre de l'annonce
- NULL     : pas trouvée
"""
from __future__ import annotations

import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scraper import SLUG_TO_RACE, _get_session

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "annonces.db"

# Prefixes de slugs sitemap-races.xml qui ne sont pas des races (guides / rubriques)
_NOISE_PREFIXES = (
    "alimentation-", "education-", "sante-", "caractere-", "entretien-",
    "prix-", "eleveur", "elevages-", "adopter-un-", "achat-", "vente-",
    "toilettage-", "assurance-", "dressage-", "comportement-",
)


def fetch_chien_race_slugs() -> list[str]:
    """Récupère les slugs de race depuis sitemap-races.xml (filtrés)."""
    s = _get_session()
    r = s.get("https://www.chien.com/sitemap-races.xml", timeout=60)
    urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
    slugs = set()
    for u in urls:
        m = re.search(r"/races-de-chiens/([a-z][a-z0-9-]+)-(\d+)\.php$", u)
        if not m:
            continue
        slug = m.group(1)
        if slug.startswith(_NOISE_PREFIXES):
            continue
        if "race-chien" in slug:  # groupes/filtres
            continue
        slugs.add(slug)
    return sorted(slugs)


def slug_to_name(slug: str) -> str:
    """Convertit 'english-springer-spaniel' → 'English Springer Spaniel'.

    Les mots courts (à, de, du, des, la, le, les, et) restent en minuscule.
    """
    lower_words = {"a", "de", "du", "des", "la", "le", "les", "et", "d", "l"}
    parts = slug.split("-")
    return " ".join(w if w in lower_words else w.capitalize() for w in parts)


def norm(s: str) -> str:
    """lowercase + strip accents."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


def _add_column_if_missing(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(petites_annonces)")]
    if "race_source" not in cols:
        conn.execute("ALTER TABLE petites_annonces ADD COLUMN race_source TEXT")
    conn.execute(
        "UPDATE petites_annonces SET race_source = 'parsed' "
        "WHERE race IS NOT NULL AND race != '' AND race_source IS NULL"
    )
    conn.commit()


def _build_title_matchers(canonical: list[str]):
    """Compile un regex par race, avec boundaries word, sur texte normalisé."""
    # Longest first pour préférer "Berger Australien Miniature" à "Berger Australien"
    canonical_sorted = sorted(set(canonical), key=len, reverse=True)
    out = []
    for r in canonical_sorted:
        n = norm(r)
        if not n:
            continue
        escaped = re.escape(n).replace(r"\ ", r"\s+")
        out.append((r, re.compile(rf"\b{escaped}\b")))
    return out


def _build_url_matchers():
    """Renvoie une liste (slug, nom_race) triée par slug le plus long d'abord.

    Combine :
    - Les 1400+ slugs de chien.com/sitemap-races.xml (nommés via slug_to_name)
    - Les SLUG_TO_RACE de scraper.py (avec leur nom canonique)
    """
    kws = {}
    # 1) SLUG_TO_RACE (plus haute priorité : nom canonique déjà défini)
    for elevage_slug, race in SLUG_TO_RACE.items():
        if race:
            kws[elevage_slug.replace("elevage-", "")] = race
    # 2) sitemap-races (nom dérivé par slug_to_name)
    try:
        for slug in fetch_chien_race_slugs():
            kws.setdefault(slug, slug_to_name(slug))
    except Exception as e:
        print(f"! sitemap-races.xml indisponible ({e}), on utilise seulement SLUG_TO_RACE")
    return sorted(kws.items(), key=lambda kv: len(kv[0]), reverse=True)


def main():
    conn = sqlite3.connect(str(DB_PATH))
    _add_column_if_missing(conn)

    parsed = {r for (r,) in conn.execute(
        "SELECT DISTINCT race FROM petites_annonces WHERE race IS NOT NULL AND race != ''"
    )}
    # Réunit races parsées + toutes les races connues dans SLUG_TO_RACE
    canonical = list(parsed | {v for v in SLUG_TO_RACE.values() if v})
    title_matchers = _build_title_matchers(canonical)
    url_matchers = _build_url_matchers()

    rows = list(conn.execute(
        "SELECT source_url, titre FROM petites_annonces "
        "WHERE race IS NULL OR race = ''"
    ))
    print(f"Annonces à enrichir : {len(rows)}")

    from_title = from_url = still_empty = 0

    for source_url, titre in rows:
        found = None
        source = None

        # 1) URL slug (prioritaire : plus fiable que le texte libre du titre)
        url_n = norm(source_url)
        for kw, race in url_matchers:
            if re.search(rf"(?:^|[^a-z0-9]){re.escape(kw)}(?:$|[^a-z0-9])", url_n):
                found = race
                source = "url"
                break

        # 2) Titre en fallback
        if not found:
            titre_n = norm(titre)
            for race, rgx in title_matchers:
                if rgx.search(titre_n):
                    found = race
                    source = "title"
                    break

        if found:
            conn.execute(
                "UPDATE petites_annonces SET race = ?, race_source = ? WHERE source_url = ?",
                (found, source, source_url),
            )
            if source == "url":
                from_url += 1
            else:
                from_title += 1
        else:
            still_empty += 1

    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM petites_annonces").fetchone()[0]
    filled = conn.execute(
        "SELECT COUNT(*) FROM petites_annonces WHERE race IS NOT NULL AND race != ''"
    ).fetchone()[0]

    def cnt(src):
        return conn.execute(
            "SELECT COUNT(*) FROM petites_annonces WHERE race_source = ?", (src,)
        ).fetchone()[0]

    print()
    print(f"Total annonces          : {total}")
    print(f"Avec race après enrichi : {filled} ({filled/total*100:.1f}%)")
    print(f"  parsed  : {cnt('parsed')}")
    print(f"  title   : {cnt('title')}  (+{from_title} nouveau)")
    print(f"  url     : {cnt('url')}    (+{from_url} nouveau)")
    print(f"  encore vide : {still_empty}")


if __name__ == "__main__":
    main()
