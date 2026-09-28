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
  - le gabarit est livre deja colore (palette « acier »), donc la rotation
    des dix identites de variantes.py est desactivee : voir IDENTITE_FIXE.

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

import controle_design     # noqa: E402
import crm                 # noqa: E402
import pipeline as pl      # noqa: E402  (helpers reutilises, jamais modifies)
import telegram            # noqa: E402
import variantes           # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "prospection.db"
VERROU_PATH = REPO_ROOT / "_data" / ".pipeline_pro.lock"
PAGES = "https://francoislang.github.io/templates"
PAR_DEFAUT = 5

# Le gabarit garage est livre deja colore : la palette « acier » fait partie
# du fichier de reference. La rotation des dix identites de variantes.py est
# donc desactivee ici, sinon elle ecraserait ce choix.
#
# Contrepartie assumee : cent sites generes se ressembleront. La rotation se
# remet en mettant IDENTITE_FIXE a None, et le vivier a piocher serait alors
# _templates/fiche-accueil/couleur-*.css, les huit palettes validees sur ce
# gabarit-la, plutot que les dix de variantes.py, calibrees sur l'ancien.
IDENTITE_FIXE = "acier"

# Le modele est une variable, pas une constante gravee : un credit epuise ou
# un fournisseur en panne ne doit pas arreter le circuit. MODELE_PRO dans
# .env, ou --modele en ligne de commande, l'emportent. Les modeles en
# « :free » d'OpenRouter ne consomment pas de credit et permettent de
# repeter la chaine entiere sans rien depenser.
MODELE = os.environ.get("MODELE_PRO") or "deepseek/deepseek-v4-pro"


