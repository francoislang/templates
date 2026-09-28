#!/usr/bin/env python3
"""Va chercher une adresse de contact sur le site des prospects.

Le vivier « refonte » compte 1 295 garages qui ont un site mais dont la base
n'a aucun courriel. Or 86 % des numeros sont des fixes : sans adresse, le seul
canal restant est l'appel. L'adresse est presque toujours affichee sur le site
lui-meme -- c'est la que ce script va la chercher.

Ce qu'il fait, pour chaque prospect :

  1. il lit robots.txt et s'y tient ;
  2. il charge la page d'accueil, puis au plus trois pages internes dont le
     lien ressemble a « contact », « nous joindre » ou « mentions legales » ;
  3. il releve les adresses : liens mailto:, texte en clair, formes
     maquillees (« nom (at) domaine point fr »), et le chiffrement
     Cloudflare (data-cfemail), tres repandu et invisible sans decodage ;
  4. il ecarte le bruit -- noms de fichiers image, adresses de l'hebergeur,
     de Sentry, de Wix, exemples de formulaire -- puis classe ce qui reste :
     une adresse sur le domaine du prospect vaut mieux qu'une Gmail, et
     « contact@ » mieux que « jean.dupont@ » ;
  5. il ecrit la meilleure, sans jamais ecraser une valeur deja connue.

Chaque prospect visite est horodate (mail_cherche_at), donc une seconde
execution reprend ou la premiere s'est arretee au lieu de tout refaire.

ATTENTION : a lancer depuis ta machine. Le conteneur de Claude et la machine
virtuelle du pont ne joignent pas les sites externes (403 du mandataire).

Usage :
    python3 _scripts/mails_sites.py --apercu --nombre 20
    python3 _scripts/mails_sites.py --nombre 200
    python3 _scripts/mails_sites.py                    tout le vivier
    python3 _scripts/mails_sites.py --relancer         reessaie les echecs
"""
from __future__ import annotations

import argparse
import base64
import binascii
import concurrent.futures as cf
import html as htmlmod
import re
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:                                     # pragma: no cover
    sys.exit("requests manque : lance ce script avec le python du depot,\n"
             "    .venv/bin/python _scripts/mails_sites.py ...\n"
             "et non « python3 », qui est le python systeme de macOS.")

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "prospection.db"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
DELAI = 12              # secondes par requete
TAILLE_MAX = 1_500_000  # octets lus par page
PAUSE_HOTE = 1.0        # une requete par seconde et par hote
PAGES_MAX = 4           # accueil + 3 pages internes

# --------------------------------------------------------------------------
# Ce qu'on refuse

# Hebergeurs, regies, outils : leurs adresses trainent dans le pied de page ou
# dans le code, et n'ont rien a voir avec le garagiste.
DOMAINES_TIERS = (
    "wix.com", "wixpress.com", "parastorage.com", "webself.net", "jimdo.com",
    "e-monsite.com", "sitew.com", "site123", "squarespace.com", "shopify.com",
    "wordpress.com", "wordpress.org", "automattic.com", "woocommerce.com",
    "godaddy.com", "ionos.", "ovh.net", "ovh.com", "hostinger", "o2switch",
    "gandi.net", "1and1.", "strato.", "netlify.", "vercel.", "github.com",
    "sentry.io", "sentry-next", "google.com", "googlemail.com", "gstatic.com",
    "facebook.com", "instagram.com", "doubleclick", "cloudflare.com",
    "solocal.com", "pagesjaunes.fr", "mappy.com", "vitrine-solocal",
    "example.com", "example.org", "domain.com", "email.com", "monsite.com",
    "votresite.fr", "nomdedomaine.fr", "adresse.fr", "test.com",
    "sitemap", "schema.org", "w3.org", "jquery.com", "bootstrapcdn",
    "wixsite.com", "wixstudio.com", "sentry.wixpress.com", "pagesperso-orange.fr",
)

