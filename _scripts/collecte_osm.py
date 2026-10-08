#!/usr/bin/env python3
"""Collecte en masse des garages francais depuis OpenStreetMap (Overpass).

Pourquoi OpenStreetMap plutot qu'un scraping d'annuaire :
  - c'est libre de droits (ODbL), gratuit, sans cle, et prevu pour ca ;
  - PagesJaunes, Vroomly et consorts l'interdisent dans leurs conditions et
    repondent par des CAPTCHA ;
  - OSM porte directement les etiquettes `phone`, `email` et `website`, donc
    la question « a-t-il un site ? » se resout sans requete supplementaire.

Ce qu'il faut savoir avant de se faire des idees sur les adresses mail :
  un garage sans site web n'a presque jamais d'adresse publique. L'email
  n'existe en pratique que chez ceux qui ont deja un site — c'est-a-dire
  precisement ceux qui ne sont pas des prospects. Le telephone, lui, est
  largement renseigne. Ce script mesure les deux et l'affiche, plutot que
  de promettre ce qui n'existe pas.

Chaine complete :
  1. collecte_osm.py     masse + telephone + presence de site      (gratuit)
  2. places.py           telephone manquant, note et avis Google   (payant)
  3. recherche_web.py    verification « a-t-il vraiment un site »  (Brave)
  4. pipeline_pro.py     generation des sites de demo

Usage :
    python3 _scripts/collecte_osm.py --dept 35
    python3 _scripts/collecte_osm.py --tous            # les 101 departements
    python3 _scripts/collecte_osm.py --region bretagne
    python3 _scripts/collecte_osm.py --stats
    python3 _scripts/collecte_osm.py --prospects --csv garages.csv
"""
from __future__ import annotations

import argparse
import csv
import json
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

# Serveurs Overpass publics. Ce sont des ressources benevoles et partagees :
# une requete par departement, une pause entre chaque, et on bascule de
# serveur plutot que de s'acharner sur celui qui sature.
# ATTENTION : ne mettre ici que des instances qui portent les donnees
# MONDIALES. overpass.osm.ch a ete retire : c'est une instance suisse, qui
# repond « 200 OK, zero resultat » sur la France. Elle a fait passer 95
# departements pour vides sans le moindre message d'erreur.
# Toute instance ajoutee ici doit passer le test de couverture ci-dessous.
SERVEURS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Requete minuscule sur un endroit ou l'on SAIT qu'il y a des garages : sert a
# verifier qu'un serveur couvre bien la France avant de lui faire confiance.
SONDE = ('[out:json][timeout:30];nwr["shop"="car_repair"]'
         '(48.09,-1.72,48.14,-1.63);out count;')
PAUSE = 6          # secondes entre deux departements — rester poli
TIMEOUT_REQ = 240

DEPARTEMENTS = [f"{n:02d}" for n in range(1, 20)] + ["2A", "2B"] + \
               [f"{n:02d}" for n in range(21, 96)] + \
               ["971", "972", "973", "974", "976"]

REGIONS = {
    "bretagne": ["22", "29", "35", "56"],
    "pays-de-la-loire": ["44", "49", "53", "72", "85"],
    "normandie": ["14", "27", "50", "61", "76"],
    "nouvelle-aquitaine": ["16", "17", "19", "23", "24", "33", "40", "47",
                            "64", "79", "86", "87"],
    "occitanie": ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65",
                   "66", "81", "82"],
    "auvergne-rhone-alpes": ["01", "03", "07", "15", "26", "38", "42", "43",
                              "63", "69", "73", "74"],
    "grand-est": ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"],
    "hauts-de-france": ["02", "59", "60", "62", "80"],
    "bourgogne-franche-comte": ["21", "25", "39", "58", "70", "71", "89", "90"],
    "centre-val-de-loire": ["18", "28", "36", "37", "41", "45"],
    "provence-alpes-cote-d-azur": ["04", "05", "06", "13", "83", "84"],
    "ile-de-france": ["75", "77", "78", "91", "92", "93", "94", "95"],
    "corse": ["2A", "2B"],
}

