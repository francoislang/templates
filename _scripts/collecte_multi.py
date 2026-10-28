#!/usr/bin/env python3
"""Collecte multi-metiers : tous les etablissements joignables par courriel.

Complement de collecte_osm.py (garage, menuisier, nautique, un metier par
passage). Ici, une seule requete Overpass par departement ramene d'un coup
tous les metiers du catalogue (_scripts/metiers.py), mais SEULEMENT les
etablissements qui ont une adresse de courriel ou un site web :

  - avec courriel : directement prospectables par pipeline_pro.py ;
  - avec site sans courriel : mails_sites.py ira chercher l'adresse sur le
    site (page contact, mentions legales).

Le reste (ni courriel ni site) ne sert a rien pour une prospection par
courriel et n'est pas stocke.

Les enseignes sont ecartees trois fois :
  1. l'etiquette brand:wikidata, que la communaute OSM pose sur les chaines ;
  2. le nom, compare a la liste d'enseignes du metier (metiers.py) ;
  3. apres collecte, un domaine de courriel ou de site porte par trois
     fiches ou plus (--seuil-domaine) : une franchise que les deux premiers
     filtres n'ont pas vue.

Base : la meme que le circuit pro (_data/prospection.db, table prospects),
colonne metier = cle du catalogue. Une fiche deja connue n'est jamais
reclassee : on complete seulement ses champs vides.

Usage :
    python3 _scripts/collecte_multi.py --dept 54
    python3 _scripts/collecte_multi.py --region grand-est
    python3 _scripts/collecte_multi.py --tous --reprendre
    python3 _scripts/collecte_multi.py --stats
    python3 _scripts/collecte_multi.py --reseaux        (seulement la passe 3)

ATTENTION : a lancer depuis le Mac (la VM du pont n'a pas acces a Overpass).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import collecte_osm as co          # noqa: E402  (serveurs, departements, normalisations)
import metiers                     # noqa: E402

GRAND_PUBLIC = {
    "gmail.com", "orange.fr", "wanadoo.fr", "free.fr", "sfr.fr", "neuf.fr",
    "hotmail.com", "hotmail.fr", "outlook.fr", "outlook.com", "live.fr",
    "yahoo.fr", "yahoo.com", "laposte.net", "bbox.fr", "aliceadsl.fr",
    "numericable.fr", "icloud.com", "me.com", "gmx.fr", "gmx.com", "aol.com",
    "msn.com", "club-internet.fr", "cegetel.net", "nordnet.fr", "protonmail.com",
    "proton.me",
}
# Plateformes : un site « monsalon.wixsite.com » ou une page planity ne
# trahit pas un reseau, meme partagee par cent fiches.
PLATEFORMES = {
    "wixsite.com", "wix.com", "jimdo.com", "jimdofree.com", "e-monsite.com",
    "sitew.com", "webself.net", "pagesperso-orange.fr", "business.site",
    "planity.com", "treatwell.fr", "facebook.com", "instagram.com",
    "linktr.ee", "google.com", "sites.google.com", "wordpress.com", "over-blog.com",
    "blogspot.com", "free.fr", "pagesjaunes.fr", "solocal.com", "canalblog.com",
    "gites-de-france.com", "booking.com", "airbnb.fr", "airbnb.com",
    "tripadvisor.fr", "thefork.fr", "lafourchette.com", "clevacances.com",
    "abritel.fr", "leboncoin.fr", "kalendes.com", "doctolib.fr", "my.site.com",
    "squarespace.com", "shopify.com", "myshopify.com", "weebly.com", "strikingly.com",
    "site123.me", "godaddysites.com", "mystrikingly.com", "simplesite.com",
    "webnode.fr", "jimdosite.com", "ueniweb.com", "business.page", "mairie.fr",
}

# Instances publiques qui portent les donnees mondiales. kumi.systems est
# retire (deconnexions systematiques en octobre 2026). Chacune passe la sonde
# de couverture de collecte_osm avant usage.
SERVEURS = [
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
PAUSE_REQ = 4            # entre deux requetes d'un meme departement
ATTENTES = (20, 60, 120)  # apres un echec : on laisse respirer le serveur
ECHECS_MAX = 3           # departements rates d'affilee -> on arrete

REQUETE = """[out:json][timeout:{t}];
area["boundary"="administrative"]["admin_level"="6"]["ref:INSEE"="{dept}"]->.d;
(
{filtres}
);
out center tags;"""

CONTACTS = ("email", "contact:email", "website", "contact:website")


def _filtres(cles: list[str], avec_site: bool) -> str:
    """Une ligne par (cle OSM, moyen de contact) : regex sur les valeurs."""
    tags = metiers.cles_osm()
    moyens = CONTACTS if avec_site else CONTACTS[:2]
    lignes = []
    for k in cles:
        valeurs = "|".join(sorted(tags[k]))
        for m in moyens:
            lignes.append(f'  nwr["{k}"~"^({valeurs})$"]["{m}"](area.d);')
    return "\n".join(lignes)


_rang = {"i": 0}


def _overpass(corps: str) -> list[dict] | None:
    """Les elements, ou None si aucun serveur n'a repondu.

    On garde le serveur qui marche (pas de retour systematique au premier),
    et chaque echec est suivi d'une vraie pause : les instances publiques
    rejettent (502, deconnexion) une IP qui reessaie trop vite.
    """
    for essai in range(len(co.SERVEURS) + 2):
        url = co.SERVEURS[_rang["i"] % len(co.SERVEURS)]
        hote = urllib.parse.urlparse(url).netloc
        req = urllib.request.Request(
            url, data=urllib.parse.urlencode({"data": corps}).encode(),
            headers={"User-Agent": "prospection-artisans/1.0 (contact via github.com/francoislang)"})
        try:
            with urllib.request.urlopen(req, timeout=co.TIMEOUT_REQ + 30) as r:
                data = json.load(r)
            if data.get("remark") and "runtime error" in data["remark"]:
                raise RuntimeError(data["remark"][:80])
            return data.get("elements", [])
        except urllib.error.HTTPError as e:
            raison = f"HTTP {e.code}"
        except Exception as e:
            raison = f"{type(e).__name__} {str(e)[:60]}"
        attente = ATTENTES[min(essai, len(ATTENTES) - 1)]
        print(f"    ! {raison} sur {hote}, pause {attente} s")
        _rang["i"] += 1
        time.sleep(attente)
    return None


def interroger(dept: str, avec_site: bool) -> list[dict] | None:
    """Une requete par cle OSM (shop, craft, amenity...) : la requete unique
    pour tout le catalogue depassait ce que les instances publiques
    acceptent (502)."""
    cles = sorted(metiers.cles_osm())
    tous: dict[str, dict] = {}
    for i, k in enumerate(cles):
        if i:
            time.sleep(PAUSE_REQ)
        part = _overpass(REQUETE.format(t=co.TIMEOUT_REQ, dept=dept,
                                        filtres=_filtres([k], avec_site)))
        if part is None:
            print(f"    echec sur « {k} » : departement incomplet, non marque fait")
            return None
        for e in part:
            tous[f"{e.get('type')}{e.get('id')}"] = e
    return list(tous.values())


def _est_reseau(m: metiers.Metier, t: dict, nom: str) -> bool:
    if t.get("brand:wikidata") or t.get("operator:wikidata"):
        return True
    texte = " " + metiers.normaliser(" ".join(
        x for x in (nom, t.get("brand"), t.get("operator")) if x)) + " "
    return any(" " + e + " " in texte for e in m.enseignes())


def extraire(el: dict, dept: str) -> dict | None:
    t = el.get("tags") or {}
    m = metiers.classer(t)
    if m is None:
        return None
    nom = (t.get("name") or "").strip()
    if not nom:
        return None
    mail = co._email(t.get("email") or t.get("contact:email") or "")
    site = co._hote(t.get("website") or t.get("contact:website") or t.get("url") or "")
    facebook = ""
    if site in ("facebook.com", "m.facebook.com", "fr-fr.facebook.com", "instagram.com"):
        facebook, site = t.get("website") or t.get("contact:website") or "", ""
    facebook = facebook or t.get("contact:facebook") or ""
    if not mail and not site:
        return None
    maintenant = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "cle": f"osm-{el.get('type', 'n')}{el.get('id')}",
        "nom": nom,
        "commune": t.get("addr:city") or "",
        "departement": dept,
        "code_postal": t.get("addr:postcode") or "",
        "adresse": " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x),
        "telephone": co._tel_fr(t.get("phone") or t.get("contact:phone") or
                                t.get("mobile") or t.get("contact:mobile") or ""),
        "email": mail,
        "mail_source": "osm" if mail else None,
        "site_web": site,
        "facebook": facebook,
        "site_statut": "reseau" if _est_reseau(m, t, nom) else ("propre" if site else "aucun"),
        "horaires": t.get("opening_hours") or "",
        "latitude": el.get("lat") or (el.get("center") or {}).get("lat"),
        "longitude": el.get("lon") or (el.get("center") or {}).get("lon"),
        "metier": m.cle,
        "sources": json.dumps([f"https://www.openstreetmap.org/{el.get('type', 'node')}/{el.get('id')}"]),
        "recense_at": maintenant,
        "resolu_at": maintenant,
    }


def ouvrir(chemin: Path | None = None):
    if chemin:
        co.DB_PATH = chemin
    conn = co.ouvrir()
    deja = {r[1] for r in conn.execute("PRAGMA table_info(prospects)")}
    for c, typ in {"mail_source": "TEXT", "mail_cherche_at": "TEXT"}.items():
        if c not in deja:
            conn.execute(f"ALTER TABLE prospects ADD COLUMN {c} {typ}")
    conn.commit()
    return conn


def enregistrer(conn, x: dict) -> str:
    """'nouveau', 'complete' ou 'inchange'. Ne reclasse jamais une fiche."""
    colonnes = {r[1] for r in conn.execute("PRAGMA table_info(prospects)")}
    x = {k: v for k, v in x.items() if k in colonnes}
    ancien = conn.execute("SELECT * FROM prospects WHERE cle=?", (x["cle"],)).fetchone()
    if ancien is None:
        cols = list(x)
        conn.execute(f"INSERT INTO prospects ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                     [x[c] for c in cols])
        return "nouveau"
    noms = [r[1] for r in conn.execute("PRAGMA table_info(prospects)")]
    courant = dict(zip(noms, ancien))
    maj = {c: x[c] for c in ("email", "mail_source", "site_web", "telephone", "horaires",
                             "code_postal", "commune", "facebook")
           if c in x and x[c] and not (courant.get(c) or "")}
    if maj.get("email") is None:
        maj.pop("mail_source", None)
    if not maj:
        return "inchange"
    conn.execute(f"UPDATE prospects SET {','.join(c + '=?' for c in maj)} WHERE cle=?",
                 [*maj.values(), x["cle"]])
    return "complete"


def traiter_dept(conn, dept: str, avec_site: bool) -> tuple[int, int, int]:
    print(f"\n--- departement {dept} ---")
    el = interroger(dept, avec_site)
    if el is None:
        print("    echec, departement ignore (sera rejoue avec --reprendre)")
        return 0, 0, 0
    lignes = [x for x in (extraire(e, dept) for e in el) if x]
    if not lignes:
        print("    0 etablissement exploitable — departement NON marque fait")
        return 0, 0, 0
    bilan = {"nouveau": 0, "complete": 0, "inchange": 0}
    for x in lignes:
        bilan[enregistrer(conn, x)] += 1
    mails = sum(1 for x in lignes if x["email"] and x["site_statut"] != "reseau")
    reseau = sum(1 for x in lignes if x["site_statut"] == "reseau")
    conn.execute("INSERT OR REPLACE INTO depts_faits VALUES (?,?,?,?,?,?,?)",
                 ("multi", dept, len(lignes), 0, mails, len(lignes) - reseau,
                  datetime.now(timezone.utc).isoformat(timespec="seconds")))
    conn.commit()
    par_m: dict[str, int] = {}
    for x in lignes:
        if x["email"] and x["site_statut"] != "reseau":
            par_m[x["metier"]] = par_m.get(x["metier"], 0) + 1
    top = ", ".join(f"{k} {v}" for k, v in sorted(par_m.items(), key=lambda kv: -kv[1])[:6])
    print(f"    {len(lignes)} fiches ({bilan['nouveau']} nouvelles, {bilan['complete']} completees) "
          f"| avec courriel hors reseau : {mails} | enseignes : {reseau}")
    if top:
        print(f"    {top}")
    return len(lignes), bilan["nouveau"], mails


def _domaine_mail(m: str) -> str:
    return (m or "").rsplit("@", 1)[-1].strip().lower() if "@" in (m or "") else ""


def _racine(h: str) -> str:
    h = (h or "").lower().removeprefix("www.")
    for p in PLATEFORMES:
        if h == p or h.endswith("." + p):
            return ""
    return h


def reseaux_par_domaine(conn, seuil: int = 3, appliquer: bool = True) -> int:
    """Un domaine porte par `seuil` fiches ou plus = une enseigne : on l'ecarte."""
    cles_cat = tuple(metiers.PAR_CLE)
    marques = ",".join("?" * len(cles_cat))
    lignes = conn.execute(
        f"SELECT cle, nom, email, site_web FROM prospects WHERE metier IN ({marques}) "
        "AND site_statut IN ('aucun','propre') AND traite_at IS NULL", cles_cat).fetchall()
    par_dom: dict[str, list[str]] = {}
    for cle, _nom, mail, site in lignes:
        doms = set()
        d = _domaine_mail(mail)
        if d and d not in GRAND_PUBLIC:
            doms.add(_racine(d))
        if site:
            doms.add(_racine(site.split("/")[0]))
        for d in doms - {""}:
            par_dom.setdefault(d, []).append(cle)
    a_marquer = {d: c for d, c in par_dom.items() if len(set(c)) >= seuil}
    total = sum(len(set(c)) for c in a_marquer.values())
    if not a_marquer:
        print("Aucun domaine partage par plusieurs fiches.")
        return 0
    print(f"{total} fiches portent un domaine partage par {seuil}+ fiches :")
    for d, c in sorted(a_marquer.items(), key=lambda kv: -len(kv[1]))[:15]:
        print(f"   {len(set(c)):>4}  {d}")
    if appliquer:
        for d, c in a_marquer.items():
            conn.executemany(
                "UPDATE prospects SET site_statut='reseau', "
                "note_interne=COALESCE(note_interne,'') || ? WHERE cle=?",
                [(f" [reseau: domaine {d}]", k) for k in set(c)])
        conn.commit()
    return total