METIERS: dict[str, dict] = {
    "garage": {
        "metier": "garage automobile indépendant",
        "gabarit": "reference-garage.html",
        "sections": [
            "Ouverture : nom, activite, appel a l'action, et la fiche "
            "inclinee qui resume l'etat de l'atelier a l'heure qu'il est",
            "Bandeau de trois faits, tires des donnees verifiees",
            "Registre numerote des familles d'intervention",
            "Horaires et acces, avec le tableau des horaires",
            "Contact : numero en grand et formulaire qui compose un SMS",
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
        # Un prospect joignable au premier essai passe devant : portable,
        # puis courriel, puis fixe. Sans cela le lot du jour se remplit de
        # fixes, ou il faut tomber sur quelqu'un.
        "ORDER BY (substr(replace(replace(replace(telephone,' ',''),'.',''),"
        "'-','') ,1,2) IN ('06','07')) DESC, "
        "(COALESCE(email,'') <> '') DESC, "
        "(site_statut='aucun') DESC, "
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
    print(f"   modele : {MODELE}")
    payload = {"model": MODELE,
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


MIN_SECTIONS_PRO = 4
MIN_OCTETS_PRO = 16000


def _site_est_correct(html: str) -> tuple[bool, str]:
    """Le meme garde-fou que pour les eleveurs, aux seuils de ce circuit.

    Celui de pipeline.py exige six sections et dix photographies : le gabarit
    garage en a cinq et aucune photo, par choix. Et la regle « une section
    sans donnees disparait » peut legitimement en retirer une de plus, d'ou
    un plancher a quatre.
    """
    if not html or not html.strip():
        return False, "vide"
    if "</html>" not in html.lower():
        return False, "HTML incomplet (generation coupee)"
    sections = len(re.findall(r"<section", html, re.IGNORECASE))
    if sections < MIN_SECTIONS_PRO:
        return False, f"{sections} sections (minimum {MIN_SECTIONS_PRO})"
    octets = len(html.encode("utf-8"))
    if octets < MIN_OCTETS_PRO:
        return False, f"{octets} octets (minimum {MIN_OCTETS_PRO})"
    return True, ""


def _nettoyer_html(html: str) -> str:
    """Retire la cloture Markdown et ne garde que le document."""
    html = re.sub(r"^```html?\n?", "", html)
    html = re.sub(r"\n?```\s*$", "", html)
    m = re.search(r"(<!DOCTYPE html.*</html>)", html, re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else html


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


def _corriger_design(html: str, cible: Path, v: dict) -> str:
    """Passe le rendu au detecteur, puis une seule passe correctrice.

    Le detecteur ne se trompe pas dans le meme sens que le modele : il rend la
    page dans un Chrome et mesure. Une seule passe, parce qu'au-dela le modele
    commence a defaire des choses justes pour satisfaire une regle qu'il a mal
    comprise. Et on ne garde la correction que si elle ameliore le compte :
    sinon on remet la premiere version.
    """
    constats, err = controle_design.analyser(cible.parent, cible.name)
    if err:
        print(f"   controle design saute ({err})")
        return html
    defauts = controle_design.echecs(constats)
    if not defauts:
        print("   design : aucun defaut")
        return html
    print(f"   design : {len(defauts)} defaut(s), passe correctrice")

    corrige, err = _appeler_modele(
        "Voici une page HTML complete. Un detecteur deterministe, qui rend la "
        "page dans un navigateur et mesure, y a releve les defauts ci-dessous. "
        "Corrige-les TOUS et ne change rien d'autre : memes sections, memes "
        "textes, memes faits, memes couleurs, meme structure.\n\n"
        f"DEFAUTS RELEVES :\n{controle_design.resume(constats)}\n\n"
        f"PAGE :\n{html}\n\n"
        "Reponds UNIQUEMENT avec le code HTML complet corrige.")
    if not corrige:
        print(f"   /!\\ passe correctrice impossible ({err})")
        return html

    corrige = _nettoyer_html(corrige)
    ok, raison = _site_est_correct(corrige)
    if not ok:
        print(f"   /!\\ version corrigee rejetee ({raison})")
        return html
    # le modele peut avoir efface le bloc d identite en reecrivant le <style>
    if not IDENTITE_FIXE and f"Identite \u00ab {v['nom']} \u00bb" not in corrige:
        corrige = _appliquer_variante(corrige, v)

    cible.write_text(corrige, encoding="utf-8")
    apres = controle_design.echecs(
        controle_design.analyser(cible.parent, cible.name)[0])
    if len(apres) < len(defauts):
        print(f"   design : {len(defauts)} -> {len(apres)} defaut(s)")
        return corrige
    print(f"   design : la correction n a pas aide ({len(apres)}), "
          f"on garde la premiere version")
    cible.write_text(html, encoding="utf-8")
    return html


def generer_site(p: dict, metier: str, force=False) -> tuple[str | None, str, dict]:
    """Retourne (url, erreur, variante)."""
    conf = METIERS[metier]
    nom = (p.get("nom") or "").strip()
    slug = pl.slugify(nom)
    v = {"nom": IDENTITE_FIXE} if IDENTITE_FIXE else variantes.pour(slug)
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
- UNE SECTION DONT LES FAITS MANQUENT DISPARAIT ENTIEREMENT. Jamais de bloc
  vide qui annonce qu'il se remplira un jour : c'est ce qui fait qu'une page
  a l'air inachevee. Pas d'avis dans les faits verifies -> pas de section
  avis, et le lien correspondant sort aussi du menu et du pied de page. Pas
  de donnee pneumatique -> pas de section pneumatique. Meme regle pour le
  balisage JSON-LD : pas de aggregateRating sans note reelle.
- LA PAGE S'ADRESSE AUX CLIENTS DU GARAGE, jamais au garagiste. Aucune phrase
  du genre « cette reputation n'est visible que sur un annuaire, pas chez
  vous » : c'est un argumentaire de vente de site web, il n'a rien a faire
  sur une page que liront des automobilistes. Ce discours-la va dans le bloc
  « bon de travail », masque derriere ?notes.
- INTERDICTION DES FORMULES PASSE-PARTOUT non presentes dans les faits :
  « toutes marques », « devis gratuit », « paiement par carte », « accessible
  aux personnes a mobilite reduite », « vehicule de pret », « sur place :
  occasions et lavage ». Le gabarit en contient parce qu'elles etaient vraies
  pour l'atelier qui a servi de modele ; elles ne le sont pas ici.
- HORAIRES. Le gabarit affiche un tableau et un indicateur « ouvert
  maintenant ». L'indicateur lit l'attribut data-h de #etat : sept entrees,
  dimanche en premier, chacune nulle (ferme) ou une suite de minutes depuis
  minuit par paires — 8h00 vaut 480, 19h00 vaut 1140. Remplis-le a partir des
  horaires verifies, et mets dans le tableau les memes horaires en toutes
  lettres. Si les horaires ne figurent pas dans les faits, retire le panneau
  « Horaires d'ouverture » et son script, et garde seulement « Venir a
  l'atelier ».
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

    html = _nettoyer_html(html)

    ok, raison = _site_est_correct(html)
    if not ok:
        return None, f"site trop pauvre — {raison}", v

    fuite = re.findall(r"\b(chiot\w*|chien\w*|port[ée]e\w*|[ée]levage\w*|LOF)\b",
                       html, re.IGNORECASE)
    if len(fuite) > 2:
        return None, f"vocabulaire canin residuel ({len(fuite)} occurrences)", v

    if not IDENTITE_FIXE:
        html = _appliquer_variante(html, v)

    cible.parent.mkdir(exist_ok=True)
    cible.write_text(html, encoding="utf-8")
    html = _corriger_design(html, cible, v)
    pl._sanitize(cible, slug, {"email": p.get("email", ""),
                               "phone": p.get("telephone", "")})
    pl._inject_tracking(cible)
    subprocess.run(["git", "-C", str(REPO_ROOT), "add", f"{slug}/index.html"],
                   capture_output=True)
    return f"{PAGES}/{slug}/", "", v


# --------------------------------------------------------------------------
# message Telegram — c'est lui qui sert a passer l'appel
# --------------------------------------------------------------------------

def canal(p: dict) -> tuple[str, str]:
    """Par ou joindre ce prospect, et avec quelle coordonnee.

    Mesure faite sur la base : 86 % des numeros sont des fixes, donc le SMS
    ne marche que pour une minorite. L'ordre est celui de la reponse
    attendue : un portable se lit tout de suite, un courriel se lit le soir,
    un fixe suppose de tomber sur quelqu'un.
    """
    tel = re.sub(r"\D", "", p.get("telephone") or "")
    if tel[:2] in ("06", "07"):
        return "sms", p["telephone"]
    mail = (p.get("email") or "").strip()
    if mail:
        return "mail", mail
    if tel:
        return "appel", p["telephone"]
    return "aucun", ""


def objet_mail(p: dict) -> str:
    """La ligne d'objet, quand le canal est le courriel."""
    ville = (p.get("commune") or "").strip()
    nom = (p.get("nom") or "").strip()
    if p.get("site_statut") == "propre":
        return f"Une autre version du site de {nom}, pour comparaison"
    return f"Un site pour {nom}" + (f", a {ville}" if ville else "")


def pitch_sms(p: dict, demo_url: str | None) -> str:
    """La version courte : un SMS se lit en entier ou pas du tout."""
    nom = (p.get("nom") or "").strip()
    debut = ("Bonjour, Francois-Frederic Lang, developpeur web a Nancy. "
             f"J'ai prepare une demo de site pour {nom}")
    fin = (", gratuite et sans engagement" if p.get("site_statut") != "propre"
           else ", juste pour comparaison avec le votre")
    q = " : " + demo_url if demo_url else ""
    return (debut + fin + q + ". Si ca ne vous interesse pas, "
            "repondez STOP et je n'insiste pas.")


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

    # En B2B la prospection par courriel se fait en opt-out, mais a trois
    # conditions : dire qui l'on est et pourquoi on ecrit, dire d'ou vient
    # l'adresse, et offrir un moyen simple de ne plus etre contacte. Les deux
    # dernieres ne sont pas dans le corps du message ci-dessus.
    if canal(p)[0] == "mail":
        parties += [
            "",
            "—",
            "Votre adresse figure dans les donnees publiques d'OpenStreetMap, "
            "ou elle est renseignee pour votre etablissement. Ce message "
            "concerne votre activite professionnelle. Repondez « STOP » et "
            "je ne vous recontacterai pas.",
        ]
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

    c, coord = canal(p)
    entetes = {
        "sms":   f"\U0001F4F2 PAR SMS au {coord}",
        "mail":  f"\u2709\uFE0F PAR COURRIEL a {coord}",
        "appel": f"\u260E\uFE0F PAR TELEPHONE au {coord} — fixe, pas de SMS",
        "aucun": "\u26A0\uFE0F AUCUNE COORDONNEE",
    }
    parties += ["", entetes[c]]

    if c == "sms":
        parties += ["", "--- SMS A ENVOYER ---", pitch_sms(p, demo_url),
                    "--- FIN DU SMS ---",
                    "", "(version longue ci-dessous si tu preferes appeler)"]
    elif c == "mail":
        parties += ["", f"Objet : {objet_mail(p)}"]

    parties += ["", "--- PITCH A ENVOYER ---", pitch(p, metier, demo_url),
                "--- FIN DU PITCH ---"]
    return "\n".join(parties)


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------

# Une panne passagere ne doit jamais consommer un prospect. Le HTTP 402
# d'OpenRouter (credit epuise) l'a montre : sans ce tri, une nuit de credit
# a zero brulait cinq fiches par execution, marquees traitees, definitivement
# sorties du vivier, sans qu'aucun site n'ait ete produit.
PASSAGERES = ("HTTP 402", "HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503",
              "HTTP 504", "HTTP 520", "HTTP 524", "Timeout", "ConnectionError",
              "ReadTimeout", "ConnectTimeout", "ChunkedEncodingError",
              "reponse vide", "echec inconnu")
# Celles-la ne s'arrangeront pas d'elles-memes : inutile d'enchainer le lot.
FATALES = ("HTTP 401", "HTTP 402", "HTTP 403", "OPENROUTER_API_KEY absente")


def _est_passagere(raison: str) -> bool:
    return any(m in (raison or "") for m in PASSAGERES)


def _est_fatale(raison: str) -> bool:
    return any(m in (raison or "") for m in FATALES)


class _SansCRM(Exception):
    """Sentinelle du mode essai : on saute la fiche CRM sans la traiter
    comme une panne."""


def run(metier: str, nombre: int, dry_run: bool, avec_site: bool = False,
        refaire: bool = False, essai: bool = False) -> None:
    conn = ouvrir()
    reste = compter(conn, metier, avec_site)

    # Le CRM est la memoire longue : une fiche peut y exister sans que la
    # base locale le sache (relance manuelle, import, autre machine).
    tel_crm = set()
    if not dry_run and not essai:
        try:
            tel_crm = {re.sub(r"\D", "", t) for t in crm.get_existing_phones()}
            print(f"{len(tel_crm)} numeros deja presents dans le CRM, ecartes")
        except Exception as e:
            print(f"/!\\ CRM injoignable ({e}) — on continue sans ce controle")
    if essai:
        print("Mode essai : le CRM n'est ni consulte ni alimente.")

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
            v = ({"nom": IDENTITE_FIXE} if IDENTITE_FIXE
                 else variantes.pour(pl.slugify(nom or "")))
            print(message(p, metier, f"{PAGES}/{pl.slugify(nom or '')}/", v))
            continue

        url, err, v = generer_site(p, metier, force=refaire)
        if err:
            print(f"   /!\\ {err}")
            if _est_passagere(err):
                # on n'ecrit pas traite_at : la fiche reste dans le vivier
                print("   panne passagere — le prospect reste a traiter")
            else:
                marquer(conn, p["cle"], erreur=err, variante=v["nom"])
            if _est_fatale(err):
                msg = (f"Arret du lot : {err}. "
                       f"Rien n'a ete consomme, {len(lot)} prospect(s) "
                       f"restent a traiter.")
                print(msg)
                if not dry_run:
                    telegram.send(f"\u26D4 {msg}")
                break
            continue

        texte = message(p, metier, url, v)
        issue = None
        try:
            if essai:
                raise _SansCRM
            issue = crm.add_entry(
                elevage=nom,
                races=[METIERS[metier]["metier"]],
                phone=p.get("telephone", ""),
                demo_url=url,
                notes=f"Site actuel: {p.get('site_web') or 'aucun'} | "
                      f"Description: {METIERS[metier]['metier']} a "
                      f"{p.get('commune','')} | Pitch: {texte}",
            )
        except _SansCRM:
            pass
        except Exception as e:
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
    p.add_argument("--refaire", action="store_true",
                   help="regenerer meme si le dossier du site existe deja")
    p.add_argument("--modele", default=None,
                   help="identifiant OpenRouter du modele, par exemple "
                        "deepseek/deepseek-chat-v3-0324:free. Sinon MODELE_PRO "
                        "dans .env, sinon deepseek/deepseek-v4-pro.")
    p.add_argument("--essai", action="store_true",
                   help="repetition : ne consulte pas le CRM et n'y ecrit pas. "
                        "Exige --db, pour ne jamais court-circuiter le "
                        "dedoublonnage sur la vraie base.")
    p.add_argument("--attendre", type=int, default=0)
    p.add_argument("--db", default=None, help="base de test au lieu de prospection.db")
    args = p.parse_args()

    if args.db:
        global DB_PATH
        DB_PATH = Path(args.db)
        print(f"base de test : {DB_PATH}")

    if args.modele:
        global MODELE
        MODELE = args.modele

    if args.essai and not args.db:
        sys.exit("--essai exige --db : sans base de test, sauter le controle "
                 "du CRM ferait re-demarcher des prospects deja contactes.")

    if args.reste:
        conn = ouvrir()
        for m in sorted(METIERS):
            print(f"  {m:10} : {compter(conn, m):5} sans site  |  "
                  f"{compter(conn, m, True):5} en incluant les refontes")
        conn.close()
        return

    try:
        with verrou(args.attendre):
            run(args.metier, args.nombre, args.dry_run, args.avec_site,
                args.refaire, args.essai)
    except DejaEnCours as e:
        print(f"Une autre execution tourne deja ({e}). Abandon.")
        sys.exit(75)


if __name__ == "__main__":
    main()
