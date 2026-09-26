#!/usr/bin/env python3
"""Circuit de prospection parallele : generation, CRM, message Telegram.

Meme logique que le pipeline eleveurs, mais sur une autre source et sans
jamais toucher a celui-ci : base differente (_data/prospection.db au lieu de
_data/annonces.db), verrou different, agent launchd different, journal
different. Les deux peuvent tourner le meme jour.

Chaine amont :
    collecte_osm.py     masse + telephone + presence de site   (OpenStreetMap)
    recherche_web.py    verification « a-t-il un site »        (API Brave)
    places.py           note et avis Google                    (facultatif)
    pipeline_pro.py     site de demo + fiche CRM + Telegram    (ce script)

Ce que ce script produit pour chaque prospect :
    1. un site de demonstration, publie sur GitHub Pages
    2. une fiche dans le CRM GitHub
    3. un message Telegram pret a servir d'appel telephonique, construit a
       partir des faits reellement constates sur ce garage-la

Deux differences avec le circuit eleveurs, assumees :
  - le gabarit garage n'utilise aucune photographie (planches techniques en
    SVG), donc ni Cloudinary ni Pexels ne sont sollicites ;
  - chaque site recoit une des dix identites visuelles de variantes.py,
    tiree par hachage de son slug, pour que cent sites ne se ressemblent pas.

Usage :
    python3 _scripts/pipeline_pro.py --metier garage --dry-run
    python3 _scripts/pipeline_pro.py --metier garage --nombre 5
    python3 _scripts/pipeline_pro.py --reste
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import crm                 # noqa: E402
import pipeline as pl      # noqa: E402  (helpers reutilises, jamais modifies)
import telegram            # noqa: E402
import variantes           # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "prospection.db"
VERROU_PATH = REPO_ROOT / "_data" / ".pipeline_pro.lock"
PAGES = "https://francoislang.github.io/templates"
PAR_DEFAUT = 5


METIERS: dict[str, dict] = {
    "garage": {
        "metier": "garage automobile indépendant",
        "gabarit": "reference-garage.html",
        "sections": [
            "Prestations (entretien, freinage, pneumatiques, diagnostic)",
            "Detail des prestations principales",
            "L'atelier, en planches techniques",
            "Avis clients",
            "Contact, adresse et acces",
        ],
    },
    "nautique": {
        "metier": "chantier naval / atelier de réparation de bateaux",
        "gabarit": "reference-nautique.html",
        "sections": [
            "Services (carenage, hivernage, stratification, moteur, greement)",
            "Realisations",
            "Manutention et capacites",
            "Avis clients",
            "Acces au port et coordonnees",
        ],
    },
}


# --------------------------------------------------------------------------
# verrou propre a ce circuit
# --------------------------------------------------------------------------

class DejaEnCours(RuntimeError):
    pass


@contextmanager
def verrou(attente_max: int = 0):
    VERROU_PATH.parent.mkdir(parents=True, exist_ok=True)
    f = open(VERROU_PATH, "a+", encoding="utf-8")
    debut = time.monotonic()
    while True:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() - debut >= attente_max:
                f.seek(0)
                detenteur = f.read().strip() or "processus inconnu"
                f.close()
                raise DejaEnCours(detenteur)
            time.sleep(1)
    f.seek(0); f.truncate()
    f.write(f"pid={os.getpid()} depuis={datetime.now(timezone.utc).isoformat(timespec='seconds')}\n")
    f.flush()
    try:
        yield
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()


# --------------------------------------------------------------------------
# base
# --------------------------------------------------------------------------

def ouvrir() -> sqlite3.Connection:
    if not DB_PATH.exists():
        sys.exit(
            f"{DB_PATH} n'existe pas.\n"
            "  1) python3 _scripts/collecte_osm.py --region bretagne\n"
            "  2) python3 _scripts/pipeline_pro.py --reste"
        )
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "prospects" not in tables:
        sys.exit("La table `prospects` n'existe pas. Lance collecte_osm.py d'abord.")
    deja = {r[1] for r in conn.execute("PRAGMA table_info(prospects)")}
    for col, typ in {"traite_at": "TEXT", "site_genere": "TEXT",
                     "crm_issue": "TEXT", "variante": "TEXT",
                     "erreur": "TEXT"}.items():
        if col not in deja:
            conn.execute(f"ALTER TABLE prospects ADD COLUMN {col} {typ}")
    conn.commit()
    return conn


# Les enseignes de reseau restent exclues en toutes circonstances : leur
# communication est pilotee par la tete de reseau, elles ne decident rien.
# En revanche « propre » (le garage a deja un site) est un vivier valable :
# un site de 2015 qui bloque le zoom est un prospect, pas un client perdu.
_FILTRE_SANS_SITE = "site_statut = 'aucun'"
_FILTRE_TOUS      = "site_statut IN ('aucun','propre')"


def _filtre(avec_site: bool) -> str:
    return f"""
      metier = ?
  AND {_FILTRE_TOUS if avec_site else _FILTRE_SANS_SITE}
  AND COALESCE(telephone,'') <> ''
  AND COALESCE(nom,'') <> ''
  AND traite_at IS NULL