def stats(conn) -> None:
    cles_cat = list(metiers.PAR_CLE)
    marques = ",".join("?" * len(cles_cat))
    rangs = conn.execute(f"""
        SELECT metier,
               COUNT(*),
               SUM(site_statut='reseau'),
               SUM(site_statut<>'reseau' AND COALESCE(email,'')<>''),
               SUM(site_statut<>'reseau' AND COALESCE(email,'')<>'' AND traite_at IS NULL),
               SUM(site_statut<>'reseau' AND COALESCE(email,'')='' AND COALESCE(site_web,'')<>''
                   AND mail_cherche_at IS NULL)
          FROM prospects WHERE metier IN ({marques})
         GROUP BY 1 ORDER BY 5 DESC""", cles_cat).fetchall()
    if not rangs:
        print("Aucune fiche multi-metiers. Lance --dept 54 ou --tous.")
        return
    print(f"\n{'metier':18} {'fiches':>7} {'reseau':>7} {'courriel':>9} {'A ECRIRE':>9} {'site a fouiller':>16}")
    tot = [0] * 5
    for m, *v in rangs:
        v = [x or 0 for x in v]
        tot = [a + b for a, b in zip(tot, v)]
        print(f"{m:18} {v[0]:>7} {v[1]:>7} {v[2]:>9} {v[3]:>9} {v[4]:>16}")
    print(f"{'TOTAL':18} {tot[0]:>7} {tot[1]:>7} {tot[2]:>9} {tot[3]:>9} {tot[4]:>16}")
    faits = conn.execute("SELECT COUNT(*) FROM depts_faits WHERE metier='multi'").fetchone()[0]
    print(f"\n{faits} departement(s) collecte(s) sur {len(co.DEPARTEMENTS)}.")
    print("« site a fouiller » : python3 _scripts/mails_sites.py --metier multi")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dept", action="append")
    p.add_argument("--region", action="append", help=", ".join(sorted(co.REGIONS)))
    p.add_argument("--tous", action="store_true")
    p.add_argument("--reprendre", action="store_true",
                   help="sauter les departements deja collectes")
    p.add_argument("--courriel-seul", action="store_true",
                   help="ne prendre que les fiches qui portent deja un courriel "
                        "(sans les sites a fouiller)")
    p.add_argument("--seuil-domaine", type=int, default=3)
    p.add_argument("--reseaux", action="store_true", help="seulement la passe domaines")
    p.add_argument("--stats", action="store_true")
    p.add_argument("--db", default=None)
    a = p.parse_args()

    conn = ouvrir(Path(a.db) if a.db else None)
    if a.stats:
        stats(conn); return
    if a.reseaux:
        reseaux_par_domaine(conn, a.seuil_domaine); stats(conn); return

    depts = list(a.dept or [])
    for r in a.region or []:
        if r.lower() not in co.REGIONS:
            sys.exit(f"Region inconnue : {r}")
        depts += co.REGIONS[r.lower()]
    if a.tous:
        depts += co.DEPARTEMENTS
    if not depts:
        p.error("donne --dept, --region, --tous, --stats ou --reseaux")
    if a.reprendre:
        faits = {r[0] for r in conn.execute(
            "SELECT departement FROM depts_faits WHERE metier='multi'")}
        depts = [d for d in depts if d not in faits]
    depts = list(dict.fromkeys(depts))

    print("Controle de couverture des serveurs Overpass :")
    co.SERVEURS = list(SERVEURS)
    co.verifier_serveurs()
    print(f"\n{len(metiers.CATALOGUE)} metiers, {len(depts)} departement(s).")
    t = n = m = 0
    rates = 0
    for i, d in enumerate(depts, 1):
        a1, b1, c1 = traiter_dept(conn, d, not a.courriel_seul)
        t += a1; n += b1; m += c1
        rates = rates + 1 if a1 == 0 else 0
        if rates >= ECHECS_MAX:
            print(f"\n{ECHECS_MAX} departements rates d'affilee : les serveurs "
                  "Overpass sont satures. Arret ; relance plus tard avec "
                  "--reprendre, ce qui est fait est garde.")
            break
        if i < len(depts):
            time.sleep(co.PAUSE)
    print(f"\n===== {t} fiches, {n} nouvelles, {m} avec courriel hors enseigne =====\n")
    reseaux_par_domaine(conn, a.seuil_domaine)
    stats(conn)


if __name__ == "__main__":
    main()
