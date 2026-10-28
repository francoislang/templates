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
import anonymiser          # noqa: E402
import crm                 # noqa: E402
import envoi_mail          # noqa: E402
import metiers as catalogue  # noqa: E402
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

# Meme comportement que le circuit eleveurs : quand le modele ne repond pas
# (credit epuise, panne) ou rend une page refusee, le site sort quand meme,
# rempli sans IA a partir du gabarit de reference (gabarit_fixe.py). Apres
# une premiere panne passagere, le reste du lot passe directement par le
# gabarit fixe, pour ne pas attendre deux fournisseurs en echec a chaque
# fiche. SANS_IA_PRO=1 dans .env (ou --sans-ia) force ce mode.
SANS_IA = os.environ.get("SANS_IA_PRO", "").strip() in ("1", "oui", "true")
_IA_EN_PANNE = False


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
    "menuisier": {
        "metier": "menuisier / atelier de menuiserie bois",
        "gabarit": "reference-menuisier.html",
        "cherche": "un menuisier",
        "pluriel": "menuisiers",
        "devis": "Un formulaire de devis avec le type de projet et les "
                 "dimensions, pour répondre juste sans dix allers-retours",
        "sections": [
            "Ouverture : nom, metier, appel a l'action, et le dessin "
            "technique cote (SVG) avec l'etat d'ouverture en direct",
            "Bandeau de trois faits, tires des donnees verifiees",
            "Les travaux de menuiserie, en trois familles dessinees en coupe",
            "Preparer votre demande : mesurer, photographier, decrire",
            "Horaires et acces, avec le tableau des horaires",
            "Contact : numero en grand et formulaire qui compose un SMS",
        ],
        "consignes": (
            "- SPECIALITE. La source ne dit pas si l'atelier fait de "
            "l'interieur, de l'exterieur, de l'agencement, de l'ebenisterie "
            "ou de la charpente. Garde les trois familles du gabarit, "
            "formulees au conditionnel du metier comme dans le gabarit, sauf "
            "si le NOM de l'entreprise indique clairement une specialite "
            "(« Ebenisterie », « Charpente », « Fenetres ») : dans ce cas, "
            "adapte les familles a cette specialite.\n"
            "- Garde le titre court du gabarit sur le principe (« coupe a vos "
            "cotes ») et le dessin cote sans aucune dimension chiffree.\n"
            "- Aucune mention Qualibat, RGE, decennale, garantie, essence de "
            "bois travaillee ou zone d'intervention : rien de cela n'est "
            "dans les faits.\n"
            "- FORMULAIRE. Il compose un SMS : il ne vaut que si le telephone "
            "commence par 06 ou 07. Avec un fixe et un email, il compose un "
            "mailto vers cet email. Avec un fixe et sans email, retire le "
            "formulaire et remplace-le par un encadre « Avant d'appeler » qui "
            "renvoie a « Preparer votre demande » et porte un bouton d'appel.\n"
            "- Email connu : affiche-le dans le contact, en lien mailto.\n"
            "- Sans adresse ni commune : aucune adresse inventee. Le panneau "
            "« Venir a l'atelier » dit que l'adresse se donne au telephone et "
            "propose un itineraire vers les coordonnees GPS si elles sont "
            "fournies. Le titre et le SEO citent le departement.\n"
            "- Si le nom indique la charpente, remplace la fenetre du dessin "
            "par une ferme de charpente cotee, sans chiffre."),
        "emoji": "\U0001FA9A",
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


# Le catalogue multi-metiers (metiers.py) : plombiers, coiffeurs,
# boulangeries, gites... Leur site sort du gabarit generique
# (_templates/artisan.html.j2) sans appel au modele, sauf IA_METIERS=1.
for _cle, _conf in catalogue.pour_pipeline().items():
    METIERS.setdefault(_cle, _conf)
IA_METIERS = os.environ.get("IA_METIERS", "").strip() in ("1", "oui", "true")

# « --metier tous » : rotation sur ces metiers-la (nautique n'a pas de gabarit).
ROTATION = ["garage", "menuisier", *catalogue.PAR_CLE]
METIERS_PAR_TOUR = int(os.environ.get("METIERS_PAR_TOUR") or 5)


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
                     "erreur": "TEXT", "email": "TEXT", "mail_source": "TEXT",
                     "mail_envoye_at": "TEXT", "mail_statut": "TEXT",
                     "mail_message_id": "TEXT", "mail_objet": "TEXT",
                     "mail_relance_at": "TEXT",
                     "mail_relance_statut": "TEXT"}.items():
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


# Depuis le 19/10/2026 : plus de premier contact par SMS ni par appel. Seuls
# les prospects qui ont une adresse sont pris, et ils recoivent un courriel.
# CANAL_PRO=tous dans .env pour revenir a l'ancien fonctionnement.
MAIL_SEUL = (os.environ.get("CANAL_PRO") or "mail").strip().lower() == "mail"