"""


def a_traiter(conn, metier: str, limit: int, tel_crm: set[str] | None = None,
              avec_site: bool = False) -> list[dict]:
    """Les plus etoffes d'abord : un garage avec beaucoup d'avis tourne.

    Trois protections contre le doublon, parce que `traite_at` sur la cle OSM
    ne suffit pas :
      - un numero deja demarche est ecarte, meme porte par une autre fiche
        (81 lignes de la base partagent un numero avec une autre) ;
      - un numero deja present dans le CRM est ecarte, comme le fait le
        pipeline eleveurs ;
      - a l'interieur d'un meme lot, on ne garde qu'une fiche par numero.
    """
    cur = conn.execute(
        f"SELECT * FROM prospects WHERE {_filtre(avec_site)} "
        "  AND telephone NOT IN (SELECT telephone FROM prospects "
        "      WHERE traite_at IS NOT NULL AND COALESCE(telephone,'') <> '') "
        # CAST explicite : si une colonne arrive en TEXT (import CSV, autre
        # collecteur), « 8 » passerait avant « 49 » en tri alphabetique et on
        # demarcherait les plus petits garages en premier sans s'en apercevoir.
        "ORDER BY (site_statut='aucun') DESC, "
        "CAST(COALESCE(avis,0) AS INTEGER) DESC, "
        "CAST(COALESCE(note,0) AS REAL) DESC, "
        "departement, commune, nom LIMIT ?", (metier, limit * 4))

    def _cle_tel(t: str) -> str:
        return re.sub(r"\D", "", t or "")

    vus = set(tel_crm or ())
    lot = []
    for r in cur:
        d = dict(r)
        t = _cle_tel(d.get("telephone"))
        if not t or t in vus:
            continue
        vus.add(t)
        lot.append(d)
        if len(lot) >= limit:
            break
    return lot


def compter(conn, metier: str, avec_site: bool = False) -> int:
    return conn.execute(
        f"SELECT COUNT(DISTINCT telephone) FROM prospects "
        f"WHERE {_filtre(avec_site)}", (metier,)).fetchone()[0]


def marquer(conn, cle: str, **champs) -> None:
    champs["traite_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        f"UPDATE prospects SET {','.join(c + '=?' for c in champs)} WHERE cle=?",
        [*champs.values(), cle])
    conn.commit()


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------

def _cle_openrouter() -> str:
    for fp in (REPO_ROOT / ".env", Path(os.path.expanduser("~/.hermes/.env"))):
        if not fp.exists():
            continue
        for ligne in fp.read_text(encoding="utf-8").splitlines():
            if ligne.startswith(("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")) and "=" in ligne:
                return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _appeler_modele(prompt: str) -> tuple[str, str]:
    import requests
    cle = _cle_openrouter()
    if not cle:
        return "", "OPENROUTER_API_KEY absente"
    payload = {"model": "deepseek/deepseek-v4-pro",
               "messages": [{"role": "user", "content": prompt}],
               "max_tokens": 24000, "stream": True}
    derniere = ""
    for tentative in (1, 2):
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                              headers={"Authorization": f"Bearer {cle}",
                                       "Content-Type": "application/json"},
                              json=payload, timeout=(30, 900), stream=True)
            if r.status_code != 200:
                derniere = f"HTTP {r.status_code}"
                print(f"   /!\\ OpenRouter {derniere} ({tentative}/2)")
                continue
            morceaux = []
            for brute in r.iter_lines(decode_unicode=False):
                if not brute:
                    continue
                ligne = brute.decode("utf-8", "replace")
                if not ligne.startswith("data: "):
                    continue
                corps = ligne[6:]
                if corps.strip() == "[DONE]":
                    break
                try:
                    delta = json.loads(corps)["choices"][0].get("delta", {})
                except (ValueError, KeyError, IndexError):
                    continue
                if delta.get("content"):
                    morceaux.append(delta["content"])
            html = "".join(morceaux)
            if html.strip():
                return html, ""
            derniere = "reponse vide"
        except requests.exceptions.RequestException as e:
            derniere = type(e).__name__
            time.sleep(5)
    return "", derniere or "echec inconnu"


def charger_gabarit(metier: str) -> str:
    conf = METIERS[metier]
    propre = REPO_ROOT / "_templates" / conf["gabarit"]
    if propre.exists():
        texte = propre.read_text(encoding="utf-8")
        if texte.strip():
            print(f"   gabarit : {propre.name}")
            return texte
    print(f"   gabarit : repli sur reference.html — {conf['gabarit']} absent")
    return pl._charger_reference()


def _appliquer_variante(html: str, v: dict) -> str:
    """Injecte l'identite visuelle apres coup plutot que de la demander au
    modele : deterministe, verifiable, et le modele ne peut pas la rater."""
    bloc = variantes.css(v)
    if "</style>" in html:
        html = html.replace("</style>", bloc + "\n</style>", 1)
    else:
        html = html.replace("</head>", f"<style>\n{bloc}\n</style>\n</head>", 1)
    lien = variantes.lien_police(v)
    if "fonts.googleapis.com" in html:
        html = re.sub(r'<link href="https://fonts\.googleapis\.com[^>]*>', lien, html, count=1)
    else:
        html = html.replace("</head>", lien + "\n</head>", 1)
    return html


def generer_site(p: dict, metier: str, force=False) -> tuple[str | None, str, dict]:
    """Retourne (url, erreur, variante)."""
    conf = METIERS[metier]
    nom = (p.get("nom") or "").strip()
    slug = pl.slugify(nom)
    v = variantes.pour(slug)
    cible = REPO_ROOT / slug / "index.html"
    if cible.exists() and not force:
        return f"{PAGES}/{slug}/", "", v

    gabarit = charger_gabarit(metier)
    if not gabarit.strip():
        return None, "aucun gabarit lisible", v

    ville = p.get("commune") or ""
    cp = p.get("code_postal") or ""
    faits = [f"- Nom : {nom}", f"- Activite : {conf['metier']}",
             f"- Telephone : {p.get('telephone','')}"]
    for libelle, champ in (("Adresse", "adresse"), ("Code postal", "code_postal"),
                           ("Commune", "commune"), ("Horaires", "horaires"),
                           ("Email", "email")):
        if p.get(champ):
            faits.append(f"- {libelle} : {p[champ]}")
    if p.get("avis"):
        note = f"{p['note']:.1f}" if p.get("note") else "?"
        faits.append(f"- Avis Google : {note}/5 sur {p['avis']} avis")

    prompt = f"""Cree un site vitrine HTML complet pour un {conf['metier']}.

