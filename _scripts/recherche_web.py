#!/usr/bin/env python3
"""Constitue une base de prospects locaux a partir de l'API de recherche Brave.

Pourquoi Brave et pas du scraping : les pages Facebook et les annuaires
interdisent l'aspiration automatique et repondent par des CAPTCHA. L'API de
recherche de Brave est un acces prevu pour ca, sans blocage, a 5 $ les 1000
requetes avec 5 $ de credit offert chaque mois — soit 1000 requetes gratuites,
environ 140 communes par mois.

Methode, en trois temps, validee a la main avant d'etre codee :

  1. RECENSER   site:facebook.com garage automobile mecanique <commune>
                Facebook est un annuaire exhaustif de commerces locaux, et les
                agregateurs n'y figurent pas puisqu'ils ne sont pas des
                commerces. Une requete par commune.

  2. RESOUDRE   "<nom exact>" <commune>
                Si un domaine propre apparait, l'entreprise a un site. S'il n'y
                a que des annuaires, elle n'en a pas : c'est un prospect.

  3. ENREGISTRER  chaque ligne conserve ses sources, pour qu'on puisse toujours
                  savoir d'ou vient une information et la reverifier.

Ce que la base garantit :
  - toute information est horodatee et tracee (colonne `sources`)
  - `site_statut` est explicite ('aucun', 'propre', 'reseau', 'inconnu'),
    jamais devine en silence
  - une valeur verifiee n'est jamais ecrasee par une valeur vide
  - la base vit dans _data/, ignoree par git : elle ne part pas sur le
    depot public

Cle API : BRAVE_API_KEY dans .env  (api-dashboard.search.brave.com)

Usage :
    python3 _scripts/recherche_web.py --commune Vitre
    python3 _scripts/recherche_web.py --tournee 5          # 5 communes de la liste
    python3 _scripts/recherche_web.py --prospects
    python3 _scripts/recherche_web.py --prospects --csv prospects.csv
    python3 _scripts/recherche_web.py --stats
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
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "prospection.db"
API = "https://api.search.brave.com/res/v1/web/search"
DELAI = 1.2          # l'offre gratuite plafonne a 1 requete/seconde
COUT_REQUETE = 0.005  # $


# --------------------------------------------------------------------------
# connaissances metier
# --------------------------------------------------------------------------

# Villes moyennes, 8 000 a 40 000 habitants, aucune banlieue de metropole.
# Le choix n'est pas anodin : a Cesson-Sevigne (banlieue aisee de Rennes) les
# cinq garages verifies avaient deja un site ; a Vitre, les deux premiers
# independants n'en avaient aucun. La commune pese plus que le metier.
COMMUNES = [
    "Vitré", "Fougères", "Redon", "Ancenis", "Cholet", "Saumur", "Mayenne",
    "Château-Gontier", "Flers", "Alençon", "Lisieux", "Vire", "Coutances",
    "Avranches", "Morlaix", "Landerneau", "Quimperlé", "Pontivy", "Ploërmel",
    "Auray", "Guingamp", "Lannion", "Dinan", "Loudéac", "Châteaubriant",
    "Pornic", "Les Herbiers", "Fontenay-le-Comte", "Bressuire", "Thouars",
    "Cognac", "Saintes", "Rochefort", "Libourne", "Marmande",
    "Villeneuve-sur-Lot", "Figeac", "Rodez", "Millau", "Castres", "Albi",
    "Carmaux", "Alès", "Béziers", "Carcassonne", "Narbonne",
    "Digne-les-Bains", "Manosque", "Gap", "Romans-sur-Isère", "Montélimar",
    "Aubenas", "Roanne", "Montbrison", "Vichy", "Montluçon", "Moulins",
    "Nevers", "Auxerre", "Sens", "Chaumont", "Saint-Dizier", "Épinal",
    "Lunéville", "Saint-Avold", "Haguenau", "Sélestat", "Guebwiller", "Dole",
    "Lons-le-Saunier", "Mâcon", "Autun", "Montceau-les-Mines", "Vierzon",
    "Châteauroux", "Issoudun", "Montargis", "Dreux", "Nogent-le-Rotrou",
    "Vernon", "Louviers", "Dieppe", "Fécamp", "Abbeville", "Soissons", "Laon",
    "Château-Thierry", "Épernay",
]

# Hotes qui ne sont jamais le site de l'entreprise elle-meme.
ANNUAIRES = {
    "facebook.com", "m.facebook.com", "web.facebook.com", "fb.com",
    "instagram.com", "linkedin.com", "youtube.com", "x.com", "twitter.com",
    "pagesjaunes.fr", "vroomly.com", "idgarages.com", "mecazen.fr",
    "top-garage.fr", "mappy.com", "fr.mappy.com", "cylex-locale.fr",
    "cylex.fr", "societe.com", "verif.com", "manageo.fr", "infogreffe.fr",
    "annuaire-entreprises.data.gouv.fr", "doctrine.fr", "infobel.com",
    "infoisinfo.fr", "autour-de-moi.pro", "autour-de-moi.com", "lesgarages.fr",
    "e-pro.fr", "automobile.e-pro.fr", "telephone.city", "trouver-ouvert.fr",
    "justacote.com", "yelp.fr", "yelp.com", "118712.fr", "kompass.com",
    "starofservice.com", "leboncoin.fr", "lacentrale.fr", "pros.lacentrale.fr",
    "centralepneus.fr", "montage.centralepneus.fr", "grip500.fr",
    "zecarrossery.fr", "meilleurs-garagistes.fr", "applivoiture.fr",
    "petitesaffiches.fr", "annuaire.petitesaffiches.fr", "hoodspot.fr",
    "villesetshopping.fr", "allomarie.fr", "wikipedia.org", "fr.wikipedia.org",
    "en.wikipedia.org", "google.com", "maps.google.com", "tripadvisor.fr",
    "apple.com", "apps.apple.com", "rv-elec.fr", "autoprimo.com",
    "vite-un-depanneur.fr", "selfgarage.org", "netguide.com", "plare.fr",
    "guest-suite.com", "societe-france.fr", "bilansgratuits.fr",
}

# Sites de tete de reseau : une fiche la-dessus signale une enseigne affiliee,
# dont la communication est pilotee par le reseau. Ce n'est ni un annuaire
# generaliste, ni le site propre de l'entreprise.
RESEAU_HOTES = {
    "ad.fr", "boschcarservice.com", "norauto.fr", "midas.fr", "feuvert.fr",
    "roady.fr", "speedy.fr", "points.fr", "pointsfrance.fr", "euromaster.fr",
    "firststop.fr", "vulco.com", "profilplus.fr", "precisium-garage.com",
    "reseau.top-garage.fr", "garage-ad.fr", "adexpert.fr",
}

# Enseignes de reseau et concessions : elles ont un site fourni par la tete de
# reseau et ne decident pas de leur communication. Ce ne sont pas des prospects.
RESEAUX = {
    "roady", "norauto", "midas", "feu vert", "feuvert", "speedy", "point s",
    "pointss", "euromaster", "first stop", "firststop", "ad expert",
    "bosch car service", "precisium", "précisium", "top garage", "vulco",
    "profil plus", "carter cash", "carter-cash", "autobacs", "kwik fit",
    "renault", "dacia", "peugeot", "citroen", "citroën", "ds automobiles",
    "opel", "ford", "fiat", "toyota", "nissan", "volkswagen", "audi", "seat",
    "skoda", "bmw", "mini", "mercedes", "hyundai", "kia", "suzuki", "mazda",
    "honda", "volvo", "jeep", "alfa romeo", "tesla", "dacia", "mg motor",
}


# --------------------------------------------------------------------------
# utilitaires
# --------------------------------------------------------------------------

def _charger_env() -> None:
    fp = REPO_ROOT / ".env"
    if not fp.exists():
        return
    for ligne in fp.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        k, v = ligne.split("=", 1)
        k = k.strip()
        if k and k not in os.environ:
            os.environ[k] = v.strip().strip('"').strip("'")


def _cle() -> str:
    cle = os.environ.get("BRAVE_API_KEY", "").strip()
    if not cle:
        sys.exit(
            "BRAVE_API_KEY absente du .env.\n"
            "  1. Cree un compte sur api-dashboard.search.brave.com\n"
            "  2. Choisis l'offre « Free » (carte demandee pour l'identite, "
            "jamais debitee)\n"
            "  3. echo 'BRAVE_API_KEY=...' >> .env"
        )
    return cle


def _sans_accents(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt or "")
    return "".join(c for c in txt if not unicodedata.combining(c))


def _slug(txt: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _sans_accents(txt).lower()).strip("-")


def _hote(url: str) -> str:
    try:
        h = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def _est_annuaire(hote: str) -> bool:
    if hote in ANNUAIRES:
        return True
    # un sous-domaine d'annuaire reste un annuaire
    return any(hote.endswith("." + a) for a in ANNUAIRES)


def _est_reseau(nom: str, url_facebook: str = "") -> bool:
    """Le nom ne suffit pas : « Breard Automobiles » est un concessionnaire
    Opel, et cela ne se voit que dans l'URL de sa page, /OpelVitre/."""
    n = " " + _sans_accents(nom).lower() + " "
    if any(" " + r + " " in n or n.startswith(" " + r) for r in RESEAUX):
        return True
    if url_facebook:
        chemin = _sans_accents(urllib.parse.urlparse(url_facebook).path).lower()
        compact = re.sub(r"[^a-z0-9]+", "", chemin)
        for r in RESEAUX:
            rc = re.sub(r"[^a-z0-9]+", "", r)
            if len(rc) >= 4 and rc in compact:
                return True
    return False