# Parties gauches bidon : gabarits de formulaire, code JavaScript ramasse par
# la regex, exemples laisses par l'agence.
GAUCHE_INTERDITE = {
    "email", "e-mail", "mail", "votreemail", "votre-email", "votre.email",
    "votremail", "adresse", "monemail", "nom", "prenom", "nom.prenom",
    "exemple", "example", "test", "user", "username", "utilisateur",
    "no-reply", "noreply", "ne-pas-repondre", "nepasrepondre", "donotreply",
    "sentry", "wordpress", "admin-ajax", "abc", "xxx", "aaa", "toto",
}

# Fin de chaine qui trahit un nom de fichier attrape par la regex
# (« logo@2x.png », « sprite@3x.webp »).
FICHIERS = re.compile(
    r"\.(png|jpe?g|gif|webp|svg|ico|css|js|json|woff2?|ttf|eot|mp4|pdf|avif)$",
    re.I)

# Messageries grand public : parfaitement valables pour un garage, mais une
# adresse sur le domaine du site vaut mieux.
GRAND_PUBLIC = {
    "gmail.com", "orange.fr", "wanadoo.fr", "free.fr", "sfr.fr", "neuf.fr",
    "hotmail.com", "hotmail.fr", "outlook.fr", "outlook.com", "live.fr",
    "yahoo.fr", "yahoo.com", "laposte.net", "bbox.fr", "aliceadsl.fr",
    "numericable.fr", "icloud.com", "me.com",
}

# Parties gauches qui designent la bonne boite : celle qu'on veut demarcher.
GAUCHE_UTILE = {
    "contact": 4, "accueil": 3, "info": 3, "infos": 3, "devis": 3,
    "commercial": 3, "secretariat": 2, "atelier": 2, "garage": 2,
    "carrosserie": 2, "rdv": 2, "bonjour": 2, "direction": 1, "gerant": 1,
    "compta": -2, "comptabilite": -2, "facturation": -2, "rh": -3,
    "recrutement": -3, "emploi": -3, "webmaster": -2, "presse": -2,
    "sav": 0, "pieces": 0,
}

# Une adresse chez un constructeur ou une enseigne (« ...@reseau.renault.fr »)
# ne designe pas un independant : c'est une succursale que le filtre reseau a
# laissee passer. On ne l'ecrit pas, on la signale.
ENSEIGNES_MAIL = (
    "renault.fr", "dacia.fr", "peugeot.fr", "peugeot.com", "citroen.fr",
    "opel.fr", "ford.fr", "toyota.fr", "nissan.fr", "volkswagen.fr", "audi.fr",
    "bmw.fr", "mercedes-benz.fr", "e-leclerc.com", "leclerc.fr", "norauto.fr",
    "midas.fr", "feuvert.fr", "speedy.fr", "euromaster.fr", "point-s.fr",
    "carglass.fr", "delko.fr", "avatacar.com", "top-garage.fr", "vulco.fr",
    "profilplus.fr", "siligom.fr", "motrio.fr", "bestdrive.fr", "eurorepar.fr",
    "autosphere.fr", "autoprimo.com", "ad.fr", "dekra.com", "securitest.fr",
    "autovision.fr", "autosur.fr",
)

MOTS_CONTACT = ("contact", "nous-joindre", "nous joindre", "nous-contacter",
                "nous contacter", "mentions", "legal", "coordonnees",
                "a-propos", "qui-sommes-nous", "acces", "infos-pratiques")

# --------------------------------------------------------------------------
# Extraction

# Le « @ » est souvent encode (%40) et suivi d'un ?subject= : on prend tout
# jusqu'au separateur, et c'est apres decodage qu'on verifie la forme.
RE_MAILTO = re.compile(r"""mailto:\s*([^"'>\s?&#]+)""", re.I)
RE_BRUT = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}")
# « nom (at) domaine (dot) fr », « nom [arobase] domaine . fr »
RE_MAQUILLE = re.compile(
    r"([A-Za-z0-9._%+\-]{2,64})\s*(?:\(|\[|&#64;|\{)?\s*"
    r"(?:at|@|arobase|arobax)\s*(?:\)|\]|\})?\s*"
    r"([A-Za-z0-9.\-]{2,64})\s*(?:\(|\[|\{)?\s*"
    r"(?:dot|point|\.)\s*(?:\)|\]|\})?\s*([A-Za-z]{2,10})",
    re.I)
