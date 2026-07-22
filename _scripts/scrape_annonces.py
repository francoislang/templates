#!/usr/bin/env python3
"""Scrape les petites annonces chien.com dans _data/annonces.db (table petites_annonces).

URLs prises depuis https://www.chien.com/sitemap-annonces.xml (~14700 annonces).
Idempotent (dedup par source_url), Ctrl-C safe (commit par ligne).

Usage:
    python3 _scripts/scrape_annonces.py                # scrape complet
    python3 _scripts/scrape_annonces.py --limit 10     # test rapide
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

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "annonces.db"
SITEMAP = "https://www.chien.com/sitemap-annonces.xml"

SCHEMA = """
CREATE TABLE IF NOT EXISTS petites_annonces (
    source_url            TEXT PRIMARY KEY,
    annonce_id            INTEGER,
    pays_dept_slug        TEXT,
    titre                 TEXT,
    race                  TEXT,
    prix                  TEXT,
    prix_min_eur          INTEGER,
    prix_max_eur          INTEGER,
    naissance             TEXT,
    pedigree              TEXT,
    nombre_males          INTEGER,
    nombre_femelles       INTEGER,
    nombre_total          INTEGER,
    vaccines              TEXT,
    sterilises            TEXT,
    identification        TEXT,
    date_annonce          TEXT,
    departement           TEXT,
    annonceur_nom         TEXT,
    annonceur_statut      TEXT,
    annonceur_code_postal TEXT,
    annonceur_ville       TEXT,
    annonceur_pays        TEXT,
    description           TEXT,
    photo_url             TEXT,
    scraped_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pa_race ON petites_annonces(race);
CREATE INDEX IF NOT EXISTS idx_pa_dept ON petites_annonces(departement);
CREATE INDEX IF NOT EXISTS idx_pa_statut ON petites_annonces(annonceur_statut);
"""

_INSERT = """INSERT OR IGNORE INTO petites_annonces (
    source_url, annonce_id, pays_dept_slug, titre, race, prix, prix_min_eur,
    prix_max_eur, naissance, pedigree, nombre_males, nombre_femelles, nombre_total,
    vaccines, sterilises, identification, date_annonce, departement,
    annonceur_nom, annonceur_statut, annonceur_code_postal, annonceur_ville, annonceur_pays,
    description, photo_url, scraped_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

_stop = False


def _sig(sig, frame):
    global _stop
    _stop = True
    print("\n[Ctrl-C] arrêt après l'annonce en cours...")


def _init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def fetch_sitemap_urls():
    """Retourne la liste des URLs d'annonces individuelles depuis le sitemap."""
    s = scraper._get_session()
    r = s.get(SITEMAP, timeout=60)
    urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
    is_annonce = re.compile(r"/annonces/[a-z]+-\d+/[^/]+-\d+\.php$")
    return [u.replace("//annonces", "/annonces") for u in urls if is_annonce.search(u)]


def _substring_before(text: str, anchors) -> str:
    """Coupe `text` avant le premier anchor trouvé."""
    stop = len(text)
    for anch in anchors:
        i = text.find(anch)
        if i >= 0 and i < stop:
            stop = i
    return text[:stop]


def _extract_portee_fields(text: str) -> dict:
    """Extrait les couples 'Label : valeur' du bloc 'Informations sur cette portée'.

    Le bloc est bordé en amont par 'Informations sur cette portée' et en aval par
    'Autres' / "Voir plus d'annonces" / 'Annonceur' / 'Adopter'.
    """
    result = {}
    anchor = text.find("Informations sur cette portée")
    if anchor < 0:
        return result
    block = text[anchor + len("Informations sur cette portée"):]
    block = _substring_before(
        block,
        ["Autres ", "Autre annonce", "Voir plus d'annonces", "Annonceur",
         "Adopter un", "Ce qu'il faut savoir", "Signaler"],
    )
    if len(block) > 2000:
        block = block[:2000]

    labels = ["Naissance", "Race", "Pedigree", "Nombre", "Prix", "Vaccinés",
              "Stérilisés", "N° identification", "Date de l'annonce"]

    for lbl in labels:
        others = [re.escape(x) for x in labels if x != lbl]
        pat = rf"{re.escape(lbl)}\s*:\s*(.+?)(?=\s+(?:{'|'.join(others)})\s*:|$)"
        m = re.search(pat, block, re.DOTALL)
        if m:
            result[lbl] = re.sub(r"\s+", " ", m.group(1)).strip()
    return result


def _extract_annonceur(text: str) -> dict:
    """Extrait annonceur nom/statut/adresse depuis le bloc 'Annonceur ...'."""
    result = {"nom": "", "statut": "", "code_postal": "", "ville": "", "pays": ""}
    idx = text.find("Annonceur")
    if idx < 0:
        return result

    block = text[idx + len("Annonceur"):]
    block = _substring_before(
        block, ["Plan d'accès", "Voir ses coordonnées", "Lui écrire",
                "Adopter un", "Ce qu'il faut savoir", "Créer une alerte"],
    )
    if len(block) > 500:
        block = block[:500]

    # Découpe : [nom] Statut : X [Adresse|Ville] : CP Ville Pays
    m_statut = re.search(r"Statut\s*:\s*([^\s].*?)(?=\s+(?:Adresse|Ville)\s*:|$)",
                          block, re.DOTALL)
    if m_statut:
        result["nom"] = block[:m_statut.start()].strip()
        result["statut"] = re.sub(r"\s+", " ", m_statut.group(1)).strip()

    m_addr = re.search(r"(?:Adresse|Ville)\s*:\s*(\d{4,5})\s+(.+?)(?:\s+(France|Belgique|Suisse|Canada|Luxembourg|Monaco|Espagne|Italie|Allemagne|Autriche|Royaume-Uni|États-Unis))?\s*$",
                        block)
    if m_addr:
        result["code_postal"] = m_addr.group(1)
        result["ville"] = m_addr.group(2).strip()
        result["pays"] = (m_addr.group(3) or "").strip()
    else:
        # fallback: juste CP + ville sans pays
        m2 = re.search(r"(?:Adresse|Ville)\s*:\s*(\d{4,5})\s+(\S[^:]*?)(?:\s{2,}|$)", block)
        if m2:
            result["code_postal"] = m2.group(1)
            result["ville"] = m2.group(2).strip()

    return result


def _parse_prix(prix_str: str):
    """Extrait (prix_min, prix_max) en euros depuis une chaîne comme '850 €' ou '1 800 €' ou '600 à 700 €'."""
    if not prix_str:
        return None, None
    # Merge thousand-separator spaces: "1 800" -> "1800"
    normalized = re.sub(r"(\d)\s+(\d{3})\b", r"\1\2", prix_str)
    nums = [int(n) for n in re.findall(r"\d+", normalized)]
    if not nums:
        return None, None
    return nums[0], (nums[-1] if len(nums) > 1 else nums[0])


def _split_naissance_type(s: str):
    """'19 mai 2026 Type : Border Collie' → ('19 mai 2026', 'Border Collie')."""
    if not s:
        return "", ""
    m = re.match(r"(.+?)\s*Type\s*:\s*(.+)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return s, ""


def _clean_date(s: str) -> str:
    """Ne garde que 'dd MONTH yyyy' au début, jette le reste."""
    if not s:
        return ""
    m = re.match(r"(\d{1,2}(?:er)?\s+\w+\s+\d{4})", s)
    return m.group(1) if m else s


def _parse_nombre(nb_str: str):
    if not nb_str:
        return None, None, None
    m_m = re.search(r"(\d+)\s*mâle", nb_str)
    m_f = re.search(r"(\d+)\s*femelle", nb_str)
    males = int(m_m.group(1)) if m_m else None
    femelles = int(m_f.group(1)) if m_f else None
    total = None
    if males is not None or femelles is not None:
        total = (males or 0) + (femelles or 0)
    return males, femelles, total


def extract(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    id_match = re.search(r"-(\d+)\.php$", url)
    annonce_id = int(id_match.group(1)) if id_match else None

    ps = re.search(r"/annonces/([a-z]+-\d+)/", url)
    pays_dept_slug = ps.group(1) if ps else ""
    dept_match = re.search(r"-(\d+)$", pays_dept_slug or "")
    departement = dept_match.group(1) if dept_match else ""

    h1 = soup.find("h1")
    titre = h1.get_text(" ", strip=True) if h1 else ""

    desc_el = soup.find(id="annonce_texte")
    description = re.sub(r"\s+", " ", desc_el.get_text(" ", strip=True)) if desc_el else ""

    photo_url = ""
    img = soup.select_one("#affichage_annonces_photos_first_a img")
    if not img:
        img = soup.select_one("img[src*='upload.chien.com/upload_global']")
    if img:
        photo_url = img.get("src", "")

    text = soup.get_text(" ", strip=True)

    portee = _extract_portee_fields(text)
    annonceur = _extract_annonceur(text)

    males, femelles, total = _parse_nombre(portee.get("Nombre", ""))
    prix_min, prix_max = _parse_prix(portee.get("Prix", ""))
    naissance, race_fallback = _split_naissance_type(portee.get("Naissance", ""))
    race = portee.get("Race", "") or race_fallback
    date_annonce = _clean_date(portee.get("Date de l'annonce", ""))

    return {
        "source_url": url,
        "annonce_id": annonce_id,
        "pays_dept_slug": pays_dept_slug,
        "titre": titre,
        "race": race,
        "prix": portee.get("Prix", ""),
        "prix_min_eur": prix_min,
        "prix_max_eur": prix_max,
        "naissance": naissance,
        "pedigree": portee.get("Pedigree", ""),
        "nombre_males": males,
        "nombre_femelles": femelles,
        "nombre_total": total,
        "vaccines": portee.get("Vaccinés", ""),
        "sterilises": portee.get("Stérilisés", ""),
        "identification": portee.get("N° identification", ""),
        "date_annonce": date_annonce,
        "departement": departement,
        "annonceur_nom": annonceur["nom"],
        "annonceur_statut": annonceur["statut"],
        "annonceur_code_postal": annonceur["code_postal"],
        "annonceur_ville": annonceur["ville"],
        "annonceur_pays": annonceur["pays"],
        "description": description[:5000],
        "photo_url": photo_url,
    }


def main():
    ap = argparse.ArgumentParser(description="Scrape les petites annonces chien.com.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Nombre max d'annonces à scraper (pour test)")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _sig)
    conn = _init_db()
    seen = {r[0] for r in conn.execute("SELECT source_url FROM petites_annonces")}
    print(f"DB : {DB_PATH}")
    print(f"Annonces déjà scrapées : {len(seen)}")

    print(f"Fetch sitemap {SITEMAP}...")
    urls = fetch_sitemap_urls()
    print(f"URLs annonces dans sitemap : {len(urls)}")

    todo = [u for u in urls if u not in seen]
    if args.limit:
        todo = todo[:args.limit]
    print(f"À scraper cette session : {len(todo)}")

    s = scraper._get_session()
    inserted = 0
    errors = 0

    for i, url in enumerate(todo):
        if _stop:
            break
        try:
            r = s.get(url, timeout=15)
            if r.status_code != 200:
                errors += 1
                time.sleep(scraper.DELAY)
                continue
            d = extract(url, r.text)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(_INSERT, (
                d["source_url"], d["annonce_id"], d["pays_dept_slug"],
                d["titre"], d["race"], d["prix"], d["prix_min_eur"],
                d["prix_max_eur"], d["naissance"], d["pedigree"],
                d["nombre_males"], d["nombre_femelles"], d["nombre_total"],
                d["vaccines"], d["sterilises"], d["identification"],
                d["date_annonce"], d["departement"],
                d["annonceur_nom"], d["annonceur_statut"],
                d["annonceur_code_postal"], d["annonceur_ville"], d["annonceur_pays"],
                d["description"], d["photo_url"], now,
            ))
            conn.commit()
            inserted += 1
        except Exception as e:
            errors += 1
            print(f"  ! erreur {url}: {e}")

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(todo)} | insérés {inserted} | erreurs {errors}]")

        time.sleep(scraper.DELAY)

    total = conn.execute("SELECT COUNT(*) FROM petites_annonces").fetchone()[0]
    print(f"\nTerminé. Insérés cette session : {inserted}. "
          f"Total DB : {total}. Erreurs : {errors}.")
    conn.close()


if __name__ == "__main__":
    main()