GABARIT DE REFERENCE (structure a reproduire exactement) :
{gabarit}

FAITS VERIFIES — tu ne peux utiliser QUE ceux-la :
{chr(10).join(faits)}

SECTIONS a couvrir :
{chr(10).join('  - ' + s for s in conf['sections'])}

REGLES ABSOLUES :
- N'INVENTE AUCUN FAIT sur cette entreprise reelle. Le site sera montre a son
  patron. Interdiction d'inventer un tarif, une duree de garantie, un nombre
  de salaries, une annee de creation, un vehicule de pret, une habilitation,
  ou le moindre avis client redige. Si une information ne figure pas dans la
  liste ci-dessus, elle n'apparait pas sur la page.
- Les avis sont un emplacement vide qui dit qu'il se remplira avec les vrais
  avis Google. Jamais de temoignage redige.
- Si les horaires ne sont pas dans les faits verifies, ecris « A confirmer »
  et n'active pas l'indicateur ouvert/ferme.
- Reproduis TOUTES les sections du gabarit, dans le meme ordre.
- Garde le bloc « bon de travail » de fin de page et sa mecanique d'affichage
  par ?notes : il n'est pas destine au prospect.
- Adapte le vocabulaire au metier. Aucun mot lie aux animaux, aux chiots, aux
  portees ou aux races.