# --------------------------------------------------------------------------
# API Brave
# --------------------------------------------------------------------------

_compteur = {"requetes": 0}


def chercher(cle: str, requete: str, nb: int = 20) -> list[dict]:
    """Retourne [{titre, url, hote, description}] ou [] en cas d'echec."""
    params = urllib.parse.urlencode({
        "q": requete, "count": nb, "country": "fr",
        "search_lang": "fr", "ui_lang": "fr-FR", "safesearch": "off",
    })
    req = urllib.request.Request(
        API + "?" + params,
        headers={"Accept": "application/json",
                 "Accept-Encoding": "identity",
                 "X-Subscription-Token": cle},
    )
    for essai in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            _compteur["requetes"] += 1
            res = (data.get("web") or {}).get("results") or []
            return [{"titre": x.get("title", ""), "url": x.get("url", ""),
                     "hote": _hote(x.get("url", "")),
                     "description": x.get("description", "")} for x in res]
        except urllib.error.HTTPError as e:
            if e.code == 429:            # quota par seconde
                time.sleep(2 + essai * 2)
                continue
            if e.code in (401, 403):
                sys.exit(f"Brave refuse la cle API ({e.code}). Verifie BRAVE_API_KEY.")
            if essai == 3:
                print(f"    ! HTTP {e.code} sur « {requete} »")
                return []
            time.sleep(1 + essai)
        except Exception as e:
            if essai == 3:
                print(f"    ! {type(e).__name__} sur « {requete} »")
                return []
            time.sleep(1 + essai)
    return []