RE_CFEMAIL = re.compile(r"""data-cfemail=["']([0-9a-fA-F]{8,})["']""")
RE_LIEN = re.compile(r"""<a\b[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""",
                     re.I | re.S)
RE_BALISE = re.compile(r"<[^>]+>")


def decode_cfemail(chiffre: str) -> str:
    """Cloudflare masque les adresses : premier octet = cle, puis XOR."""
    try:
        octets = bytes.fromhex(chiffre)
    except ValueError:
        return ""
    cle, corps = octets[0], octets[1:]
    try:
        return "".join(chr(o ^ cle) for o in corps)
    except ValueError:
        return ""


def est_tiers(hote: str) -> bool:
    """Comparaison par etiquette, jamais par sous-chaine : « mail.com » dans
    la liste ne doit pas emporter « gmail.com », qui est l'adresse de la
    moitie des garagistes."""
    h = "." + hote.lower().strip(".")
    for t in DOMAINES_TIERS:
        t = t.strip(".")
        if h.endswith("." + t) or ("." + t + ".") in h:
            return True
    return False


def recevable(adresse: str) -> bool:
    """Le filtre du bruit. Genereux sur la forme, strict sur la provenance."""
    adresse = adresse.strip().strip(".,;:()[]<>\"'").lower()
    if adresse.count("@") != 1 or len(adresse) > 120:
        return False
    gauche, hote = adresse.split("@")
    if not gauche or not hote or "." not in hote:
        return False
    if FICHIERS.search(adresse) or FICHIERS.search(gauche):
        return False
    if not re.fullmatch(r"[a-z0-9._%+\-]{1,64}", gauche):
        return False
    if not re.fullmatch(r"[a-z0-9.\-]+\.[a-z]{2,24}", hote):
        return False
    if gauche.strip("._-") in GAUCHE_INTERDITE:
        return False
    # « 2x » de « logo@2x », « u003e » echappe de JSON, suites de chiffres
    if re.fullmatch(r"\d?x|u00[0-9a-f]{2}|\d+", gauche):
        return False
    if est_tiers(hote):
        return False
    return True


def est_enseigne(adresse: str) -> str:
    hote = adresse.rsplit("@", 1)[-1].lower()
    h = "." + hote
    for e in ENSEIGNES_MAIL:
        if h.endswith("." + e):
            return e
    return ""


def racine(hote: str) -> str:
    """Domaine enregistrable, grossierement : les deux derniers labels, trois
    pour les suffixes composes (.co.uk, .com.fr)."""
    bouts = hote.lower().strip(".").split(".")
    if len(bouts) >= 3 and bouts[-2] in ("co", "com", "asso", "gouv", "org"):
        return ".".join(bouts[-3:])
    return ".".join(bouts[-2:])


def moissonner(page: str) -> dict[str, int]:
    """Toutes les adresses d'une page, avec un bonus de provenance."""
    trouve: dict[str, int] = {}

    def garder(adresse: str, bonus: int) -> None:
        a = adresse.strip().strip(".,;:()[]<>\"'").lower()
        a = htmlmod.unescape(a)
        if recevable(a):
            trouve[a] = max(trouve.get(a, -99), bonus)

    for chiffre in RE_CFEMAIL.findall(page):
        garder(decode_cfemail(chiffre), 3)
    for brut in RE_MAILTO.findall(page):
        garder(urllib.parse.unquote(brut), 3)

    texte = htmlmod.unescape(RE_BALISE.sub(" ", page))
    for brut in RE_BRUT.findall(texte):
        garder(brut, 1)
    for gauche, milieu, fin in RE_MAQUILLE.findall(texte):
        garder(f"{gauche}@{milieu}.{fin}", 2)
    return trouve