def _filtre(avec_site: bool) -> str:
    return f"""
      metier = ?
  AND {_FILTRE_TOUS if avec_site else _FILTRE_SANS_SITE}
  {"AND COALESCE(email,'') <> ''" if MAIL_SEUL else "AND COALESCE(telephone,'') <> ''"}
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
        "  AND COALESCE(telephone,'') NOT IN (SELECT telephone FROM prospects "
        "      WHERE traite_at IS NOT NULL AND COALESCE(telephone,'') <> '') "
        # CAST explicite : si une colonne arrive en TEXT (import CSV, autre
        # collecteur), « 8 » passerait avant « 49 » en tri alphabetique et on
        # demarcherait les plus petits garages en premier sans s'en apercevoir.
        # Un prospect joignable sans toi passe devant : courriel (envoye par
        # envoi_mail.py), puis portable, puis fixe. Sans cela le lot du jour
        # se remplit de fixes, ou il faut tomber sur quelqu'un.
        "ORDER BY (COALESCE(email,'') <> '') DESC, "
        "(substr(replace(replace(replace(telephone,' ',''),'.',''),"
        "'-','') ,1,2) IN ('06','07')) DESC, "
        "(site_statut='aucun') DESC, "
        "CAST(COALESCE(avis,0) AS INTEGER) DESC, "
        "CAST(COALESCE(note,0) AS REAL) DESC, "
        "departement, commune, nom LIMIT ?", (metier, limit * 4))

    def _cle_tel(t: str) -> str:
        return re.sub(r"\D", "", t or "")

    # En mode courriel, un prospect sans telephone est valable : la cle de
    # dedoublonnage devient alors l'adresse.
    vus = set(tel_crm or ())
    lot = []
    for r in cur:
        d = dict(r)
        t = _cle_tel(d.get("telephone"))
        m = (d.get("email") or "").strip().lower()
        if t and t in vus or (m and m in vus):
            continue
        if not t and not (MAIL_SEUL and m):
            continue
        vus.update(x for x in (t, m) if x)
        lot.append(d)
        if len(lot) >= limit:
            break
    return lot


def compter(conn, metier: str, avec_site: bool = False) -> int:
    return conn.execute(
        f"SELECT COUNT(DISTINCT COALESCE(NULLIF(telephone,''), lower(email))) FROM prospects "
        f"WHERE {_filtre(avec_site)}", (metier,)).fetchone()[0]


def mails_du_jour(conn) -> int:
    """Courriels deja deposes ou envoyes aujourd'hui (heure locale)."""
    return conn.execute(
        "SELECT COUNT(*) FROM prospects WHERE mail_envoye_at IS NOT NULL "
        "AND date(mail_envoye_at, 'localtime') = date('now', 'localtime')"
    ).fetchone()[0]


def deja_ecrit(conn, email: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM prospects WHERE lower(trim(email)) = ? "
        "AND mail_envoye_at IS NOT NULL LIMIT 1",
        ((email or "").strip().lower(),)).fetchone() is not None


def noter_mail(conn, cle: str, statut: str, message_id: str | None = None,
               objet: str | None = None) -> None:
    """Trace l'envoi sans toucher a traite_at."""
    quand = (datetime.now(timezone.utc).isoformat(timespec="seconds")
             if statut in ("brouillon", "envoye") else None)
    conn.execute("UPDATE prospects SET mail_statut=?, "
                 "mail_envoye_at=COALESCE(?, mail_envoye_at), "
                 "mail_message_id=COALESCE(?, mail_message_id), "
                 "mail_objet=COALESCE(?, mail_objet) WHERE cle=?",
                 (statut, quand, message_id, objet, cle))
    conn.commit()


def marquer(conn, cle: str, **champs) -> None:
    champs["traite_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        f"UPDATE prospects SET {','.join(c + '=?' for c in champs)} WHERE cle=?",
        [*champs.values(), cle])
    conn.commit()


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------