# Enseignes de reseau et concessions : leur communication est pilotee par la
# tete de reseau, ce ne sont pas des prospects.
RESEAUX_GARAGE = {
    "roady", "norauto", "midas", "feu vert", "feuvert", "speedy", "point s",
    "euromaster", "first stop", "ad expert", "garage ad", "bosch car service",
    "precisium", "top garage", "vulco", "profil plus", "carter cash",
    "autobacs", "kwik fit", "mister auto", "dekra", "securitest", "autovision",
    "autosur", "renault", "dacia", "peugeot", "citroen", "ds automobiles",
    "opel", "ford", "fiat", "toyota", "nissan", "volkswagen", "audi", "seat",
    "skoda", "bmw", "mini", "mercedes", "hyundai", "kia", "suzuki", "mazda",
    "honda", "volvo", "jeep", "alfa romeo", "tesla", "mg motor", "porsche",
    "land rover", "jaguar", "subaru", "mitsubishi", "cupra",
}

# Cote nautique, deux familles a ecarter. Les enseignes d'accastillage, dont
# la communication est pilotee par la centrale. Et les chantiers de
# construction en serie : ce sont des industriels, pas des artisans qu'on
# demarche. La liste est empirique et se completera en voyant les donnees,
# comme il a fallu le faire pour le pare-brise cote garage.
RESEAUX_NAUTIQUE = {
    # accastillage et distribution
    "accastillage diffusion", "uship", "u-ship", "bigship", "big ship",
    "comptoir de la mer", "nautic store", "nautistore", "marine store",
    "sea design", "accastillage", "coopérative maritime", "cooperative maritime",
    "decathlon", "tribord",
    # constructeurs en serie
    "beneteau", "bénéteau", "jeanneau", "dufour", "lagoon", "fountaine pajot",
    "amel", "alubat", "garcia", "outremer", "catana", "nautitech", "zodiac",
    "bombard", "sunseeker", "princess", "azimut", "rodman", "quicksilver",
    "brunswick", "yamaha", "suzuki marine", "mercury", "volvo penta",
    "groupe beneteau", "chantiers de l'atlantique", "naval group", "piriou",
}

# Cote menuiserie, trois familles a ecarter. Les fabricants-installateurs de
# fenetres en reseau, dont la communication est pilotee par la franchise. Les
# cuisinistes en enseigne. Et les negoces / GSB, qui remontent parfois sous
# craft=carpenter quand ils ont un atelier de decoupe. Liste empirique, a
# completer en lisant les donnees.
RESEAUX_MENUISIER = {
    # fenetres, portes, fermetures en reseau
    "lapeyre", "k par k", "kpark", "tryba", "franciaflex", "art et fenetres",
    "art & fenetres", "grosfillex", "monsieur store", "france fermetures",
    "bel'm", "belm", "oknoplast", "les ouvertures", "solabaie", "internorm",
    "mistermenuiserie", "mister menuiserie", "akena", "komilfo",
    "la boutique du menuisier", "boutique du menuisier",
    "kline", "k line", "bieber", "zilten", "sybaie", "proferm",
    "repar'stores", "fenetrea", "lorenove", "sofrapa", "technal", "schuco",
    # cuisinistes et agencement en enseigne
    "schmidt", "cuisinella", "mobalpa", "ixina", "arthur bonnet", "socooc",
    "socoo'c", "cuisine plus", "cuisines references", "aviva", "perene",
    "nolte", "hygena", "ikea", "conforama",
    # negoce et grandes surfaces de bricolage
    "point p", "leroy merlin", "castorama", "brico depot", "mr bricolage",
    "mr.bricolage", "bricomarche", "weldom", "gedimat", "bigmat", "big mat",
    "tout faire", "dispano", "panofrance", "bois et materiaux", "chausson",
    "samse", "vm materiaux", "doras",
}