- Telephone cliquable (tel:), formulaire de devis, JSON-LD, meta SEO avec la
  commune, mobile d'abord, contrastes au minimum 4,5:1.
- NE CHANGE PAS les couleurs ni la police du gabarit : une identite visuelle
  est appliquee automatiquement apres generation.
- Reponds UNIQUEMENT avec le code HTML complet."""

    html, err = _appeler_modele(prompt)
    if not html:
        return None, err, v

    html = re.sub(r"^```html?\n?", "", html)
    html = re.sub(r"\n?```\s*$", "", html)
    m = re.search(r"(<!DOCTYPE html.*</html>)", html, re.DOTALL | re.IGNORECASE)
    if m:
        html = m.group(1)

    ok, raison = pl._site_est_correct(html)
    if not ok and "photos" not in raison:
        # Le gabarit garage n'a volontairement aucune photographie : le
        # garde-fou « 10 photos minimum » ne s'applique pas ici.
        return None, f"site trop pauvre — {raison}", v

    fuite = re.findall(r"\b(chiot\w*|chien\w*|port[ée]e\w*|[ée]levage\w*|LOF)\b",
                       html, re.IGNORECASE)
    if len(fuite) > 2:
        return None, f"vocabulaire canin residuel ({len(fuite)} occurrences)", v

    html = _appliquer_variante(html, v)

    cible.parent.mkdir(exist_ok=True)
    cible.write_text(html, encoding="utf-8")
    pl._sanitize(cible, slug, {"email": p.get("email", ""),
                               "phone": p.get("telephone", "")})
    pl._inject_tracking(cible)
    subprocess.run(["git", "-C", str(REPO_ROOT), "add", f"{slug}/index.html"],
                   capture_output=True)
    return f"{PAGES}/{slug}/", "", v


# --------------------------------------------------------------------------
# message Telegram — c'est lui qui sert a passer l'appel
# --------------------------------------------------------------------------

def pitch(p: dict, metier: str, demo_url: str | None) -> str:
    """Le message a envoyer au garagiste, pret a copier-coller.

    Meme registre que le pitch eleveurs : on s'adresse a la personne, on dit
    d'ou on vient, ce qu'on propose et pourquoi, on donne la demo. Les
    arguments sont personnalises avec les faits reellement constates sur ce
    garage — jamais avec des generalites, et jamais avec un fait invente.
    """
    nom = (p.get("nom") or "").strip()
    ville = (p.get("commune") or "").strip()
    dept = (p.get("departement") or "").strip()
    lieu = f"à {ville}" if ville else "dans votre secteur"

    avis = p.get("avis")
    note = f"{p['note']:.1f}".replace(".", ",") if p.get("note") else ""
    a_facebook = bool((p.get("facebook") or "").strip())
    a_mail = bool((p.get("email") or "").strip())

    a_un_site = (p.get("site_statut") == "propre") and bool(p.get("site_web"))

    # Ouverture : on dit comment on l'a trouve, ce qui rend l'approche concrete.
    if a_un_site:
        # On ne juge PAS son site : on ne l'a pas regarde. On propose une
        # comparaison, ce qui est honnete et se refuse moins facilement.
        ouverture = (f"Je me permets de vous contacter car j'ai cherché un garage "
                     f"{lieu} et je suis tombé sur votre site, {p['site_web']}.")
    elif avis and note and int(avis) >= 10:
        ouverture = (f"Je me permets de vous contacter car j'ai cherché un garage "
                     f"{lieu} et je suis tombé sur le vôtre : {avis} avis à "
                     f"{note}/5, et pourtant aucun site à vous.")
    elif a_facebook:
        ouverture = (f"Je me permets de vous contacter car j'ai cherché un garage "
                     f"{lieu} et je n'ai trouvé de vous qu'une page Facebook.")
    else:
        ouverture = (f"Je me permets de vous contacter car j'ai cherché un garage "
                     f"{lieu} et je n'ai trouvé votre établissement que sur des "
                     f"annuaires.")

    # Avantages : les deux premiers dependent de sa situation reelle.
    avantages = []
    if a_un_site:
        avantages.append("Une page qui se lit correctement sur un téléphone, "
                         "là où se font aujourd'hui la plupart des recherches "
                         "de garage")
    elif avis and note and int(avis) >= 10:
        avantages.append(f"Vos {avis} avis affichés chez vous, et plus seulement "
                         f"sur un annuaire qui vous met en concurrence avec "
                         f"trois autres garages sur la même page")
    else:
        avantages.append("Une adresse à vous quand on cherche votre nom, plutôt "
                         "qu'une fiche d'annuaire que vous ne contrôlez pas")
    if not a_mail:
        avantages.append("Un formulaire de devis qui arrive même quand l'atelier "
                         "est fermé, au lieu d'un téléphone qui sonne dans le vide")
    else:
        avantages.append("Un formulaire de devis avec la plaque et le modèle, pour "
                         "répondre juste sans dix allers-retours")
    avantages += [
        "Vos horaires, votre adresse et vos prestations trouvables en une "
        "recherche, depuis un téléphone, au bord de la route",
        "Moins d'appels pour rien : ce que vous prenez en charge et ce que vous "
        "ne faites pas, c'est écrit",
    ]

    parties = [
        "Bonjour,",
        "",
        ouverture,
        "",
        "Je suis François-Frédéric, développeur web basé à Nancy. J'ai eu envie "
        + ("de vous proposer une autre version, pour comparaison — sans vous "
           "dire que la vôtre est mauvaise, je ne la connais pas assez."
           if a_un_site else
           "de vous proposer quelque chose : un site vitrine qui vous "
           "appartienne, au lieu de laisser les comparateurs capter vos clients."),
        "",
        ("Ce que la version que j'ai préparée apporte :" if a_un_site
         else "Un site à vous, c'est concrètement :"),
    ]
    parties += [f"\u2022  {a}" for a in avantages]

    if demo_url:
        parties += ["", "J'ai préparé une démo gratuite, sans engagement :",
                    demo_url, "",
                    "Si elle vous plaît et que vous souhaitez en discuter, "
                    "n'hésitez pas à me répondre."]
    else:
        parties += ["", "Si vous souhaitez en discuter, n'hésitez pas à me répondre."]

    parties += ["", "Bien cordialement,", "", "François-Frédéric Lang",
                "langfrancoisfrederic@gmail.com", "06 32 81 42 00"]
    return "\n".join(parties)


def message(p: dict, metier: str, demo_url: str | None, v: dict) -> str:
    """Le message Telegram : l'entete pour toi, le pitch a transferer."""
    nom = (p.get("nom") or "").strip()
    parties = [f"\U0001F527 {nom} — {METIERS[metier]['metier']}"]
    if p.get("telephone"):
        parties.append(f"\U0001F4DE {p['telephone']}")
    if (p.get("email") or "").strip():
        parties.append(f"\U0001F4E7 {p['email']}")
    lieu = (p.get("commune") or "").strip()
    if lieu and p.get("departement"):
        lieu += f" ({p['departement']})"
    if p.get("adresse"):
        lieu = f"{p['adresse']}, {lieu}" if lieu else p["adresse"]
    if lieu:
        parties.append(f"\U0001F4CD {lieu}")
    if p.get("avis"):
        note = f"{p['note']:.1f}".replace(".", ",") if p.get("note") else "?"
        parties.append(f"\u2B50 {note}/5 sur {p['avis']} avis")
    if p.get("site_statut") == "propre" and p.get("site_web"):
        parties.append(f"\u267B\uFE0F REFONTE — a deja {p['site_web']}")
    else:
        parties.append("\u2728 PREMIER SITE — aucun site aujourd'hui")
    if demo_url:
        parties.append(f"\U0001F310 {demo_url}")
        parties.append(f"\U0001F4DD Tes notes : {demo_url}?notes")
    else:
        parties.append("\u26A0\uFE0F Site non genere")
    parties.append(f"\U0001F3A8 Identite : {v['nom']}")

    parties += ["", "--- PITCH A ENVOYER ---", pitch(p, metier, demo_url),
                "--- FIN DU PITCH ---"]
    return "\n".join(parties)


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------