def _appeler_modele(prompt: str) -> tuple[str, str]:
    # DeepSeek en direct, OpenRouter en secours (voir llm.py). Les erreurs
    # gardent la forme « HTTP 402 »… attendue par PASSAGERES / FATALES.
    import llm
    return llm.generer(prompt, MODELE, max_tokens=24000)


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
    global _IA_EN_PANNE
    conf = METIERS[metier]
    nom = (p.get("nom") or "").strip()
    slug = pl.slugify(nom)
    if conf.get("generique"):
        v = {"nom": catalogue.PAR_CLE[metier].palette(slug)}
    else:
        v = {"nom": IDENTITE_FIXE} if IDENTITE_FIXE else variantes.pour(slug)
    cible = REPO_ROOT / slug / "index.html"
    if cible.exists() and not force:
        return f"{PAGES}/{slug}/", "", v

    def _repli(raison: str):
        """Site rempli sans IA, comme le template universel des eleveurs."""
        import gabarit_fixe
        print(f"   \u26a0\ufe0f  Repli sur le gabarit fixe ({raison})")
        try:
            page = gabarit_fixe.remplir(anonymiser.fiche_publique(p), metier, slug)
        except Exception as e:
            return None, f"{raison} ; repli impossible : {e}", v
        cible.parent.mkdir(exist_ok=True)
        cible.write_text(page, encoding="utf-8")
        restes = pl.neutraliser_fichier(cible, p.get("cle") or nom)
        restes += anonymiser.verifier(cible.read_text(encoding="utf-8"), p)
        if restes:
            cible.unlink()
            return None, f"{raison} ; repli refuse : " + ", ".join(restes[:3]), v
        pl._inject_tracking(cible)
        subprocess.run(["git", "-C", str(REPO_ROOT), "add", f"{slug}/index.html"],
                       capture_output=True)
        return f"{PAGES}/{slug}/", "", v

    if conf.get("generique") and not IA_METIERS:
        return _repli("gabarit generique du catalogue")
    if SANS_IA or _IA_EN_PANNE:
        return _repli("IA desactivee" if SANS_IA else "IA en panne sur ce lot")

    if conf.get("generique"):
        import gabarit_generique
        gabarit = gabarit_generique.remplir(anonymiser.fiche_publique(p), metier, slug)
    else:
        gabarit = charger_gabarit(metier)
    if not gabarit.strip():
        return _repli("aucun gabarit lisible pour le modele")

    # Le modele ne voit jamais les vraies coordonnees : il les recopierait
    # dans un attribut data-, un commentaire ou un JSON-LD reformate, ou le
    # remplacement posterieur ne va pas les chercher. Nom, commune et code
    # postal restent -- c'est ce qui fait l'interet de la demonstration.
    pub = anonymiser.fiche_publique(p)
    ville = pub.get("commune") or ""
    cp = pub.get("code_postal") or ""
    faits = [f"- Nom : {nom}", f"- Activite : {conf['metier']}",
             f"- Telephone : {pub.get('telephone','')}"]
    if pub.get("departement"):
        faits.append(f"- Departement : {pub['departement']}")
    for libelle, champ in (("Code postal", "code_postal"),
                           ("Commune", "commune"), ("Horaires", "horaires")):
        if pub.get(champ):
            faits.append(f"- {libelle} : {pub[champ]}")
    if pub.get("avis"):
        note = f"{pub['note']:.1f}" if pub.get("note") else "?"
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
{conf.get('consignes', '')}
- LA PAGE S'ADRESSE AUX CLIENTS DE L'ENTREPRISE, jamais a son patron. Aucune phrase
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
- Adapte le vocabulaire au metier.{'' if conf.get('animaux') else ' Aucun mot lie aux animaux, aux chiots, aux portees ou aux races.'}
- Telephone cliquable (tel:), formulaire de devis, JSON-LD, meta SEO avec la
  commune, mobile d'abord, contrastes au minimum 4,5:1.
- NE CHANGE PAS les couleurs ni la police du gabarit : une identite visuelle
  est appliquee automatiquement apres generation.
- AUCUNE COORDONNEE AUTRE QUE CELLES CI-DESSUS. Pas d'adresse de rue, pas
  de courriel, pas de numero SIREN, pas de coordonnees GPS au dix-millieme :
  ces informations ne sont pas dans les faits, donc elles n'existent pas.
  N'invente pas non plus d'adresse plausible pour remplir un bloc contact :
  la commune et le code postal suffisent.
