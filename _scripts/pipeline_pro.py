#!/usr/bin/env python3
"""Circuit de prospection parallele, hors elevage canin.

Ne touche a rien du pipeline eleveurs : source differente (table `sirene`
au lieu de `annonces`), verrou different, agent launchd different, horaire
different. Les deux peuvent tourner le meme jour sans se marcher dessus.

Chaine complete d'un nouveau marche :

    1. sirene.py       qui existe, ou, quelle taille        (gratuit, sans cle)
    2. places.py       telephone, site web, note, avis      (Google Places)
    3. pipeline_pro.py site de demo + CRM + Telegram        (ce script)

Les helpers lourds (reference HTML, garde-fou qualite, anonymisation,
pixel de comptage, commit et push) sont importes de pipeline.py tels quels,
sans le modifier.

Usage :
    python3 _scripts/pipeline_pro.py --metier garage --dry-run
    python3 _scripts/pipeline_pro.py --metier garage --nombre 5
    python3 _scripts/pipeline_pro.py --metier nautique
    python3 _scripts/pipeline_pro.py --metier garage --reste
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

import config           # noqa: E402
import crm              # noqa: E402
import photos           # noqa: E402
import pipeline as pl   # noqa: E402  (reutilise ses helpers, ne le modifie pas)
import telegram         # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "annonces.db"
VERROU_PATH = REPO_ROOT / "_data" / ".pipeline_pro.lock"
CACHE_PHOTOS = REPO_ROOT / "_data" / "photos_pro.json"

PAR_DEFAUT = 5          # prospects par execution

# Tranches d'effectif INSEE gardees par defaut. Le NAF 45.20A ne contient pas
# que des ateliers de quartier : il ramene aussi MIDAS FRANCE, NORAUTO ou des
# holdings de reseau, qui ne sont pas des prospects et que le tri par nombre
# d'avis Google fait remonter en tete. On plafonne donc a 19 salaries.
#   NN/vide non renseigne (tres souvent une TPE)   11  10 a 19
#   00  0 salarie      01  1-2    02  3-5    03  6-9
# Au-dela (12 = 20-49, 21 = 50-99, 22 = 100-199...) : reseau ou groupe.
EFFECTIFS_TPE = ("", "NN", "00", "01", "02", "03", "11")

# Mots qui trahissent une personne morale dans le champ `dirigeant` : SIRENE y
# met la societe mere quand l'entreprise est detenue par une autre. Les mettre
# dans le pitch comme interlocuteur ferait demander « Monsieur Holding » au
# telephone.
MORAUX = {"holding", "sa", "sas", "sasu", "sarl", "eurl", "sci", "spa", "s.p.a",
          "groupe", "group", "ltd", "gmbh", "bv", "nv", "participations",
          "finance", "financiere", "invest", "investissements", "france"}


# --------------------------------------------------------------------------
# les marches
# --------------------------------------------------------------------------
# `naf`      : codes a collecter avec sirene.py (informatif ici, sert au filtre)
# `metier`   : comment nommer l'activite dans le site et le pitch
# `requetes` : recherches photo, du plus specifique au plus generique
# `ambiance` : consigne de direction artistique passee au modele
# `arguments`: ce que le site doit faire gagner au prospect, pour le pitch

METIERS: dict[str, dict] = {
    "garage": {
        "naf": ["45.20A", "45.20B"],
        "metier": "garage automobile independant",
        "pluriel": "garages",
        "requetes": [
            "car repair garage workshop mechanic",
            "auto repair shop interior tools",
            "mechanic working under car lift",
            "car engine maintenance close up",
        ],
        "ambiance": (
            "atelier, metal brosse, gris anthracite et une couleur d'accent "
            "franche (orange, rouge ou bleu). Serieux et technique, jamais "
            "clinquant. Typographies sans empattement, lisibles."
        ),
        "sections_metier": [
            "Prestations (revision, freinage, distribution, climatisation, "
            "diagnostic electronique, pneumatiques)",
            "Marques et vehicules pris en charge",
            "Devis gratuit et delais",
            "Vehicule de pret / vehicule de courtoisie",
            "Horaires et acces (plan)",
        ],
        "arguments": [
            "un automobiliste cherche un garage sur son telephone, au bord de la route",
            "le devis en ligne evite les appels pour rien",
            "les avis Google affiches rassurent face aux chaines",
        ],
    },
    "nautique": {
        "naf": ["33.15Z", "30.12Z"],
        "metier": "chantier naval / atelier de reparation de bateaux",
        "pluriel": "chantiers",
        "requetes": [
            "boatyard shipyard sailboat repair",
            "sailboat hull maintenance workshop",
            "marina boat lift crane",
            "wooden boat restoration craftsman",
        ],
        "ambiance": (
            "bord de mer, bleu profond, sable, bois clair. Photographie large, "
            "beaucoup de blanc, elegant et artisanal."
        ),
        "sections_metier": [
            "Services (carenage, hivernage, stratification, moteur, greement, "
            "electronique de bord)",
            "Realisations et chantiers passes",
            "Manutention et capacites (tonnage, levage, place a sec)",
            "Devis et delais",
            "Acces au port et coordonnees",
        ],
        "arguments": [
            "un refit se decide sur des photos de realisations",
            "le proprietaire compare trois chantiers avant d'appeler",
            "l'hivernage se reserve en ligne des septembre",
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
    """Verrou distinct de celui du pipeline eleveurs : les deux coexistent."""
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
    f.seek(0)
    f.truncate()
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

COLONNES = {
    "traite_at": "TEXT",
    "site_slug": "TEXT",
    "site_url": "TEXT",
    "crm_issue_url": "TEXT",
    "erreur": "TEXT",
    "metier": "TEXT",
}


def preparer(conn: sqlite3.Connection) -> None:
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "sirene" not in tables:
        sys.exit(
            "La table `sirene` n'existe pas.\n"
            "  1) python3 _scripts/sirene.py --naf 45.20A\n"
            "  2) python3 _scripts/places.py --naf 45.20A --max-appels 300"
        )
    deja = {r[1] for r in conn.execute("PRAGMA table_info(sirene)")}
    for col, typ in COLONNES.items():
        if col not in deja:
            conn.execute(f"ALTER TABLE sirene ADD COLUMN {col} {typ}")
    conn.commit()


def prospects(conn, cle_metier: str, limit: int) -> list[dict]:
    """Les prospects joignables, sans site, pas encore traites, les plus gros d'abord.

    `avis` (nombre d'avis Google) sert de proxy d'activite : un atelier a 60
    avis tourne et peut payer, un a 2 avis est souvent une coquille vide.
    """
    conf = METIERS[cle_metier]
    effectifs = conf.get("effectifs", EFFECTIFS_TPE)
    marques = ",".join("?" * len(conf["naf"]))
    tranches = ",".join("?" * len(effectifs))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(f"""
        SELECT siren, nom, enseigne, dirigeant, telephone, adresse, code_postal,
               ville, departement, note, avis, effectif, date_creation
        FROM sirene
        WHERE naf IN ({marques})
          AND traite_at IS NULL
          AND enrichi_at IS NOT NULL
          AND COALESCE(telephone,'') <> ''
          AND COALESCE(site_web,'') = ''
          AND COALESCE(confiance,'') IN ('haute','moyenne')
          AND COALESCE(statut_google,'OPERATIONAL') = 'OPERATIONAL'
          AND COALESCE(effectif,'') IN ({tranches})
        ORDER BY COALESCE(avis,0) DESC, COALESCE(note,0) DESC
        LIMIT ?
    """, [*conf["naf"], *effectifs, limit])
    return [dict(r) for r in cur]


def compter(conn, cle_metier: str) -> int:
    conf = METIERS[cle_metier]
    effectifs = conf.get("effectifs", EFFECTIFS_TPE)
    marques = ",".join("?" * len(conf["naf"]))
    tranches = ",".join("?" * len(effectifs))
    # Exactement les memes conditions que prospects(), sinon la reserve annoncee
    # est gonflee et le message "vivier vide" ne se declenche jamais.
    return conn.execute(f"""
        SELECT COUNT(*) FROM sirene
        WHERE naf IN ({marques})
          AND traite_at IS NULL
          AND enrichi_at IS NOT NULL
          AND COALESCE(telephone,'') <> ''
          AND COALESCE(site_web,'') = ''
          AND COALESCE(confiance,'') IN ('haute','moyenne')
          AND COALESCE(statut_google,'OPERATIONAL') = 'OPERATIONAL'
          AND COALESCE(effectif,'') IN ({tranches})
    """, [*conf["naf"], *effectifs]).fetchone()[0]


def marquer(conn, siren: str, *, metier: str, slug=None, url=None,
            issue=None, erreur=None) -> None:
    conn.execute(
        "UPDATE sirene SET traite_at=?, metier=?, site_slug=?, site_url=?, "
        "crm_issue_url=?, erreur=? WHERE siren=?",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), metier,
         slug, url, issue, erreur, siren),
    )
    conn.commit()


# --------------------------------------------------------------------------
# photos : une banque par metier, constituee une fois puis reutilisee
# --------------------------------------------------------------------------

def photos_metier(cle_metier: str, combien: int = 14, rafraichir=False) -> list[str]:
    conf = METIERS[cle_metier]
    cache = {}
    if CACHE_PHOTOS.exists():
        try:
            cache = json.loads(CACHE_PHOTOS.read_text(encoding="utf-8"))
        except ValueError:
            cache = {}
    if not rafraichir and len(cache.get(cle_metier, [])) >= combien:
        return cache[cle_metier][:combien]

    urls: list[str] = list(cache.get(cle_metier, []))
    for requete in conf["requetes"]:
        if len(urls) >= combien:
            break
        manque = combien - len(urls)
        trouvees = photos.search_images(requete, count=manque) or []
        for i, img in enumerate(trouvees):
            public_id = f"{cle_metier}_{len(urls) + 1}"
            cloud = photos.upload_to_cloudinary(img["url"], public_id, race=cle_metier)
            urls.append(cloud or img["url"])
            if len(urls) >= combien:
                break

    cache[cle_metier] = urls
    CACHE_PHOTOS.write_text(json.dumps(cache, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    return urls[:combien]


# --------------------------------------------------------------------------
# generation du site
# --------------------------------------------------------------------------

def charger_reference(cle_metier: str) -> str:
    """Le site modele envoye au modele, par ordre de preference.

    _templates/reference-<metier>.html  -> gabarit propre au metier
    _templates/reference.html           -> repli, le gabarit elevage

    Tant qu'un metier n'a pas son propre gabarit on retombe sur celui des
    eleveurs : ca marche, mais le modele doit desapprendre son vocabulaire,
    d'ou le garde-fou anti-vocabulaire-canin plus bas. Des qu'un marche se
    confirme, lui ecrire son reference-<metier>.html supprime le probleme
    a la source et donne des sections vraiment adaptees.
    """
    propre = REPO_ROOT / "_templates" / f"reference-{cle_metier}.html"
    if propre.exists():
        try:
            texte = propre.read_text(encoding="utf-8")
            if texte.strip():
                print(f"   gabarit : {propre.name}")
                return texte
        except OSError as e:
            print(f"   /!\\ {propre.name} illisible ({e}), repli sur reference.html")
    print("   gabarit : reference.html (elevage) — pas encore de gabarit "
          f"« {cle_metier} »")
    return pl._charger_reference()


def _cle_openrouter() -> str:
    for fp in (REPO_ROOT / ".env", Path(os.path.expanduser("~/.hermes/.env"))):
        if not fp.exists():
            continue
        for line in fp.read_text(encoding="utf-8").splitlines():
            if line.startswith(("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")) and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _appeler_modele(prompt: str) -> tuple[str, str]:
    """Retourne (html, erreur). Meme protocole que pipeline.py."""
    import requests
    cle = _cle_openrouter()
    if not cle:
        return "", "OPENROUTER_API_KEY absente"
    payload = {
        "model": "deepseek/deepseek-v4-pro",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 24000,
        "stream": True,
    }
    derniere = ""
    for tentative in (1, 2):
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {cle}",
                         "Content-Type": "application/json"},
                json=payload, timeout=(30, 900), stream=True,
            )
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


def generer_site(prospect: dict, cle_metier: str, images: list[str],
                 force=False) -> tuple[str | None, str]:
    """Retourne (url_demo, erreur)."""
    conf = METIERS[cle_metier]
    nom = (prospect.get("enseigne") or prospect.get("nom") or "").strip()
    slug = pl.slugify(nom)
    cible = REPO_ROOT / slug / "index.html"
    if cible.exists() and not force:
        return f"https://francoislang.github.io/templates/{slug}", ""

    ref = charger_reference(cle_metier)
    if not ref.strip():
        return None, "aucune reference HTML lisible"
    if not images:
        return None, "aucune photo disponible"

    ville = prospect.get("ville") or ""
    dept = prospect.get("departement") or ""
    lieu = f"a {ville} ({dept})" if ville and dept else (ville or dept or "France")
    liste_photos = "\n".join(f"  {u}" for u in images)
    sections = "\n".join(f"  - {s}" for s in conf["sections_metier"])

    prompt = f"""Cree un site vitrine HTML complet pour un {conf['metier']}.

REFERENCE (structure a reproduire exactement) :
{ref}

CONTENU :
- Nom: {nom}
- Activite: {conf['metier']}
- Tel: {prospect.get('telephone','')}
- Adresse: {prospect.get('adresse','')} {prospect.get('code_postal','')} {ville}
- Lieu: {lieu}
- SIREN: {prospect.get('siren','')}
- Photos ({len(images)} dispo):
{liste_photos}

SECTIONS METIER a couvrir, en plus de la structure de reference :
{sections}

REGLES:
- Reproduis EXACTEMENT la structure HTML, les sections et les classes de la
  reference. Elle est COMPLETE : reprends TOUTES ses sections, dans le meme
  ordre. Un site a moins de 6 sections sera rejete.
- Adapte le VOCABULAIRE au metier : il ne s'agit pas d'un elevage. Aucun mot
  lie aux animaux, aux chiots, aux portees ou aux races ne doit apparaitre.
- Hero: une des photos Cloudinary fournies.
- Galerie: utilise TOUTES les {len(images)} photos. Boucle si besoin.
- Formulaire de contact (nom, telephone, email, message) oriente demande de devis.
- Footer: (c) 2026 {nom}, {f"SIREN {prospect.get('siren')}" if prospect.get('siren') else ""}, {ville or dept or "France"}, Mentions legales, CGV, Politique de confidentialite
- Animations au defilement (IntersectionObserver)
- Schema.org JSON-LD (type LocalBusiness), Open Graph, meta SEO avec la ville
- DIRECTION ARTISTIQUE : {conf['ambiance']}

PERFORMANCE DES IMAGES (obligatoire, la reference l'applique deja) :
- Les URLs Cloudinary se terminent par .../image/upload/<chemin>. Insere
  TOUJOURS une transformation juste apres /image/upload/ :
    hero et og:image  -> f_auto,q_auto,w_1920,c_fill,g_auto
    images de section -> f_auto,q_auto,w_900,c_fill,g_auto
    vignettes galerie -> f_auto,q_auto,w_600,c_fill,g_auto
- Chaque <img> porte loading="lazy", decoding="async", width et height,
  SAUF l'image du hero.
- Dans <head> : <link rel="preconnect" href="https://res.cloudinary.com" crossorigin>
  et un <link rel="preload" as="image" fetchpriority="high"> sur le hero.
- Reponds UNIQUEMENT avec le code HTML complet."""

    html, err = _appeler_modele(prompt)
    if not html:
        return None, err

    html = re.sub(r"^```html?\n?", "", html)
    html = re.sub(r"\n?```\s*$", "", html)
    m = re.search(r"(<!DOCTYPE html.*</html>)", html, re.DOTALL | re.IGNORECASE)
    if m:
        html = m.group(1)

    ok, raison = pl._site_est_correct(html)
    if not ok:
        return None, f"site trop pauvre — {raison}"

    # Garde-fou propre a ce circuit : le modele part parfois sur le vocabulaire
    # canin parce que la reference est un site d'elevage.
    fuite = re.findall(r"\b(chiot\w*|chien\w*|port[ée]e\w*|[ée]levage\w*|LOF)\b",
                       html, re.IGNORECASE)
    if len(fuite) > 2:
        return None, f"vocabulaire canin residuel ({len(fuite)} occurrences)"

    cible.parent.mkdir(exist_ok=True)
    cible.write_text(html, encoding="utf-8")
    pl._sanitize(cible, slug, {"email": "", "phone": prospect.get("telephone", "")})
    pl._inject_tracking(cible)
    subprocess.run(["git", "-C", str(REPO_ROOT), "add", f"{slug}/index.html"],
                   capture_output=True)
    return f"https://francoislang.github.io/templates/{slug}", ""


# --------------------------------------------------------------------------
# pitch
# --------------------------------------------------------------------------

def dirigeant_physique(dirigeant: str | None, nom_societe: str = "") -> str:
    """Le dirigeant, seulement si c'est bien une personne et pas une societe mere."""
    if not dirigeant:
        return ""
    mots = re.findall(r"[\w.]+", dirigeant.lower())
    if any(m.strip(".") in MORAUX for m in mots):
        return ""
    # « GARAGE DUPONT » comme dirigeant de « GARAGE DUPONT SARL » : c'est la
    # societe elle-meme, pas quelqu'un a demander au telephone.
    if nom_societe and dirigeant.strip().lower() in nom_societe.strip().lower():
        return ""
    return dirigeant.strip()


def pitch(prospect: dict, cle_metier: str, demo_url: str | None) -> str:
    conf = METIERS[cle_metier]
    nom = prospect.get("enseigne") or prospect.get("nom") or ""
    lignes = [
        f"*{nom}*",
        f"{conf['metier'].capitalize()} — {prospect.get('ville','')} "
        f"({prospect.get('departement','')})",
        f"Tel : {prospect.get('telephone','')}",
    ]
    humain = dirigeant_physique(prospect.get("dirigeant"), nom)
    if humain:
        lignes.append(f"Interlocuteur : {humain}")
    if prospect.get("avis"):
        note = f"{prospect['note']:.1f}" if prospect.get("note") else "?"
        lignes.append(f"Google : {note}/5 sur {prospect['avis']} avis")
    if prospect.get("date_creation"):
        lignes.append(f"Cree en {str(prospect['date_creation'])[:4]}")
    lignes.append("Pas de site web reference sur Google.")
    if demo_url:
        lignes.append(f"\nDemo : {demo_url}")
    lignes.append("\nAngles d'accroche :")
    lignes += [f"- {a}" for a in conf["arguments"]]
    lignes += ["", "Francois-Frederic Lang", "langfrancoisfrederic@gmail.com",
               "06 32 81 42 00"]
    return "\n".join(lignes)


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------

def run(cle_metier: str, nombre: int, dry_run: bool) -> None:
    conf = METIERS[cle_metier]
    conn = sqlite3.connect(str(DB_PATH))
    preparer(conn)

    reste = compter(conn, cle_metier)
    lot = prospects(conn, cle_metier, nombre)
    print(f"Marche « {cle_metier} » : {len(lot)} prospect(s) ce tour, "
          f"{reste} en reserve")
    if not lot:
        msg = (f"Vivier « {cle_metier} » vide. Relancer sirene.py puis "
               f"places.py pour en collecter d'autres.")
        print(msg)
        if not dry_run:
            telegram.send(msg)
        return

    images = [] if dry_run else photos_metier(cle_metier)
    if not dry_run and not images:
        print("Aucune photo pour ce metier : on s'arrete avant de generer.")
        return

    faits = 0
    for p in lot:
        nom = p.get("enseigne") or p.get("nom")
        print(f"\n{'=' * 52}\n{nom} — {p.get('ville','')} — {p.get('telephone','')}")
        if dry_run:
            print(pitch(p, cle_metier, None))
            continue

        url, err = generer_site(p, cle_metier, images)
        if err:
            print(f"   /!\\ {err}")
            marquer(conn, p["siren"], metier=cle_metier, erreur=err)
            continue

        texte = pitch(p, cle_metier, url)
        try:
            issue = crm.add_entry(
                elevage=nom,
                races=[conf["metier"]],
                phone=p.get("telephone", ""),
                demo_url=url,
                notes=f"SIREN: {p.get('siren','')} | Site actuel: aucun | "
                      f"Description: {conf['metier']} a {p.get('ville','')} | "
                      f"Pitch: {texte}",
            )
        except Exception as e:
            issue = None
            print(f"   /!\\ CRM: {e}")

        marquer(conn, p["siren"], metier=cle_metier,
                slug=pl.slugify(nom), url=url, issue=str(issue) if issue else None)
        telegram.send(texte)
        faits += 1

    if faits and not dry_run:
        pl.commit_and_push(faits)
        telegram.send(f"{faits} site(s) « {cle_metier} » publies. "
                      f"Reserve restante : {compter(conn, cle_metier)}")
    conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--metier", required=True, choices=sorted(METIERS),
                   help="marche a prospecter")
    p.add_argument("--nombre", type=int, default=PAR_DEFAUT,
                   help=f"prospects a traiter (defaut {PAR_DEFAUT})")
    p.add_argument("--dry-run", action="store_true",
                   help="affiche les prospects et les pitchs, ne genere rien")
    p.add_argument("--reste", action="store_true",
                   help="affiche la taille du vivier et sort")
    p.add_argument("--attendre", type=int, default=0,
                   help="secondes d'attente si une autre execution tourne")
    p.add_argument("--db", default=None,
                   help="base a utiliser au lieu de _data/annonces.db "
                        "(pour essayer le circuit sans toucher la vraie base)")
    args = p.parse_args()

    if args.db:
        global DB_PATH
        DB_PATH = Path(args.db)
        print(f"base de test : {DB_PATH}")

    if args.reste:
        conn = sqlite3.connect(str(DB_PATH))
        preparer(conn)
        for cle in sorted(METIERS):
            print(f"  {cle:10} : {compter(conn, cle)} prospect(s) en reserve")
        conn.close()
        return

    try:
        with verrou(args.attendre):
            run(args.metier, args.nombre, args.dry_run)
    except DejaEnCours as e:
        print(f"Une autre execution de pipeline_pro tourne deja ({e}). Abandon.")
        sys.exit(75)


if __name__ == "__main__":
    main()