def run(metier: str, nombre: int, dry_run: bool, avec_site: bool = False) -> None:
    conn = ouvrir()
    reste = compter(conn, metier, avec_site)

    # Le CRM est la memoire longue : une fiche peut y exister sans que la
    # base locale le sache (relance manuelle, import, autre machine).
    tel_crm = set()
    if not dry_run:
        try:
            tel_crm = {re.sub(r"\D", "", t) for t in crm.get_existing_phones()}
            print(f"{len(tel_crm)} numeros deja presents dans le CRM, ecartes")
        except Exception as e:
            print(f"/!\\ CRM injoignable ({e}) — on continue sans ce controle")

    lot = a_traiter(conn, metier, nombre, tel_crm, avec_site)
    print(f"Marche « {metier} » : {len(lot)} prospect(s) ce tour, {reste} en reserve")

    if not lot:
        msg = (f"Vivier « {metier} » vide. Relancer collecte_osm.py sur "
               f"d'autres departements.")
        print(msg)
        if not dry_run:
            telegram.send(msg)
        return

    faits = 0
    for p in lot:
        nom = p.get("nom")
        print(f"\n{'=' * 54}\n{nom} — {p.get('commune','')} — {p.get('telephone','')}")
        if dry_run:
            v = variantes.pour(pl.slugify(nom or ""))
            print(message(p, metier, f"{PAGES}/{pl.slugify(nom or '')}/", v))
            continue

        url, err, v = generer_site(p, metier)
        if err:
            print(f"   /!\\ {err}")
            marquer(conn, p["cle"], erreur=err, variante=v["nom"])
            continue

        texte = message(p, metier, url, v)
        try:
            issue = crm.add_entry(
                elevage=nom,
                races=[METIERS[metier]["metier"]],
                phone=p.get("telephone", ""),
                demo_url=url,
                notes=f"Site actuel: {p.get('site_web') or 'aucun'} | "
                      f"Description: {METIERS[metier]['metier']} a "
                      f"{p.get('commune','')} | Pitch: {texte}",
            )
        except Exception as e:
            issue = None
            print(f"   /!\\ CRM : {e}")

        marquer(conn, p["cle"], site_genere=url, variante=v["nom"],
                crm_issue=str(issue) if issue else None)
        telegram.send(texte)
        print(f"   -> {url}  ({v['nom']})")
        faits += 1

    if faits and not dry_run:
        pl.commit_and_push(faits)
        telegram.send(f"{faits} site(s) « {metier} » publies. "
                      f"Reserve restante : {compter(conn, metier, avec_site)}")
    conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--metier", default="garage", choices=sorted(METIERS))
    p.add_argument("--nombre", type=int, default=PAR_DEFAUT)
    p.add_argument("--dry-run", action="store_true",
                   help="affiche les messages Telegram sans rien generer ni envoyer")
    p.add_argument("--reste", action="store_true", help="taille du vivier et sortie")
    p.add_argument("--avec-site", action="store_true",
                   help="inclure les garages qui ont deja un site (offre de "
                        "refonte). Les enseignes de reseau restent exclues.")
    p.add_argument("--attendre", type=int, default=0)
    p.add_argument("--db", default=None, help="base de test au lieu de prospection.db")
    args = p.parse_args()

    if args.db:
        global DB_PATH
        DB_PATH = Path(args.db)
        print(f"base de test : {DB_PATH}")

    if args.reste:
        conn = ouvrir()
        for m in sorted(METIERS):
            print(f"  {m:10} : {compter(conn, m):5} sans site  |  "
                  f"{compter(conn, m, True):5} en incluant les refontes")
        conn.close()
        return

    try:
        with verrou(args.attendre):
            run(args.metier, args.nombre, args.dry_run, args.avec_site)
    except DejaEnCours as e:
        print(f"Une autre execution tourne deja ({e}). Abandon.")
        sys.exit(75)


if __name__ == "__main__":
    main()