# --------------------------------------------------------------------------
# base
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS prospects (
    cle            TEXT PRIMARY KEY,   -- slug nom + commune
    nom            TEXT NOT NULL,
    commune        TEXT NOT NULL,
    departement    TEXT,
    code_postal    TEXT,
    adresse        TEXT,
    telephone      TEXT,
    note           REAL,
    avis           INTEGER,
    facebook       TEXT,
    site_web       TEXT,               -- domaine propre, vide si aucun
    site_statut    TEXT NOT NULL,      -- aucun | propre | reseau | inconnu
    metier         TEXT NOT NULL DEFAULT 'garage',
    sources        TEXT,               -- JSON : d'ou vient chaque fait
    recense_at     TEXT,
    resolu_at      TEXT,
    traite_at      TEXT,               -- date de generation du site
    site_genere    TEXT,
    note_interne   TEXT
);
CREATE INDEX IF NOT EXISTS idx_p_statut  ON prospects(site_statut);
CREATE INDEX IF NOT EXISTS idx_p_commune ON prospects(commune);
CREATE INDEX IF NOT EXISTS idx_p_traite  ON prospects(traite_at);

CREATE TABLE IF NOT EXISTS communes_faites (
    commune    TEXT PRIMARY KEY,
    metier     TEXT NOT NULL DEFAULT 'garage',
    trouves    INTEGER,
    prospects  INTEGER,
    fait_at    TEXT NOT NULL
);
"""


def ouvrir() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    return conn


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def enregistrer(conn, **champs) -> None:
    """Insere ou met a jour, sans jamais ecraser une valeur par du vide."""
    cle = champs["cle"]
    ancien = conn.execute("SELECT * FROM prospects WHERE cle=?", (cle,)).fetchone()
    colonnes = [r[1] for r in conn.execute("PRAGMA table_info(prospects)")]

    if ancien is None:
        champs.setdefault("site_statut", "inconnu")
        cols = [c for c in colonnes if c in champs]
        conn.execute(
            f"INSERT INTO prospects ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [champs[c] for c in cols],
        )
    else:
        courant = dict(zip(colonnes, ancien))
        maj = {c: v for c, v in champs.items()
               if c in colonnes and c != "cle"
               and v not in (None, "")            # jamais ecraser par du vide
               and v != courant.get(c)}
        if maj:
            conn.execute(
                f"UPDATE prospects SET {','.join(c + '=?' for c in maj)} WHERE cle=?",
                [*maj.values(), cle],
            )
    conn.commit()


# --------------------------------------------------------------------------
# les trois temps de la methode
# --------------------------------------------------------------------------

def recenser(cle_api: str, commune: str) -> list[dict]:
    """Temps 1 : les commerces de la commune, via leurs pages Facebook."""
    res = chercher(cle_api, f"site:facebook.com garage automobile mécanique {commune}")
    time.sleep(DELAI)

    vus, sortie = set(), []
    for r in res:
        if "facebook.com" not in r["hote"]:
            continue
        # « Garage Milet | Vitré | Facebook » -> « Garage Milet »
        nom = re.split(r"\s*\|\s*", r["titre"])[0].strip()
        nom = re.sub(r"\s*[-–]\s*Facebook\s*$", "", nom, flags=re.I).strip()
        if not nom or len(nom) < 3:
            continue
        s = _slug(nom)
        if s in vus:
            continue
        vus.add(s)
        sortie.append({"nom": nom, "facebook": r["url"], "reseau": _est_reseau(nom, r["url"])})
    return sortie


def resoudre(cle_api: str, nom: str, commune: str) -> dict:
    """Temps 2 : cette entreprise a-t-elle son propre site ?"""
    res = chercher(cle_api, f'"{nom}" {commune}')
    time.sleep(DELAI)
    if not res:
        return {"site_statut": "inconnu", "site_web": "", "sources": []}

    # Le rapprochement doit se faire par SOUS-CHAINE, pas par intersection de
    # mots : « Garage de Thorigne » a pour domaine garagedethorigne.fr, ou les
    # mots sont colles. Une comparaison par jetons le declarait sans site —
    # l'erreur la plus couteuse possible, puisqu'on appellerait un garagiste
    # pour lui annoncer qu'il n'a pas de site alors qu'il en a un.
    jetons = [m for m in re.split(r"[^a-z0-9]+", _sans_accents(nom).lower())
              if len(m) >= 4]
    propres, annuaires, reseaux = [], [], []
    for r in res:
        h = r["hote"]
        if not h:
            continue
        if h in RESEAU_HOTES or any(h.endswith("." + x) for x in RESEAU_HOTES):
            reseaux.append(r["url"])
            continue
        if _est_annuaire(h):
            annuaires.append(r["url"])
            continue
        base = re.sub(r"\.(fr|com|net|eu|bzh|paris|pro|io|co)$", "", h)
        compact = re.sub(r"[^a-z0-9]+", "", base)
        if any(j in compact for j in jetons):
            propres.append(h)

    if propres:
        return {"site_statut": "propre", "site_web": propres[0],
                "sources": (annuaires + reseaux)[:6] + propres[:2]}
    if reseaux:
        return {"site_statut": "reseau", "site_web": "",
                "sources": (reseaux + annuaires)[:8]}
    if annuaires:
        return {"site_statut": "aucun", "site_web": "", "sources": annuaires[:8]}
    return {"site_statut": "inconnu", "site_web": "", "sources": []}


def traiter_commune(conn, cle_api: str, commune: str, metier: str = "garage") -> tuple[int, int]:
    print(f"\n=== {commune} ===")
    trouves = recenser(cle_api, commune)
    if not trouves:
        print("  aucun commerce recense")
        conn.execute(
            "INSERT OR REPLACE INTO communes_faites VALUES (?,?,?,?,?)",
            (commune, metier, 0, 0, maintenant()))
        conn.commit()
        return 0, 0

    nb_prospects = 0
    for t in trouves:
        cle = f"{_slug(t['nom'])}--{_slug(commune)}"
        if t["reseau"]:
            print(f"  {t['nom'][:38]:38} reseau, ignore")
            enregistrer(conn, cle=cle, nom=t["nom"], commune=commune,
                        metier=metier, facebook=t["facebook"],
                        site_statut="reseau", recense_at=maintenant(),
                        sources=json.dumps([t["facebook"]]))
            continue

        r = resoudre(cle_api, t["nom"], commune)
        marque = {"aucun": "PROSPECT", "propre": "a deja un site",
                  "reseau": "affilie a un reseau",
                  "inconnu": "INDETERMINE — a verifier a la main"}[r["site_statut"]]
        detail = f" ({r['site_web']})" if r["site_web"] else ""
        print(f"  {t['nom'][:38]:38} {marque}{detail}")
        if r["site_statut"] == "aucun":
            nb_prospects += 1

        enregistrer(conn, cle=cle, nom=t["nom"], commune=commune, metier=metier,
                    facebook=t["facebook"], site_web=r["site_web"],
                    site_statut=r["site_statut"], recense_at=maintenant(),
                    resolu_at=maintenant(),
                    sources=json.dumps([t["facebook"], *r["sources"]]))

    conn.execute("INSERT OR REPLACE INTO communes_faites VALUES (?,?,?,?,?)",
                 (commune, metier, len(trouves), nb_prospects, maintenant()))
    conn.commit()
    print(f"  -> {len(trouves)} recenses, {nb_prospects} sans site")
    return len(trouves), nb_prospects


# --------------------------------------------------------------------------
# lectures
# --------------------------------------------------------------------------

def lister(conn, chemin_csv: str | None, tous: bool) -> None:
    cond = "" if tous else " AND traite_at IS NULL"
    lignes = conn.execute(
        "SELECT nom, commune, telephone, note, avis, facebook, traite_at, cle "
        f"FROM prospects WHERE site_statut='aucun'{cond} "
        "ORDER BY COALESCE(avis,0) DESC, commune, nom").fetchall()
    print(f"\n{len(lignes)} prospect(s) sans site"
          f"{'' if tous else ' et non traites'}\n")
    for nom, commune, tel, note, avis, fb, traite, _ in lignes[:50]:
        etoiles = f"{note:.1f}*{avis}" if note else "—"
        print(f"  {nom[:32]:32} {(commune or '')[:16]:16} {(tel or '—'):16} "
              f"{etoiles:9} {'traite' if traite else ''}")
    if len(lignes) > 50:
        print(f"  ... et {len(lignes) - 50} autres")
    if chemin_csv:
        with open(chemin_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["nom", "commune", "telephone", "note", "avis",
                        "facebook", "traite_at", "cle"])
            w.writerows(lignes)
        print(f"\n-> {len(lignes)} lignes dans {chemin_csv}")


def stats(conn) -> None:
    total = conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0]
    print(f"\n{total} entreprises en base\n")
    for statut, n in conn.execute(
            "SELECT site_statut, COUNT(*) FROM prospects GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {statut:10} : {n}")
    communes = conn.execute("SELECT COUNT(*) FROM communes_faites").fetchone()[0]
    reste = [c for c in COMMUNES if not conn.execute(
        "SELECT 1 FROM communes_faites WHERE commune=?", (c,)).fetchone()]
    print(f"\n{communes} commune(s) traitee(s), {len(reste)} restantes sur {len(COMMUNES)}")
    if communes:
        print("\nTaux de « sans site » par commune :")
        for c, t, p in conn.execute(
                "SELECT commune, trouves, prospects FROM communes_faites "
                "ORDER BY fait_at DESC LIMIT 12"):
            taux = f"{100 * p / t:.0f}%" if t else "—"
            print(f"  {c[:22]:22} {p}/{t}  {taux}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--commune", action="append", help="commune a traiter (repetable)")
    p.add_argument("--tournee", type=int, metavar="N",
                   help="traiter les N prochaines communes non faites de la liste")
    p.add_argument("--metier", default="garage")
    p.add_argument("--prospects", action="store_true", help="lister les prospects")
    p.add_argument("--tous", action="store_true", help="avec --prospects : inclure les traites")
    p.add_argument("--csv", default=None)
    p.add_argument("--stats", action="store_true")
    args = p.parse_args()

    _charger_env()
    conn = ouvrir()

    if args.stats:
        stats(conn); return
    if args.prospects:
        lister(conn, args.csv, args.tous); return

    communes = list(args.commune or [])
    if args.tournee:
        faites = {r[0] for r in conn.execute("SELECT commune FROM communes_faites")}
        communes += [c for c in COMMUNES if c not in faites][:args.tournee]
    if not communes:
        p.error("donne --commune, --tournee, --prospects ou --stats")

    cle_api = _cle()
    print(f"{len(communes)} commune(s) : {', '.join(communes)}")
    for c in communes:
        traiter_commune(conn, cle_api, c, args.metier)

    cout = _compteur["requetes"] * COUT_REQUETE
    print(f"\n{_compteur['requetes']} requetes Brave, soit {cout:.3f} $ "
          f"(5 $ de credit offert chaque mois)")
    stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