# Un metier = une liste de filtres Overpass et une liste d'enseignes a
# ecarter. Tout le reste de la collecte est commun.
#
# Cote nautique, waterway=boatyard est le tag central : le wiki le definit
# comme « un lieu ou l'on construit, repare et entrepose des bateaux hors de
# l'eau », ce qui est exactement la cible. craft=sailmaker ramene les
# voileries, qui reparent les voiles et le greement -- la demande de depart.
# industrial=shipyard ramene aussi de gros chantiers : ils seront ecartes par
# la liste d'enseignes plutot que par le filtre, parce que la frontiere entre
# un chantier naval de vingt personnes et un industriel ne tient pas dans un
# tag.
METIERS_OSM = {
    "garage": {
        "filtres": ['nwr["shop"="car_repair"](area.d);',
                    'nwr["shop"="tyres"](area.d);',
                    'nwr["craft"="car_repair"](area.d);'],
        "reseaux": RESEAUX_GARAGE,
    },
    "nautique": {
        "filtres": ['nwr["waterway"="boatyard"](area.d);',
                    'nwr["craft"="boatbuilder"](area.d);',
                    'nwr["craft"="sailmaker"](area.d);',
                    'nwr["shop"="boat"](area.d);',
                    'nwr["industrial"="shipyard"](area.d);',
                    'nwr["service:boat:repair"="yes"](area.d);',
                    'nwr["boat:repair"="yes"](area.d);'],
        "reseaux": RESEAUX_NAUTIQUE,
    },
    "menuisier": {
        # craft=carpenter couvre menuisiers et charpentiers (le wiki ne les
        # separe pas), craft=joiner la menuiserie d'agencement,
        # craft=cabinet_maker les ebenistes, craft=window_construction les
        # poseurs de fenetres. shop=doors ramene quelques ateliers-showrooms.
        "filtres": ['nwr["craft"="carpenter"](area.d);',
                    'nwr["craft"="joiner"](area.d);',
                    'nwr["craft"="cabinet_maker"](area.d);',
                    'nwr["craft"="window_construction"](area.d);',
                    'nwr["craft"="parquet_layer"](area.d);',
                    'nwr["shop"="doors"](area.d);'],
        "reseaux": RESEAUX_MENUISIER,
    },
}

# Le metier courant : fixe une fois pour toutes par --metier, lu partout
# ailleurs. Une variable de module plutot qu'un parametre traine de fonction
# en fonction.
METIER = "garage"

REQUETE = """[out:json][timeout:{t}];
area["boundary"="administrative"]["admin_level"="6"]["ref:INSEE"="{dept}"]->.d;
(
{filtres}
);
out center tags;"""


# --------------------------------------------------------------------------
# utilitaires
# --------------------------------------------------------------------------

def _sans_accents(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c))


def _slug(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _sans_accents(t).lower()).strip("-")


def _est_reseau(*champs: str) -> bool:
    """Vrai si l'un des champs porte une enseigne du metier courant.

    Comparaison bornee par des espaces, et non par sous-chaine : « ad » ne
    doit pas se declencher au milieu d'un mot, et « renault » ne doit pas
    attraper un patronyme qui le contient.
    """
    texte = " " + _sans_accents(" ".join(c or "" for c in champs)).lower() + " "
    return any(" " + r + " " in texte
               for r in METIERS_OSM[METIER]["reseaux"])


def _tel_fr(brut: str) -> str:
    """Normalise en 0X XX XX XX XX ; rend '' si ce n'est pas un numero francais."""
    if not brut:
        return ""
    brut = brut.split(";")[0].strip()
    chiffres = re.sub(r"[^\d+]", "", brut)
    if chiffres.startswith("+33"):
        chiffres = "0" + chiffres[3:]
    elif chiffres.startswith("0033"):
        chiffres = "0" + chiffres[4:]
    chiffres = re.sub(r"\D", "", chiffres)
    if len(chiffres) != 10 or not chiffres.startswith("0"):
        return ""
    return " ".join(chiffres[i:i + 2] for i in range(0, 10, 2))


def _email(brut: str) -> str:
    if not brut:
        return ""
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", brut)
    return m.group(0).lower() if m else ""


def _hote(url: str) -> str:
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        h = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


# --------------------------------------------------------------------------
# Overpass
# --------------------------------------------------------------------------