def noter(adresse: str, provenance: int, hote_site: str) -> int:
    """Plus c'est haut, plus l'adresse a de chances d'etre la bonne boite."""
    gauche, hote = adresse.split("@")
    note = provenance
    if racine(hote) == racine(hote_site):
        note += 6
    elif hote in GRAND_PUBLIC:
        note += 1
    else:
        note -= 2              # un tiers inconnu : fournisseur, partenaire...
    note += GAUCHE_UTILE.get(gauche.split(".")[0], 0)
    if "." in gauche or "-" in gauche:
        note += 1              # prenom.nom@ : c'est quelqu'un, pas un robot
    return note


# --------------------------------------------------------------------------
# Reseau

_verrous: dict[str, float] = {}
_verrou_global = threading.Lock()
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def _attendre(hote: str) -> None:
    with _verrou_global:
        dernier = _verrous.get(hote, 0.0)
        reste = PAUSE_HOTE - (time.time() - dernier)
        _verrous[hote] = time.time() + max(reste, 0.0)
    if reste > 0:
        time.sleep(reste)


def autorise(session, url: str) -> bool:
    morceaux = urllib.parse.urlsplit(url)
    origine = f"{morceaux.scheme}://{morceaux.netloc}"
    with _verrou_global:
        connu = origine in _robots
    if not connu:
        rp = urllib.robotparser.RobotFileParser()
        try:
            _attendre(morceaux.netloc)
            r = session.get(origine + "/robots.txt", timeout=DELAI)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])                    # pas de robots.txt : on peut lire
        with _verrou_global:
            _robots[origine] = rp
    rp = _robots.get(origine)
    try:
        return rp is None or rp.can_fetch(UA, url)
    except Exception:
        return True


def charger(session, url: str) -> tuple[str, str]:
    """Le HTML de la page, et l'URL finale apres redirections."""
    hote = urllib.parse.urlsplit(url).netloc
    if not autorise(session, url):
        return "", url
    _attendre(hote)
    r = session.get(url, timeout=DELAI, allow_redirects=True, stream=True)
    if r.status_code >= 400:
        r.close()
        raise requests.HTTPError(f"HTTP {r.status_code}")
    type_ = (r.headers.get("content-type") or "").lower()
    if "html" not in type_ and "text" not in type_:
        r.close()
        return "", r.url
    morceaux = []
    total = 0
    for bloc in r.iter_content(65536):
        morceaux.append(bloc)
        total += len(bloc)
        if total >= TAILLE_MAX:
            break
    r.close()
    brut = b"".join(morceaux)
    encodage = r.encoding or "utf-8"
    return brut.decode(encodage, errors="replace"), r.url


def pages_contact(accueil: str, base: str) -> list[str]:
    """Les liens internes qui sentent la page de contact, les meilleurs d'abord."""
    vus: dict[str, int] = {}
    origine = urllib.parse.urlsplit(base)
    for href, libelle in RE_LIEN.findall(accueil):
        href = htmlmod.unescape(href.strip())
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        cible = urllib.parse.urljoin(base, href)
        m = urllib.parse.urlsplit(cible)
        if m.scheme not in ("http", "https") or m.netloc != origine.netloc:
            continue
        cible = urllib.parse.urlunsplit((m.scheme, m.netloc, m.path, "", ""))
        if cible.rstrip("/") == base.rstrip("/"):
            continue
        texte = (RE_BALISE.sub(" ", libelle) + " " + m.path).lower()
        note = 0
        if "contact" in texte:
            note = 3
        elif "mention" in texte or "legal" in texte:
            note = 2
        elif any(mot in texte for mot in MOTS_CONTACT):
            note = 1
        if note:
            vus[cible] = max(vus.get(cible, 0), note)
    classe = sorted(vus, key=lambda u: (-vus[u], len(u)))
    return classe[:PAGES_MAX - 1]