- Reponds UNIQUEMENT avec le code HTML complet."""

    html, err = _appeler_modele(prompt)
    if not html:
        if _est_passagere(err) or _est_fatale(err):
            _IA_EN_PANNE = True
        return _repli(err or "reponse vide")

    html = _nettoyer_html(html)

    ok, raison = _site_est_correct(html)
    if not ok:
        return _repli(f"site trop pauvre — {raison}")

    fuite = re.findall(r"\b(chiot\w*|chien\w*|port[ée]e\w*|[ée]levage\w*|LOF)\b",
                       html, re.IGNORECASE)
    if len(fuite) > 2 and not conf.get("animaux"):
        return _repli(f"vocabulaire canin residuel ({len(fuite)} occurrences)")

    if not IDENTITE_FIXE:
        html = _appliquer_variante(html, v)

    # Garde-fou : on relit la page finie et on refuse de publier s'il reste
    # une coordonnee reelle. Ceinture et bretelles -- le modele n'a pas vu
    # ces valeurs, mais une regression de prompt ne doit pas se traduire par
    # une fuite en ligne.
    restes = anonymiser.verifier(html, p)
    if restes:
        return _repli("donnees reelles dans la page : " + ", ".join(restes))

    cible.parent.mkdir(exist_ok=True)
    cible.write_text(html, encoding="utf-8")
    html = _corriger_design(html, cible, v)
    # _sanitize remplace les courriels inventes par celui du contact : on lui
    # donne la fiche publique, sinon il reinjecte la vraie adresse.
    pl._sanitize(cible, slug, {"email": pub.get("email", ""),
                               "phone": pub.get("telephone", "")})
    # Derniere passe : la correction de design repasse par le modele, qui
    # peut inventer un numero ou un courriel. Rien de joignable ne sort.
    restes = pl.neutraliser_fichier(cible, p.get("cle") or nom)
    if restes:
        cible.unlink()
        return _repli("coordonnees non fictives dans la page : " + ", ".join(restes[:3]))
    pl._inject_tracking(cible)
    subprocess.run(["git", "-C", str(REPO_ROOT), "add", f"{slug}/index.html"],
                   capture_output=True)
    return f"{PAGES}/{slug}/", "", v


# --------------------------------------------------------------------------
# message Telegram — c'est lui qui sert a passer l'appel
# --------------------------------------------------------------------------

def canal(p: dict) -> tuple[str, str]:
    """Par ou joindre ce prospect, et avec quelle coordonnee.

    Le courriel passe en premier : il part depuis le compte Workspace
    (envoi_mail.py) sans que tu aies a recopier quoi que ce soit. Le SMS reste
    pour les portables sans adresse, l'appel pour les fixes.
    """
    tel = re.sub(r"\D", "", p.get("telephone") or "")
    mail = (p.get("email") or "").strip()
    if mail:
        return "mail", mail
    if tel[:2] in ("06", "07"):
        return "sms", p["telephone"]
    if tel:
        return "appel", p["telephone"]
    return "aucun", ""


def objet_mail(p: dict) -> str:
    """La ligne d'objet, quand le canal est le courriel."""
    ville = (p.get("commune") or "").strip()
    nom = (p.get("nom") or "").strip()
    if p.get("site_statut") == "propre" and p.get("site_web"):
        return f"Une autre version du site de {nom}"
    return f"Le site préparé pour {nom}"


def _origine_adresse(p: dict) -> str:
    """D'ou vient l'adresse : la CNIL demande de le dire."""
    src = (p.get("mail_source") or "").strip()
    if p.get("mail_cherche_at") and (src == "accueil" or src.startswith("/")):
        site = (p.get("site_web") or "").strip()
        return ("Votre adresse est affichée sur votre site"
                + (f" ({site})." if site else "."))
    return ("Votre adresse figure dans les données publiques d'OpenStreetMap, "
            "où elle est renseignée pour votre établissement.")


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


def _constat(p: dict) -> str:
    """La phrase qui dit pourquoi on ecrit a CE prospect (faits constates)."""
    nom = (p.get("nom") or "").strip()
    avis = p.get("avis")
    note = f"{p['note']:.1f}".replace(".", ",") if p.get("note") else ""
    if p.get("site_statut") == "propre" and p.get("site_web"):
        return (f"{nom} a déjà un site. J'en ai imaginé une version plus "
                "récente, pour comparer :")
    if avis and note and int(avis) >= 10:
        return (f"{nom} a {avis} avis Google ({note}/5), mais pas encore de site "
                "pour les mettre en avant. Voici une démo préparée avec les "
                "informations publiques de votre activité :")
    if (p.get("facebook") or "").strip():
        return (f"{nom} a une page Facebook, mais pas encore de site pour être "
                "trouvé sur Google. Voici une démo préparée avec les "
                "informations publiques de votre activité :")
    return (f"Je n'ai pas trouvé de site pour {nom}. Voici une démo préparée "
            "avec les informations publiques de votre activité :")


def pitch_mail(p: dict, metier: str, demo_url: str | None) -> str:
    """Le courriel (version validee le 28/10/2026) : qui je suis, le constat,
    la demo, ce que je propose, une reponse en un mot. Pas de prix, pas de
    mention STOP ; la signature Kerr est ajoutee par envoi_mail."""
    parties = ["Bonjour,", "",
               "Je suis François Lang, développeur web près de Nancy.", "",
               _constat(p)]
    if demo_url:
        parties.append(demo_url)
    parties += ["",
                "Si elle vous plaît, je la finalise avec vos photos et vos "
                "textes, et je m'occupe de la mise en ligne.",
                "",
                "Ça vous intéresse ? Répondez « oui » et dites-moi quand vous "
                "appeler. Un « non merci » suffit, et je ne vous écris plus.",
                "", *envoi_mail.signature()]
    return "\n".join(parties)


