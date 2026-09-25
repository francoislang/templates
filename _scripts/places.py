#!/usr/bin/env python3
"""Enrichit la table `sirene` avec les contacts trouves via Google Places (New).

Deuxieme etape de la prospection hors-canine :

    1. sirene.py  -> qui existe, ou, quelle taille  (gratuit, exhaustif, sans cle)
    2. places.py  -> telephone, site web, note, nombre d'avis   (ce script)
    3. pipeline   -> generation + CRM + relances                (deja en place)

Le signal de prospect est l'ABSENCE de `websiteUri` chez Google : c'est
l'equivalent exact du champ vide sur chien.com, mais sur n'importe quel
metier. `userRatingCount` sert de proxy de taille : un chantier a 80 avis
tourne, un a 2 avis n'a pas de budget.

Cle API : GOOGLE_PLACES_API_KEY dans .env
    console.cloud.google.com -> APIs & Services -> Places API (New)
    Restreindre la cle a "Places API (New)" avant de s'en servir.

Cout : Text Search Pro ~ 0,032 $/appel, + ~0,003 $ pour les champs contact.
Un appel par entreprise. Le credit mensuel Google couvre les premiers
milliers d'appels. Le script refuse de depasser --max-appels (defaut 500)
et affiche l'estimation avant de commencer.

Usage :
    python3 _scripts/places.py --naf 33.15Z --max-appels 200
    python3 _scripts/places.py --naf 33.15Z --naf 30.12Z --departements 29,56,44,85,17
    python3 _scripts/places.py --naf 33.15Z --prospects        # aucun appel, lecture seule
    python3 _scripts/places.py --naf 33.15Z --prospects --csv prospects.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402  (charge le .env)

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "annonces.db"

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
])
DELAY = 0.12          # ~8 req/s, tres en dessous du quota Google
RAYON_M = 3000.0      # biais geographique autour des coordonnees SIRENE
COUT_APPEL = 0.035    # $ : Text Search Pro + champs contact

# Colonnes ajoutees par ce script si elles manquent (sirene.py est anterieur).
COLONNES_SUP = {
    "place_id": "TEXT",
    "note": "REAL",
    "avis": "INTEGER",
    "statut_google": "TEXT",
    "confiance": "TEXT",
}

FORMES_JURIDIQUES = {
    "sarl", "sas", "sasu", "eurl", "sa", "sci", "scop", "snc", "gie", "eirl",
    "ei", "scm", "selarl", "sarlu", "etablissements", "ets", "societe", "ste",
    "entreprise", "chantier", "chantiers", "naval", "navals", "nautique",
    "nautic", "marine", "monsieur", "madame", "mr", "mme",
}


# --------------------------------------------------------------------------
# utilitaires
# --------------------------------------------------------------------------

def _cle() -> str:
    cle = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if not cle:
        sys.exit(
            "GOOGLE_PLACES_API_KEY absente du .env.\n"
            "  console.cloud.google.com > APIs & Services > Places API (New)\n"
            "  puis : echo 'GOOGLE_PLACES_API_KEY=...' >> .env"
        )
    return cle


def _normaliser(txt: str) -> str:
    """minuscules, sans accents, sans ponctuation."""
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", txt.lower()).strip()


def _jetons(nom: str) -> set[str]:
    mots = _normaliser(nom).split()
    utiles = {m for m in mots if len(m) > 2 and m not in FORMES_JURIDIQUES}
    return utiles or set(mots)


def _confiance(nom_sirene: str, nom_google: str) -> str:
    """haute / moyenne / faible selon le recouvrement des noms."""
    a, b = _jetons(nom_sirene), _jetons(nom_google)
    if not a or not b:
        return "faible"
    commun = len(a & b)
    if commun == 0:
        return "faible"
    if commun >= min(len(a), len(b)):
        return "haute"
    return "moyenne"


def _requete(cle: str, texte: str, lat, lon) -> dict | None:
    corps: dict = {
        "textQuery": texte,
        "languageCode": "fr",
        "regionCode": "FR",
        "maxResultCount": 1,
    }
    if lat is not None and lon is not None:
        corps["locationBias"] = {
            "circle": {
                "center": {"latitude": float(lat), "longitude": float(lon)},
                "radius": RAYON_M,
            }
        }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(corps).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": cle,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        method="POST",
    )
    for tentative in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            lieux = data.get("places") or []
            return lieux[0] if lieux else None
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401, 403):
                detail = exc.read().decode("utf-8", "replace")[:400]
                sys.exit(f"\nGoogle refuse la requete ({exc.code}) :\n{detail}")
            if tentative == 3:
                print(f"    ! HTTP {exc.code}, abandon de cette ligne")
                return None
            time.sleep(2 ** tentative)
        except Exception as exc:
            if tentative == 3:
                print(f"    ! {exc}, abandon de cette ligne")
                return None
            time.sleep(2 ** tentative)
    return None


# --------------------------------------------------------------------------
# base
# --------------------------------------------------------------------------

def _preparer(conn: sqlite3.Connection) -> None:
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "sirene" not in tables:
        sys.exit(
            "La table `sirene` n'existe pas encore.\n"
            "  Lance d'abord :  python3 _scripts/sirene.py --naf 33.15Z"
        )
    existantes = {r[1] for r in conn.execute("PRAGMA table_info(sirene)")}
    for col, typ in COLONNES_SUP.items():
        if col not in existantes:
            conn.execute(f"ALTER TABLE sirene ADD COLUMN {col} {typ}")
    conn.commit()


def _filtre(naf: list[str] | None, depts: list[str] | None) -> tuple[str, list]:
    clauses, args = [], []
    if naf:
        clauses.append("naf IN (%s)" % ",".join("?" * len(naf)))
        args += naf
    if depts:
        clauses.append("departement IN (%s)" % ",".join("?" * len(depts)))
        args += depts
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", args


# --------------------------------------------------------------------------
# enrichissement
# --------------------------------------------------------------------------

def enrichir(conn, naf, depts, max_appels: int, dry_run: bool) -> None:
    where, args = _filtre(naf, depts)
    jointure = " AND " if where else " WHERE "
    sql = (
        "SELECT siren, nom, enseigne, adresse, code_postal, ville, latitude, longitude "
        f"FROM sirene{where}{jointure}enrichi_at IS NULL "
        "ORDER BY COALESCE(effectif,'00') DESC, date_creation ASC "
        f"LIMIT {int(max_appels)}"
    )
    lignes = conn.execute(sql, args).fetchall()
    if not lignes:
        print("Rien a enrichir (tout est deja fait, ou le filtre ne renvoie rien).")
        return

    reste = conn.execute(
        f"SELECT COUNT(*) FROM sirene{where}{jointure}enrichi_at IS NULL", args
    ).fetchone()[0]
    print(f"{len(lignes)} lignes a interroger (sur {reste} non enrichies)")
    print(f"Cout estime : {len(lignes) * COUT_APPEL:.2f} $ "
          f"(plafond dur : {max_appels} appels, soit {max_appels * COUT_APPEL:.2f} $)")
    if dry_run:
        print("--dry-run : aucun appel envoye.")
        for siren, nom, enseigne, adr, cp, ville, *_ in lignes[:10]:
            print(f"  {siren}  {nom}  ({cp} {ville})")
        return

    cle = _cle()
    maintenant = datetime.now(timezone.utc).isoformat(timespec="seconds")
    trouves = sans_site = appels = 0

    for i, (siren, nom, enseigne, adr, cp, ville, lat, lon) in enumerate(lignes, 1):
        if appels >= max_appels:
            print(f"\nPlafond de {max_appels} appels atteint, arret propre. "
                  f"Relance la commande pour continuer la ou elle s'est arretee.")
            break
        # L'enseigne est le nom commercial (celui que Google connait), le nom
        # est la raison sociale. On tente l'enseigne, puis la raison sociale.
        libelle = (enseigne or nom or "").strip()
        essais = [libelle]
        if nom and _normaliser(nom) != _normaliser(libelle):
            essais.append(nom.strip())

        lieu = None
        for essai in essais:
            if appels >= max_appels:
                break
            texte = " ".join(x for x in (essai, adr, cp, ville) if x)
            lieu = _requete(cle, texte, lat, lon)
            appels += 1
            time.sleep(DELAY)
            if lieu:
                break

        if not lieu:
            conn.execute(
                "UPDATE sirene SET enrichi_at=?, confiance='introuvable' WHERE siren=?",
                (maintenant, siren),
            )
            print(f"  [{i}/{len(lignes)}] {libelle[:38]:38} — introuvable")
            continue

        nom_g = (lieu.get("displayName") or {}).get("text", "")
        tel = lieu.get("nationalPhoneNumber", "") or ""
        site = lieu.get("websiteUri", "") or ""
        conf = _confiance(libelle, nom_g)
        trouves += 1
        if not site:
            sans_site += 1

        conn.execute(
            "UPDATE sirene SET telephone=?, site_web=?, place_id=?, note=?, avis=?, "
            "statut_google=?, confiance=?, enrichi_at=? WHERE siren=?",
            (
                tel, site, lieu.get("id"), lieu.get("rating"),
                lieu.get("userRatingCount"), lieu.get("businessStatus"),
                conf, maintenant, siren,
            ),
        )
        if i % 20 == 0:
            conn.commit()

        marque = "PROSPECT" if (not site and tel) else ("site" if site else "—")
        print(
            f"  [{i}/{len(lignes)}] {libelle[:38]:38} {conf:8} "
            f"{(tel or '—'):16} {marque}"
        )

    conn.commit()
    print(f"\n{trouves} fiches Google trouvees, dont {sans_site} sans site web.")
    print(f"{appels} appels envoyes, cout reel : ~{appels * COUT_APPEL:.2f} $")


# --------------------------------------------------------------------------
# lecture : la liste de prospects
# --------------------------------------------------------------------------

def prospects(conn, naf, depts, chemin_csv: str | None, mini_avis: int) -> None:
    where, args = _filtre(naf, depts)
    jointure = " AND " if where else " WHERE "
    sql = (
        "SELECT nom, enseigne, dirigeant, telephone, ville, code_postal, departement, "
        "note, avis, confiance, siren "
        f"FROM sirene{where}{jointure}"
        "enrichi_at IS NOT NULL "
        "AND COALESCE(site_web,'')='' "
        "AND COALESCE(telephone,'')<>'' "
        "AND confiance IN ('haute','moyenne') "
        "AND COALESCE(statut_google,'OPERATIONAL')='OPERATIONAL' "
        f"AND COALESCE(avis,0) >= {int(mini_avis)} "
        "ORDER BY COALESCE(avis,0) DESC, COALESCE(note,0) DESC"
    )
    lignes = conn.execute(sql, args).fetchall()
    entetes = ["nom", "enseigne", "dirigeant", "telephone", "ville", "code_postal",
               "departement", "note", "avis", "confiance", "siren"]

    print(f"\n{len(lignes)} prospects : joignables, sans site web, actifs sur Google\n")
    for nom, ens, dir_, tel, ville, cp, dept, note, avis, conf, siren in lignes[:40]:
        etoiles = f"{note:.1f}*{avis}" if note else "—"
        print(f"  {(ens or nom)[:34]:34} {tel:16} {(cp or ''):6} {(ville or '')[:18]:18} "
              f"{etoiles:9} {(dir_ or '')[:22]}")
    if len(lignes) > 40:
        print(f"  ... et {len(lignes) - 40} autres")

    if chemin_csv:
        dest = Path(chemin_csv)
        with dest.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(entetes)
            w.writerows(lignes)
        print(f"\n-> {len(lignes)} lignes ecrites dans {dest}")


def stats(conn, naf, depts) -> None:
    where, args = _filtre(naf, depts)
    jointure = " AND " if where else " WHERE "
    tot = conn.execute(f"SELECT COUNT(*) FROM sirene{where}", args).fetchone()[0]
    enr = conn.execute(
        f"SELECT COUNT(*) FROM sirene{where}{jointure}enrichi_at IS NOT NULL", args
    ).fetchone()[0]
    sans = conn.execute(
        f"SELECT COUNT(*) FROM sirene{where}{jointure}"
        "enrichi_at IS NOT NULL AND COALESCE(site_web,'')='' "
        "AND COALESCE(telephone,'')<>''", args
    ).fetchone()[0]
    print(f"\n{tot} en base | {enr} enrichies | {sans} sans site + joignables")
    if enr:
        print("\nConfiance du rapprochement SIRENE <-> Google :")
        for conf, n in conn.execute(
            f"SELECT COALESCE(confiance,'?'), COUNT(*) FROM sirene{where}{jointure}"
            "enrichi_at IS NOT NULL GROUP BY 1 ORDER BY 2 DESC", args
        ):
            print(f"  {conf:12} : {n}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--naf", action="append",
                   help="code NAF avec le point, ex: 33.15Z (repetable)")
    p.add_argument("--departements", default=None,
                   help="liste separee par virgules, ex: 29,56,44,85,17")
    p.add_argument("--max-appels", type=int, default=500,
                   help="plafond d'appels Google pour cette execution (defaut 500)")
    p.add_argument("--dry-run", action="store_true",
                   help="montre ce qui serait interroge, sans appeler Google")
    p.add_argument("--prospects", action="store_true",
                   help="lecture seule : liste les prospects qualifies")
    p.add_argument("--min-avis", type=int, default=0,
                   help="avec --prospects : nombre minimum d'avis Google")
    p.add_argument("--csv", default=None, help="avec --prospects : fichier de sortie")
    p.add_argument("--stats", action="store_true", help="compteurs et sortie")
    args = p.parse_args()

    depts = args.departements.split(",") if args.departements else None
    conn = sqlite3.connect(DB_PATH)
    _preparer(conn)

    if args.stats:
        stats(conn, args.naf, depts)
    elif args.prospects:
        prospects(conn, args.naf, depts, args.csv, args.min_avis)
    else:
        enrichir(conn, args.naf, depts, args.max_appels, args.dry_run)
        stats(conn, args.naf, depts)
    conn.close()


if __name__ == "__main__":
    main()