def chercher(prospect: dict) -> dict:
    """Le travail pour un prospect : renvoie l'adresse retenue, ou l'echec."""
    site = (prospect["site_web"] or "").strip()
    if not site.startswith(("http://", "https://")):
        site = "https://" + site.lstrip("/")
    session = requests.Session()
    session.headers.update({"User-Agent": UA,
                            "Accept-Language": "fr-FR,fr;q=0.9"})
    try:
        accueil, url_finale = charger(session, site)
    except Exception as exc:
        # bien des petits garages sont encore en http, ou en TLS casse
        try:
            accueil, url_finale = charger(
                session, "http://" + urllib.parse.urlsplit(site).netloc)
        except Exception:
            return {"cle": prospect["cle"], "email": "", "source": "",
                    "erreur": f"{type(exc).__name__}: {exc}"[:120]}
    if not accueil:
        return {"cle": prospect["cle"], "email": "", "source": "",
                "erreur": "page vide ou non HTML"}

    hote_site = urllib.parse.urlsplit(url_finale).netloc
    candidats = moissonner(accueil)
    sources = {a: "accueil" for a in candidats}

    for lien in pages_contact(accueil, url_finale):
        if any(noter(a, p, hote_site) >= 8 for a, p in candidats.items()):
            break                       # deja une adresse du domaine : assez
        try:
            page, _ = charger(session, lien)
        except Exception:
            continue
        for adresse, provenance in moissonner(page).items():
            if provenance > candidats.get(adresse, -99):
                candidats[adresse] = provenance
            sources.setdefault(adresse, urllib.parse.urlsplit(lien).path or lien)

    session.close()
    if not candidats:
        return {"cle": prospect["cle"], "email": "", "source": "",
                "erreur": "aucune adresse sur le site"}
    meilleur = max(candidats, key=lambda a: (noter(a, candidats[a], hote_site), -len(a)))
    if noter(meilleur, candidats[meilleur], hote_site) < 1:
        return {"cle": prospect["cle"], "email": "", "source": "",
                "erreur": f"adresses ecartees ({len(candidats)} vues)"}
    enseigne = est_enseigne(meilleur)
    if enseigne:
        # « danielle.capelli.stismier02@reseau.renault.fr » : releve sur un
        # vrai prospect de la base. L'adresse est bonne, mais le prospect ne
        # l'est pas -- c'est une succursale, pas un independant.
        return {"cle": prospect["cle"], "email": "", "source": "",
                "erreur": f"reseau {enseigne} ({meilleur})", "reseau": enseigne}
    return {"cle": prospect["cle"], "email": meilleur,
            "source": sources.get(meilleur, "?"), "erreur": "",
            "autres": sorted(a for a in candidats if a != meilleur)[:4]}


# --------------------------------------------------------------------------
# Base

def migrer(conn) -> None:
    colonnes = {d[1] for d in conn.execute("PRAGMA table_info(prospects)")}
    if "mail_cherche_at" not in colonnes:
        conn.execute("ALTER TABLE prospects ADD COLUMN mail_cherche_at TEXT")
    if "mail_source" not in colonnes:
        conn.execute("ALTER TABLE prospects ADD COLUMN mail_source TEXT")
    conn.commit()


def _domaine(site: str) -> str:
    site = (site or "").strip().lower()
    if not site.startswith(("http://", "https://")):
        site = "https://" + site.lstrip("/")
    return urllib.parse.urlsplit(site).netloc.removeprefix("www.")