def pitch(p: dict, metier: str, demo_url: str | None) -> str:
    """Le message a envoyer au garagiste, pret a copier-coller.

    Meme registre que le pitch eleveurs : on s'adresse a la personne, on dit
    d'ou on vient, ce qu'on propose et pourquoi, on donne la demo. Les
    arguments sont personnalises avec les faits reellement constates sur ce
    garage — jamais avec des generalites, et jamais avec un fait invente.
    """
    if canal(p)[0] == "mail":
        return pitch_mail(p, metier, demo_url)
    nom = (p.get("nom") or "").strip()
    ville = (p.get("commune") or "").strip()
    dept = (p.get("departement") or "").strip()
    lieu = f"à {ville}" if ville else "dans votre secteur"
    qui = METIERS[metier].get("cherche", "un garage")
    pluriel = METIERS[metier].get("pluriel", "garages")

    avis = p.get("avis")
    note = f"{p['note']:.1f}".replace(".", ",") if p.get("note") else ""
    a_facebook = bool((p.get("facebook") or "").strip())
    a_mail = bool((p.get("email") or "").strip())

    a_un_site = (p.get("site_statut") == "propre") and bool(p.get("site_web"))

    # Ouverture : on dit comment on l'a trouve, ce qui rend l'approche concrete.
    if a_un_site:
        # On ne juge PAS son site : on ne l'a pas regarde. On propose une
        # comparaison, ce qui est honnete et se refuse moins facilement.
        ouverture = (f"Je me permets de vous contacter car j'ai cherché {qui} "
                     f"{lieu} et je suis tombé sur votre site, {p['site_web']}.")
    elif avis and note and int(avis) >= 10:
        ouverture = (f"Je me permets de vous contacter car j'ai cherché {qui} "
                     f"{lieu} et je suis tombé sur le vôtre : {avis} avis à "
                     f"{note}/5, et pourtant aucun site à vous.")
    elif a_facebook:
        ouverture = (f"Je me permets de vous contacter car j'ai cherché {qui} "
                     f"{lieu} et je n'ai trouvé de vous qu'une page Facebook.")
    else:
        ouverture = (f"Je me permets de vous contacter car j'ai cherché {qui} "
                     f"{lieu} et je n'ai trouvé votre établissement que sur des "
                     f"annuaires.")

    # Avantages : les deux premiers dependent de sa situation reelle.
    avantages = []
    if a_un_site:
        avantages.append("Une page qui se lit correctement sur un téléphone, "
                         "là où se font aujourd'hui la plupart des recherches "
                         f"d'artisans")
    elif avis and note and int(avis) >= 10:
        avantages.append(f"Vos {avis} avis affichés chez vous, et plus seulement "
                         f"sur un annuaire qui vous met en concurrence avec "
                         f"trois autres {pluriel} sur la même page")
    else:
        avantages.append("Une adresse à vous quand on cherche votre nom, plutôt "
                         "qu'une fiche d'annuaire que vous ne contrôlez pas")
    if not a_mail:
        avantages.append("Un formulaire de devis qui arrive même quand l'atelier "
                         "est fermé, au lieu d'un téléphone qui sonne dans le vide")
    else:
        avantages.append(METIERS[metier].get(
            "devis", "Un formulaire de devis avec la plaque et le modèle, "
                     "pour répondre juste sans dix allers-retours"))
    avantages += [
        "Vos horaires, votre adresse et vos prestations trouvables en une "
        "recherche, depuis un téléphone" + (", au bord de la route"
        if metier == "garage" else ""),
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
    ]
    # La liste d'avantages sert d'argumentaire a l'appel ; dans un courriel,
    # elle alourdit le message : retiree a la demande de Francois (18/10).
    if canal(p)[0] != "mail":
        parties += ["", ("Ce que la version que j'ai préparée apporte :"
                         if a_un_site else "Un site à vous, c'est concrètement :")]
        parties += [f"\u2022  {a}" for a in avantages]

    if demo_url:
        parties += ["", "J'ai préparé une démo gratuite, sans engagement :",
                    demo_url, "",
                    "Si elle vous plaît et que vous souhaitez en discuter, "
                    "n'hésitez pas à me répondre."]
    else:
        parties += ["", "Si vous souhaitez en discuter, n'hésitez pas à me répondre."]

    parties += ["", "Bien cordialement,", "", *envoi_mail.signature()]

    # En B2B la prospection par courriel se fait en opt-out, mais a trois
    # conditions : dire qui l'on est et pourquoi on ecrit, dire d'ou vient
    # l'adresse, et offrir un moyen simple de ne plus etre contacte. Les deux
    # dernieres ne sont pas dans le corps du message ci-dessus.
    # Mention d'origine et de desinscription retiree du corps a la demande de
    # Francois (18/10). La desinscription reste offerte par l'en-tete
    # List-Unsubscribe (lien « Se desabonner » de Gmail), cf. envoi_mail.py.
    return "\n".join(parties)