_etat = {"requetes": 0, "serveur": 0}


def verifier_serveurs() -> None:
    """Ecarte les serveurs qui ne couvrent pas la France.

    La distinction qui compte, et que j'avais ratee deux fois :

      repond AVEC des donnees  -> le serveur couvre la France, on le garde
      repond 200 mais a ZERO   -> couverture regionale, on l'ECARTE
      ne repond pas du tout    -> surcharge passagere, on le GARDE

    Un serveur muet n'est pas un serveur inutile : overpass-api.de a rate la
    sonde tout en repondant ensuite sur six departements d'affilee. On
    n'arrete donc la collecte que si TOUS les serveurs ont repondu ET que
    tous ont repondu vide.
    """
    global SERVEURS
    couvrent, sans_donnees, muets = [], [], []
    for url in SERVEURS:
        hote = urllib.parse.urlparse(url).netloc
        total = None
        for essai in (1, 2):          # la sonde elle-meme peut tomber sur un 504
            try:
                req = urllib.request.Request(
                    url, data=urllib.parse.urlencode({"data": SONDE}).encode(),
                    headers={"User-Agent": "prospection-garages/1.0"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.load(r)
                total = int((data.get("elements") or [{}])[0]
                            .get("tags", {}).get("total", 0))
                break
            except Exception:
                if essai == 2:
                    break
                time.sleep(5)
        if total is None:
            print(f"  {hote} : muet pour l'instant, garde quand meme")
            muets.append(url)
        elif total > 0:
            print(f"  {hote} : couverture confirmee ({total} garages sur la sonde)")
            couvrent.append(url)
        else:
            print(f"  {hote} : ECARTE — repond sans erreur mais ne couvre pas la France")
            sans_donnees.append(url)

    SERVEURS = couvrent + muets
    if not SERVEURS:
        sys.exit("\nTous les serveurs repondent sans donnees sur la France. "
                 "Verifie la liste SERVEURS en haut du fichier.")
    if not couvrent:
        print("  (aucune sonde n'a abouti — on tente quand meme, les requetes "
              "par departement ont leurs propres reessais)")


def interroger(dept: str) -> list[dict] | None:
    """Liste des elements, [] si le departement est reellement vide,
    None si aucun serveur n'a pu repondre.

    Une reponse vide n'est PAS prise pour argent comptant : on reverifie sur
    un autre serveur. Un departement francais sans aucun garage n'existe pas,
    donc un zero signale presque toujours un probleme de serveur.
    """
    _etat["serveur"] = 0          # toujours repartir du serveur principal
    vides = 0
    filtres = "\n".join("  " + f for f in METIERS_OSM[METIER]["filtres"])
    corps = REQUETE.format(t=TIMEOUT_REQ, dept=dept,
                           filtres=filtres).encode("utf-8")
    for essai in range(len(SERVEURS) * 2):
        url = SERVEURS[_etat["serveur"] % len(SERVEURS)]
        req = urllib.request.Request(
            url, data=urllib.parse.urlencode({"data": corps.decode()}).encode(),
            headers={"User-Agent": "prospection-garages/1.0 (contact via github.com/francoislang)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_REQ + 30) as r:
                data = json.load(r)
            _etat["requetes"] += 1
            elements = data.get("elements", [])
            if elements:
                return elements
            vides += 1
            hote = urllib.parse.urlparse(url).netloc
            if vides >= len(SERVEURS):
                print(f"    tous les serveurs renvoient 0 : departement "
                      f"reellement vide, ou probleme general")
                return []
            print(f"    reponse vide sur {hote}, verification sur un autre serveur")
            _etat["serveur"] += 1
            time.sleep(3)
        except urllib.error.HTTPError as e:
            # 429 : trop de requetes. 504 : le serveur a sature. On change.
            print(f"    ! HTTP {e.code} sur {urllib.parse.urlparse(url).netloc}")
            _etat["serveur"] += 1
            time.sleep(10 + essai * 5)
        except Exception as e:
            print(f"    ! {type(e).__name__} sur {urllib.parse.urlparse(url).netloc}")
            _etat["serveur"] += 1
            time.sleep(8 + essai * 4)
    return None


def extraire(el: dict, dept: str) -> dict | None:
    t = el.get("tags") or {}
    nom = (t.get("name") or t.get("operator") or t.get("brand") or "").strip()
    if not nom:
        return None          # sans nom, impossible d'appeler qui que ce soit

    tel = _tel_fr(t.get("phone") or t.get("contact:phone") or
                  t.get("mobile") or t.get("contact:mobile") or "")
    mail = _email(t.get("email") or t.get("contact:email") or "")
    site = _hote(t.get("website") or t.get("contact:website") or
                 t.get("url") or "")
    if site in ("facebook.com", "m.facebook.com", "instagram.com"):
        site = ""            # une page Facebook n'est pas un site

    adresse = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x)
    commune = t.get("addr:city") or ""
    reseau = _est_reseau(nom, t.get("brand"), t.get("operator"))

    return {
        "cle": f"osm-{el.get('type','n')}{el.get('id')}",
        "nom": nom,
        "commune": commune,
        "departement": dept,
        "code_postal": t.get("addr:postcode") or "",
        "adresse": adresse,
        "telephone": tel,
        "email": mail,
        "site_web": site,
        "site_statut": "reseau" if reseau else ("propre" if site else "aucun"),
        "horaires": t.get("opening_hours") or "",
        "latitude": el.get("lat") or (el.get("center") or {}).get("lat"),
        "longitude": el.get("lon") or (el.get("center") or {}).get("lon"),
        "metier": METIER,
        "sources": json.dumps([f"https://www.openstreetmap.org/"
                               f"{el.get('type','node')}/{el.get('id')}"]),
        "recense_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "resolu_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# --------------------------------------------------------------------------
# base
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS prospects (
    cle TEXT PRIMARY KEY, nom TEXT NOT NULL, commune TEXT, departement TEXT,
    code_postal TEXT, adresse TEXT, telephone TEXT, note REAL, avis INTEGER,
    facebook TEXT, site_web TEXT, site_statut TEXT NOT NULL,
    metier TEXT NOT NULL DEFAULT 'garage', sources TEXT,
    recense_at TEXT, resolu_at TEXT, traite_at TEXT, site_genere TEXT,
    note_interne TEXT
);
CREATE INDEX IF NOT EXISTS idx_p_statut  ON prospects(site_statut);
CREATE INDEX IF NOT EXISTS idx_p_dept    ON prospects(departement);
CREATE INDEX IF NOT EXISTS idx_p_traite  ON prospects(traite_at);

CREATE TABLE IF NOT EXISTS depts_faits (
    metier TEXT NOT NULL DEFAULT 'garage', departement TEXT, trouves INTEGER,
    avec_tel INTEGER, avec_mail INTEGER, prospects INTEGER,
    fait_at TEXT NOT NULL, PRIMARY KEY (metier, departement)
);
"""
COLONNES_SUP = {"email": "TEXT", "horaires": "TEXT",
                "latitude": "REAL", "longitude": "REAL", "osm": "TEXT"}


def ouvrir() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    deja = {r[1] for r in conn.execute("PRAGMA table_info(prospects)")}
    for c, t in COLONNES_SUP.items():
        if c not in deja:
            conn.execute(f"ALTER TABLE prospects ADD COLUMN {c} {t}")
    conn.commit()
    return conn


def enregistrer(conn, champs: dict) -> None:
    """Insere ou complete, sans jamais ecraser une valeur connue par du vide."""
    colonnes = {r[1] for r in conn.execute("PRAGMA table_info(prospects)")}
    champs = {k: v for k, v in champs.items() if k in colonnes}
    cle = champs["cle"]
    ancien = conn.execute("SELECT * FROM prospects WHERE cle=?", (cle,)).fetchone()
    if ancien is None:
        cols = list(champs)
        conn.execute(f"INSERT INTO prospects ({','.join(cols)}) "
                     f"VALUES ({','.join('?' * len(cols))})",
                     [champs[c] for c in cols])
        return
    ordre = [r[1] for r in conn.execute("PRAGMA table_info(prospects)")]
    courant = dict(zip(ordre, ancien))
    maj = {c: v for c, v in champs.items()
           if c != "cle" and v not in (None, "") and v != courant.get(c)}
    if maj:
        conn.execute(f"UPDATE prospects SET {','.join(c + '=?' for c in maj)} "
                     "WHERE cle=?", [*maj.values(), cle])


def traiter_dept(conn, dept: str) -> tuple[int, int, int, int]:
    print(f"\n--- departement {dept} ---")
    elements = interroger(dept)
    if elements is None:
        print("    echec sur tous les serveurs, departement ignore")
        return 0, 0, 0, 0

    lignes = [x for x in (extraire(e, dept) for e in elements) if x]
    if not lignes:
        # On n'ecrit PAS dans depts_faits : sinon --reprendre le sauterait a
        # jamais, et un incident serveur devient une perte definitive.
        print("    0 etablissement — departement NON marque comme fait, "
              "il sera rejoue au prochain --reprendre")
        return 0, 0, 0, 0
    tel = sum(1 for x in lignes if x["telephone"])
    mail = sum(1 for x in lignes if x["email"])
    prosp = sum(1 for x in lignes if x["site_statut"] == "aucun" and x["telephone"])

    for x in lignes:
        enregistrer(conn, x)
    conn.execute("INSERT OR REPLACE INTO depts_faits VALUES (?,?,?,?,?,?,?)",
                 (METIER, dept, len(lignes), tel, mail, prosp,
                  datetime.now(timezone.utc).isoformat(timespec="seconds")))
    conn.commit()
    pc = lambda n: f"{100 * n / len(lignes):.0f}%" if lignes else "—"
    print(f"    {len(lignes)} etablissements | telephone {tel} ({pc(tel)}) "
          f"| email {mail} ({pc(mail)}) | prospects joignables sans site {prosp}")
    return len(lignes), tel, mail, prosp


# --------------------------------------------------------------------------
# lectures
# --------------------------------------------------------------------------

def prospects(conn, chemin_csv, mini_tel, tous) -> None:
    cond = "" if tous else " AND traite_at IS NULL"
    where_tel = "AND COALESCE(telephone,'')<>''" if mini_tel else \
                "AND (COALESCE(telephone,'')<>'' OR COALESCE(email,'')<>'')"
    lignes = conn.execute(
        "SELECT nom, commune, code_postal, departement, telephone, "
        "COALESCE(email,''), adresse, COALESCE(horaires,''), cle "
        f"FROM prospects WHERE metier=? AND site_statut='aucun' "
        f"{where_tel}{cond} ORDER BY departement, commune, nom",
        (METIER,)).fetchall()
    print(f"\n{len(lignes)} prospect(s) « {METIER} » sans site et joignables\n")
    for nom, com, cp, dep, tel, mail, adr, _h, _c in lignes[:40]:
        print(f"  {nom[:34]:34} {(cp or ''):6} {(com or '')[:20]:20} "
              f"{(tel or '—'):16} {mail[:28]}")
    if len(lignes) > 40:
        print(f"  ... et {len(lignes) - 40} autres")
    if chemin_csv:
        with open(chemin_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["nom", "commune", "code_postal", "departement",
                        "telephone", "email", "adresse", "horaires", "cle"])
            w.writerows(lignes)
        print(f"\n-> {len(lignes)} lignes dans {chemin_csv}")


def stats(conn) -> None:
    """Un tableau par metier : les deux marches partagent la base."""
    lignes = conn.execute(
        "SELECT metier, COUNT(*) FROM prospects GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    if not lignes:
        print("\nBase vide. Lance d'abord --dept 35 ou --tous.")
        return
    for metier, tot in lignes:
        q = lambda s: conn.execute(s, (metier,)).fetchone()[0]
        tel = q("SELECT COUNT(*) FROM prospects WHERE metier=? "
                "AND COALESCE(telephone,'')<>''")
        mail = q("SELECT COUNT(*) FROM prospects WHERE metier=? "
                 "AND COALESCE(email,'')<>''")
        joignable = q("SELECT COUNT(*) FROM prospects WHERE metier=? AND "
                      "(COALESCE(telephone,'')<>'' OR COALESCE(email,'')<>'')")
        print(f"\n=== {metier} — {tot} etablissements ===")
        print(f"  avec telephone      : {tel}  ({100*tel/tot:.0f}%)")
        print(f"  avec email          : {mail}  ({100*mail/tot:.0f}%)")
        print(f"  joignables (l'un ou l'autre) : {joignable}  "
              f"({100*joignable/tot:.0f}%)")
        for s, n in conn.execute(
                "SELECT site_statut, COUNT(*) FROM prospects WHERE metier=? "
                "GROUP BY 1 ORDER BY 2 DESC", (metier,)):
            print(f"    {s:8} : {n}")
        pr = q("SELECT COUNT(*) FROM prospects WHERE metier=? "
               "AND site_statut='aucun' AND COALESCE(telephone,'')<>'' "
               "AND traite_at IS NULL")
        faits = conn.execute("SELECT COUNT(*) FROM depts_faits WHERE metier=?",
                             (metier,)).fetchone()[0]
        print(f"  EXPLOITABLES (sans site, joignables, non traites) : {pr}")
        print(f"  {faits} departement(s) collecte(s) sur {len(DEPARTEMENTS)}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--metier", default="garage", choices=sorted(METIERS_OSM),
                   help="marche a collecter. garage : reparation automobile. "
                        "nautique : chantiers, voileries et reparateurs de "
                        "bateaux. menuisier : menuisiers, ebenistes, poseurs de "
                        "fenetres. Tous cohabitent dans la meme base, "
                        "separes par la colonne metier.")
    p.add_argument("--dept", action="append", help="code departement (repetable)")
    p.add_argument("--region", action="append",
                   help="nom de region : " + ", ".join(sorted(REGIONS)))
    p.add_argument("--tous", action="store_true", help="les 101 departements")
    p.add_argument("--reprendre", action="store_true",
                   help="avec --tous : sauter les departements deja collectes")
    p.add_argument("--prospects", action="store_true")
    p.add_argument("--tel-obligatoire", action="store_true",
                   help="avec --prospects : exiger un telephone (defaut : tel OU email)")
    p.add_argument("--tous-prospects", action="store_true",
                   help="avec --prospects : inclure ceux deja traites")
    p.add_argument("--csv", default=None)
    p.add_argument("--stats", action="store_true")
    args = p.parse_args()

    global METIER
    METIER = args.metier

    conn = ouvrir()
    if args.stats:
        stats(conn); return
    if args.prospects:
        prospects(conn, args.csv, args.tel_obligatoire, args.tous_prospects); return

    depts = list(args.dept or [])
    for r in (args.region or []):
        if r.lower() not in REGIONS:
            sys.exit(f"Region inconnue : {r}. Au choix : {', '.join(sorted(REGIONS))}")
        depts += REGIONS[r.lower()]
    if args.tous:
        depts += DEPARTEMENTS
    if not depts:
        p.error("donne --dept, --region, --tous, --prospects ou --stats")

    if args.reprendre:
        faits = {r[0] for r in conn.execute(
            "SELECT departement FROM depts_faits WHERE metier=?", (METIER,))}
        depts = [d for d in depts if d not in faits]

    depts = list(dict.fromkeys(depts))
    print("Controle de couverture des serveurs Overpass :")
    verifier_serveurs()
    print(f"\nMarche « {METIER} » — {len(depts)} departement(s) a collecter. "
          f"Une requete chacun, "
          f"{PAUSE} s de pause entre deux — Overpass est un service benevole.")
    t = m = e = pr = 0
    for i, d in enumerate(depts, 1):
        a, b, c, dd = traiter_dept(conn, d)
        t += a; m += b; e += c; pr += dd
        if i < len(depts):
            time.sleep(PAUSE)

    print(f"\n===== {t} etablissements, {m} avec telephone, {e} avec email, "
          f"{pr} prospects joignables sans site =====")
    stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