def vivier(conn, nombre: int, relancer: bool, statut: str,
           seuil: int = 3) -> list[dict]:
    where = ["COALESCE(site_web,'') <> ''", "COALESCE(email,'') = ''"]
    params: list = []
    if statut != "tous":
        where.append("site_statut = ?")
        params.append(statut)
    else:
        where.append("site_statut IN ('aucun','propre')")
    if not relancer:
        where.append("mail_cherche_at IS NULL")
    sql = ("SELECT cle, nom, commune, departement, site_web FROM prospects "
           f"WHERE {' AND '.join(where)} ORDER BY departement, nom")
    conn.row_factory = sqlite3.Row
    lignes = [dict(r) for r in conn.execute(sql, params)]

    # Un meme domaine porte par plusieurs fiches, c'est un reseau que le
    # filtre par nom n'a pas vu : ad.fr en compte 253 a lui seul. Inutile
    # d'aller y chercher 253 fois la meme adresse de siege.
    partages: dict[str, int] = {}
    for l in lignes:
        d = _domaine(l["site_web"])
        partages[d] = partages.get(d, 0) + 1
    ecartes = {d for d, n in partages.items() if n >= seuil}
    if ecartes:
        total = sum(partages[d] for d in ecartes)
        print(f"{total} fiches ecartees : {len(ecartes)} domaines portes par "
              f"{seuil} fiches ou plus (des reseaux, presque surement)")
        for d in sorted(ecartes, key=lambda x: -partages[x])[:10]:
            print(f"    {partages[d]:>4}  {d}")
        print()
        lignes = [l for l in lignes if _domaine(l["site_web"]) not in ecartes]
    return lignes[:nombre] if nombre else lignes


def enregistrer(conn, res: dict, apercu: bool) -> None:
    if apercu:
        return
    maintenant = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # COALESCE : on ne remplace jamais une adresse deja connue, meme si une
    # autre execution l'a ecrite entre-temps.
    conn.execute(
        "UPDATE prospects SET email = COALESCE(NULLIF(email,''), ?), "
        "mail_source = COALESCE(mail_source, ?), mail_cherche_at = ? "
        "WHERE cle = ?",
        (res["email"] or None, res["source"] or res["erreur"], maintenant,
         res["cle"]))
    conn.commit()


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", type=int, default=0, help="0 = tout le vivier")
    ap.add_argument("--apercu", action="store_true", help="n'ecrit rien")
    ap.add_argument("--relancer", action="store_true",
                    help="reessaie aussi les sites deja visites")
    ap.add_argument("--statut", default="tous",
                    choices=("tous", "propre", "aucun"))
    ap.add_argument("--fils", type=int, default=4, help="sites en parallele")
    ap.add_argument("--seuil-domaine", type=int, default=3,
                    help="a partir de combien de fiches un domaine partage "
                         "est tenu pour un reseau et ecarte (0 = aucun filtre)")
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()

    conn = sqlite3.connect(args.db, timeout=30)
    migrer(conn)
    lots = vivier(conn, args.nombre, args.relancer, args.statut,
                  args.seuil_domaine or 10 ** 9)
    if not lots:
        print("Rien a faire : tous les sites du vivier ont deja ete visites.")
        return 0

    print(f"{len(lots)} sites a visiter"
          f"{'  (apercu, rien ne sera ecrit)' if args.apercu else ''}\n")
    trouves = echecs = reseaux = 0
    debut = time.time()
    with cf.ThreadPoolExecutor(max_workers=max(1, args.fils)) as pool:
        for i, res in enumerate(pool.map(chercher, lots), 1):
            p = next(x for x in lots if x["cle"] == res["cle"])
            etiquette = f"{p['nom'][:38]:<38} {p['departement']:>3}"
            if res["email"]:
                trouves += 1
                autres = res.get("autres") or []
                suite = f"   (+{len(autres)})" if autres else ""
                print(f"  ✓ {etiquette}  {res['email']}{suite}")
            elif res.get("reseau"):
                reseaux += 1
                print(f"  ⚑ {etiquette}  — {res['erreur']}")
            else:
                echecs += 1
                print(f"  · {etiquette}  — {res['erreur']}")
            enregistrer(conn, res, args.apercu)
            if i % 50 == 0:
                print(f"    … {i}/{len(lots)}  {trouves} trouvees")

    duree = time.time() - debut
    taux = 100 * trouves / max(len(lots), 1)
    print(f"\n{trouves} adresses trouvees sur {len(lots)} sites ({taux:.0f} %), "
          f"{echecs} sans resultat, en {duree/60:.1f} min.")
    if reseaux:
        print(f"{reseaux} fiches portent une adresse d'enseigne (⚑) : ce sont "
              f"des succursales, a passer en « reseau » dans nettoyer.py.")
    if args.apercu:
        print("Apercu : la base n'a pas ete modifiee.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