def message(p: dict, metier: str, demo_url: str | None, v: dict) -> str:
    """Le message Telegram : l'entete pour toi, le pitch a transferer."""
    nom = (p.get("nom") or "").strip()
    em = METIERS[metier].get("emoji", "\U0001F527")
    parties = [f"{em} {nom} — {METIERS[metier]['metier']}"]
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
        "mail":  f"\u2709\uFE0F PAR COURRIEL a {coord}"
                 + (" — envoi automatique" if envoi_mail.MODE == "envoi"
                    and envoi_mail.actif() else
                    " — brouillon dans Gmail" if envoi_mail.actif() else ""),
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
    mails_crm = set()
    crm_ok = False         # sans le CRM, aucun courriel ne part
    if not dry_run and not essai:
        try:
            tel_crm = {re.sub(r"\D", "", t) for t in crm.get_existing_phones()}
            print(f"{len(tel_crm)} numeros deja presents dans le CRM, ecartes")
            mails_crm = crm.get_existing_emails()
            print(f"{len(mails_crm)} adresses deja presentes dans le CRM")
            crm_ok = True
        except Exception as e:
            print(f"/!\\ CRM injoignable ({e}) — on continue sans ce controle, "
                  "et sans courriel")
    if essai:
        print("Mode essai : le CRM n'est ni consulte ni alimente.")

    if MAIL_SEUL and not dry_run:
        if not envoi_mail.actif():
            msg = ("\u23F8\uFE0F Prospection « " + metier + " » en pause : le premier "
                   "contact se fait desormais par courriel, et MAIL_ADRESSE / "
                   "MAIL_MOT_DE_PASSE ne sont pas renseignes dans le .env "
                   "(ou MAIL_MODE=off).")
            print(msg)
            telegram.send(msg)
            return
        if not essai and not crm_ok:
            msg = (f"\u26A0\uFE0F CRM injoignable : prospection « {metier} » "
                   "sautee ce tour-ci, pour ne recontacter personne.")
            print(msg)
            telegram.send(msg)
            return
        place = envoi_mail.PAR_JOUR - mails_du_jour(conn)
        if place <= 0:
            print(f"Plafond de {envoi_mail.PAR_JOUR} courriels/jour deja atteint.")
            return
        nombre = min(nombre, place)

    lot = a_traiter(conn, metier, nombre * 3, tel_crm, avec_site)
    if MAIL_SEUL and not dry_run and not essai:
        # On ecarte AVANT de generer : inutile de produire un site pour
        # quelqu'un qu'on ne contactera pas.
        tels_vus, mails_vus = contacts_anterieurs(conn, set(), tel_crm, mails_crm)
        avant = len(lot)
        lot = [p for p in lot
               if (p.get("email") or "").strip().lower() not in mails_vus
               and _tel(p.get("telephone")) not in tels_vus
               and (p.get("email") or "").strip().lower()
               not in envoi_mail.desinscrits()]
        if avant - len(lot):
            print(f"{avant - len(lot)} prospect(s) deja contacte(s) ecarte(s)")
    lot = lot[:nombre]
    print(f"Marche « {metier} » : {len(lot)} prospect(s) ce tour, {reste} en reserve")

    if not lot:
        msg = (f"Vivier « {metier} » vide. Relancer collecte_osm.py sur "
               f"d'autres departements.")
        print(msg)
        if not dry_run:
            telegram.send(msg)
        return

    faits = 0
    a_ecrire = []          # (prospect, url) : courriels a deposer apres le push
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
        if not (MAIL_SEUL and canal(p)[0] == "mail"):
            telegram.send(texte)
        print(f"   -> {url}  ({v['nom']})")
        faits += 1
        if canal(p)[0] == "mail" and not essai:
            a_ecrire.append((p, url))

    if faits and not dry_run:
        pl.commit_and_push(faits)
        telegram.send(f"{faits} site(s) « {metier} » publies. "
                      f"Reserve restante : {compter(conn, metier, avec_site)}")
    if a_ecrire and not dry_run:
        if crm_ok:
            ecrire(conn, metier, a_ecrire, tel_crm, mails_crm)
        else:
            telegram.send("\u26A0\uFE0F CRM injoignable : aucun courriel depose "
                          "ce tour-ci, pour ne recontacter personne. Pitchs sur "
                          "Telegram.")
    conn.close()


def _en_ligne(url: str, attente_max: int = 300) -> bool:
    """GitHub Pages met une a deux minutes a publier : on n'envoie pas un
    lien qui repond encore 404."""
    import requests
    debut = time.monotonic()
    while time.monotonic() - debut < attente_max:
        try:
            if requests.get(url, timeout=15).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(20)
    return False


def _tel(t: str | None) -> str:
    """Numero ramene a 10 chiffres : 0612345678, que la source ecrive
    +33 6 12..., 06.12... ou 0033..."""
    d = re.sub(r"\D", "", t or "")
    if d.startswith("0033"):
        d = "0" + d[4:]
    elif d.startswith("33") and len(d) == 11:
        d = "0" + d[2:]
    return d


DEJA_CONTACTES = REPO_ROOT / "_data" / "deja_contactes.txt"


def contacts_anterieurs(conn, cles_du_lot: set[str], tel_crm: set[str],
                        mails_crm: set[str]) -> tuple[set[str], set[str]]:
    """Tous les numeros et adresses deja demarches, par n'importe quel canal.

    Sources :
      - prospection.db : toute fiche deja traitee lors d'un tour precedent
        (SMS, appel, courriel) — les fiches du lot en cours sont exclues,
        puisqu'elles viennent d'etre marquees ;
      - annonces.db : les eleveurs du pipeline principal deja traites ;
      - le CRM GitHub : numeros et adresses lus en debut de tour, AVANT
        l'ajout des fiches du jour ;
      - _data/deja_contactes.txt : ceux contactes a la main, hors outils
        (une adresse ou un numero par ligne).
    """
    tels = {_tel(t) for t in tel_crm}
    mails = {m.lower() for m in mails_crm}

    marques = ",".join("?" * len(cles_du_lot)) or "''"
    for tel, mail in conn.execute(
            f"SELECT telephone, email FROM prospects WHERE traite_at IS NOT NULL "
            f"AND cle NOT IN ({marques})", list(cles_du_lot)):
        tels.add(_tel(tel))
        mails.add((mail or "").strip().lower())

    annonces = REPO_ROOT / "_data" / "annonces.db"
    if annonces.exists():
        a = sqlite3.connect(f"file:{annonces}?mode=ro", uri=True)
        try:
            for tel, mail in a.execute(
                    "SELECT phone, email FROM annonces "
                    "WHERE processed_at IS NOT NULL OR crm_issue_url IS NOT NULL"):
                tels.add(_tel(tel))
                mails.add((mail or "").strip().lower())
        finally:
            a.close()

    if DEJA_CONTACTES.exists():
        for l in DEJA_CONTACTES.read_text(encoding="utf-8").splitlines():
            l = l.strip()
            if not l or l.startswith("#"):
                continue
            if "@" in l:
                mails.add(l.lower())
            else:
                tels.add(_tel(l))

    tels.discard("")
    mails.discard("")
    return tels, mails


def ecrire(conn, metier: str, a_ecrire: list[tuple[dict, str]],
           tel_crm: set[str], mails_crm: set[str]) -> None:
    """Depose (ou envoie) les courriels du lot, dans la limite du jour.

    Personne qui a deja ete demarche -- par SMS, par appel, par courriel,
    par l'un ou l'autre pipeline, ou a la main -- ne recoit de courriel.
    """
    if not envoi_mail.actif():
        print("Courriels : MAIL_MODE=off ou identifiants absents, pitch "
              "laisse sur Telegram.")
        return
    tels_vus, mails_vus = contacts_anterieurs(
        conn, {p["cle"] for p, _ in a_ecrire}, tel_crm, mails_crm)
    bilan = {"brouillon": 0, "envoye": 0, "ignore": 0, "erreur": 0}
    for p, url in a_ecrire:
        nom = p.get("nom") or ""
        dest = (p.get("email") or "").strip()
        if mails_du_jour(conn) >= envoi_mail.PAR_JOUR:
            print(f"   plafond de {envoi_mail.PAR_JOUR}/jour atteint — {nom} "
                  "reste sur Telegram")
            noter_mail(conn, p["cle"], "plafond")
            bilan["ignore"] += 1
            continue
        if (deja_ecrit(conn, dest) or dest.lower() in mails_vus
                or _tel(p.get("telephone")) in tels_vus):
            print(f"   {nom} <{dest}> deja contacte (SMS, appel ou courriel) "
                  "— aucun courriel")
            noter_mail(conn, p["cle"], "deja_contacte")
            bilan["ignore"] += 1
            continue
        if envoi_mail.MODE == "envoi" and url and not _en_ligne(url):
            print(f"   {url} toujours hors ligne — {nom} passe en brouillon")
            mode = "brouillon"
        else:
            mode = None
        try:
            statut, mid = envoi_mail.expedier(dest, objet_mail(p),
                                              pitch(p, metier, url), mode)
        except Exception as e:
            print(f"   /!\\ courriel {nom} : {e}")
            noter_mail(conn, p["cle"], f"erreur: {e}"[:200])
            bilan["erreur"] += 1
            continue
        noter_mail(conn, p["cle"], statut, mid, objet_mail(p))
        mails_vus.add(dest.lower())
        tels_vus.add(_tel(p.get("telephone")))
        bilan[statut] += 1
        print(f"   \u2709 {nom} <{dest}> : {statut}")

    morceaux = []
    if bilan["envoye"]:
        morceaux.append(f"{bilan['envoye']} envoye(s)")
    if bilan["brouillon"]:
        morceaux.append(f"{bilan['brouillon']} en brouillon dans Gmail, a relire")
    if bilan["ignore"]:
        morceaux.append(f"{bilan['ignore']} ignore(s) (deja contacte ou plafond)")
    if bilan["erreur"]:
        morceaux.append(f"{bilan['erreur']} en erreur")
    if morceaux:
        telegram.send("\u2709\uFE0F Courriels « " + metier + " » : "
                      + ", ".join(morceaux))


def ordre_rotation(conn, avec_site: bool) -> list[str]:
    """Les metiers qui ont des prospects, le moins recemment servi d'abord.

    Un metier jamais servi passe avant tous les autres ; a egalite, celui qui
    a le plus gros vivier. Ainsi chaque jour touche des metiers differents,
    et on apprend vite lesquels repondent.
    """
    dernier = dict(conn.execute(
        "SELECT metier, MAX(traite_at) FROM prospects WHERE traite_at IS NOT NULL "
        "GROUP BY 1").fetchall())
    candidats = [(m, compter(conn, m, avec_site)) for m in ROTATION if m in METIERS]
    candidats = [(m, n) for m, n in candidats if n > 0]
    candidats.sort(key=lambda mn: (dernier.get(mn[0]) or "", -mn[1]))
    return [m for m, _ in candidats]


def rotation(nombre: int, dry_run: bool, avec_site: bool, refaire: bool,
             essai: bool) -> None:
    """Repartit `nombre` prospects sur METIERS_PAR_TOUR metiers."""
    conn = ouvrir()
    ordre = ordre_rotation(conn, avec_site)
    conn.close()
    if not ordre:
        print("Aucun prospect dans aucun metier. Lance collecte_multi.py.")
        return
    k = max(1, min(METIERS_PAR_TOUR, len(ordre), nombre))
    parts = [nombre // k + (1 if i < nombre % k else 0) for i in range(k)]
    print(f"Rotation : {', '.join(f'{m} ({n})' for m, n in zip(ordre, parts))}")
    for m, n in zip(ordre, parts):
        if n <= 0:
            continue
        print(f"\n########## {m} ##########")
        run(m, n, dry_run, avec_site, refaire, essai)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--metier", default="garage", choices=["tous", *sorted(METIERS)],
                   help="« tous » : rotation sur garage, menuisier et les "
                        f"{len(catalogue.CATALOGUE)} metiers de metiers.py "
                        "(METIERS_PAR_TOUR metiers par passage)")
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
    p.add_argument("--sans-ia", action="store_true",
                   help="ne pas appeler le modele : sites remplis depuis le gabarit "
                        "de reference (gabarit_fixe.py), comme le template universel "
                        "des eleveurs")
    p.add_argument("--db", default=None, help="base de test au lieu de prospection.db")
    args = p.parse_args()

    if args.db:
        global DB_PATH
        DB_PATH = Path(args.db)
        print(f"base de test : {DB_PATH}")

    if args.modele:
        global MODELE
        MODELE = args.modele

    if args.sans_ia:
        global SANS_IA
        SANS_IA = True

    if args.essai and not args.db:
        sys.exit("--essai exige --db : sans base de test, sauter le controle "
                 "du CRM ferait re-demarcher des prospects deja contactes.")

    if args.reste:
        conn = ouvrir()
        total = 0
        for m in sorted(METIERS, key=lambda x: -compter(conn, x, True)):
            a, b = compter(conn, m), compter(conn, m, True)
            total += b
            if b:
                print(f"  {m:18} : {a:5} sans site  |  {b:5} en incluant les refontes")
        print(f"  {'TOTAL':18}   {total:5} prospects joignables "
              f"({'courriel' if MAIL_SEUL else 'tous canaux'})")
        conn.close()
        return

    try:
        with verrou(args.attendre):
            if args.metier == "tous":
                rotation(args.nombre, args.dry_run, args.avec_site,
                         args.refaire, args.essai)
            else:
                run(args.metier, args.nombre, args.dry_run, args.avec_site,
                    args.refaire, args.essai)
    except DejaEnCours as e:
        print(f"Une autre execution tourne deja ({e}). Abandon.")
        sys.exit(75)


if __name__ == "__main__":
    main()
