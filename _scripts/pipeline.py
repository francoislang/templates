#!/usr/bin/env python3
"""Pipeline prospection: lit la DB `annonces`, genere sites + CRM + Telegram."""
import sys, os, re, time, json, subprocess, sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
import config, scraper, telegram, crm
from generator import generate_site
from photos import get_photos_for_race
from cloudinary_check import get_photos_for_breed

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "annonces.db"
GITHUB_REPO_SLUG = "francoislang/templates"

def slugify(text):
    """Slug sans accent — identique a generator.slugify (sinon 'Vallee Caid' -> 'vall-e-ca-d')."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _key_phone(phone):
    """Cle de regroupement par telephone (chiffres uniquement, indicatif 33 ramene a 0)."""
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("33") and len(d) == 11:
        d = "0" + d[2:]
    return d


def _key_name(name):
    """Cle de regroupement par nom, insensible aux accents, a la casse et a la ponctuation."""
    t = unicodedata.normalize("NFD", name or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def fetch_unprocessed_profiles(limit, existing_phones, existing_names, normalize):
    """Retourne jusqu'a `limit` profils non traites depuis _data/annonces.db.

    Un meme eleveur apparait plusieurs fois dans chien.com — une ligne par race.
    On regroupe donc par telephone (a defaut par nom) pour ne le contacter qu'une
    fois, en fusionnant ses races. Toutes les lignes du groupe sont renvoyees dans
    `source_urls` afin d'etre marquees ensemble.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.execute("""
        SELECT source_url, name, race, phone, email, website, siren,
               ville, code_postal, departement, description, photo_url
        FROM annonces
        WHERE processed_at IS NULL
          AND phone IS NOT NULL AND phone != ''
          AND name IS NOT NULL AND name != ''
          AND race IS NOT NULL AND race != ''
        ORDER BY scraped_at DESC
    """)

    groupes = {}
    ordre = []
    for row in cur:
        if normalize(row["phone"] or "") in existing_phones:
            continue
        if (row["name"] or "").strip().lower() in existing_names:
            continue
        cle = _key_phone(row["phone"]) or _key_name(row["name"])
        if not cle:
            continue
        if cle not in groupes:
            if len(ordre) >= limit:
                continue          # quota atteint : on ignore les nouveaux eleveurs
            groupes[cle] = {
                "source_url": row["source_url"],
                "source_urls": [row["source_url"]],
                "name": row["name"],
                "races": [],
                "phone": row["phone"] or "",
                "email": row["email"] or "",
                "website": row["website"] or "",
                "siren": row["siren"] or "",
                "ville": row["ville"] or "",
                "code_postal": row["code_postal"] or "",
                "departement": row["departement"] or "",
                "description": row["description"] or "",
                "photo_url": row["photo_url"] or "",
            }
            ordre.append(cle)
        else:
            # ligne supplementaire du meme eleveur : on complete au lieu de dupliquer
            g = groupes[cle]
            g["source_urls"].append(row["source_url"])
            for champ in ("email", "siren", "ville", "code_postal", "description", "photo_url"):
                if not g[champ] and row[champ]:
                    g[champ] = row[champ]
        if row["race"] and row["race"] not in groupes[cle]["races"]:
            groupes[cle]["races"].append(row["race"])

    conn.close()
    profils = [groupes[c] for c in ordre]
    for pr in profils:
        if not pr["races"]:
            pr["races"] = ["Inconnue"]
        if len(pr["source_urls"]) > 1:
            print(f"      (regroupe {len(pr['source_urls'])} fiches pour {pr['name']} "
                  f"— races: {', '.join(pr['races'])})")
    return profils


def mark_processed(source_url, *, site_slug=None, site_url=None,
                   crm_issue_url=None, error=None, source_urls=None):
    """Marque la (les) ligne(s) du prospect comme traitees.

    `source_urls` permet de marquer d'un coup toutes les lignes d'un meme
    eleveur (une par race). On bloque aussi, par securite, toute autre ligne
    portant le meme telephone normalise : sinon l'eleveur ressort demain.
    """
    urls = list(source_urls or [])
    if source_url and source_url not in urls:
        urls.insert(0, source_url)
    if not urls:
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        UPDATE annonces
        SET processed_at = ?, site_slug = ?, site_url = ?,
            crm_issue_url = ?, processing_error = ?
        WHERE source_url = ?
    """, (now, site_slug, site_url, crm_issue_url, error, urls[0]))
    for u in urls[1:]:
        conn.execute("""
            UPDATE annonces
            SET processed_at = ?, site_slug = ?, site_url = ?,
                crm_issue_url = ?, processing_error = ?
            WHERE source_url = ?
        """, (now, site_slug, site_url, crm_issue_url,
              "meme eleveur, autre race", u))

    # filet de securite : meme telephone, ligne encore libre
    row = conn.execute("SELECT phone FROM annonces WHERE source_url = ?", (urls[0],)).fetchone()
    if row and row[0]:
        cle = _key_phone(row[0])
        if cle:
            conn.execute("""
                UPDATE annonces
                SET processed_at = ?, processing_error = 'doublon (meme telephone)'
                WHERE processed_at IS NULL
                  AND replace(replace(replace(phone,' ',''),'.',''),'-','') = ?
            """, (now, cle))
    conn.commit()
    conn.close()


def _sanitize(path, slug, contact=None):
    """Reecrit les URLs et emails inventes par l'IA."""
    try:
        import sanitize_site
        changes = sanitize_site.process(path, apply=True, contact=contact)
        for ch in changes:
            print(f"   nettoyage: {ch}")
    except Exception as e:
        print(f"  WARNING nettoyage non applique: {e}")


def _inject_tracking(path):
    """Ajoute le snippet de tracking dans un site fraichement genere par l'IA."""
    website_id = (config.UMAMI_WEBSITE_ID or os.environ.get("UMAMI_WEBSITE_ID", "")).strip()
    if not website_id:
        return
    try:
        import set_tracking
        set_tracking.apply(path, website_id)
    except Exception as e:
        print(f"  WARNING tracking non injecte: {e}")


REFERENCE_PATH = REPO_ROOT / "_templates" / "reference.html"

# Seuils du garde-fou. Calibres sur les sites issus du template Jinja
# (8 sections, ~14 photos, ~55 ko) face aux improvisations de l'IA quand la
# reference manquait (3 a 4 sections, parfois 2 photos, 15 ko).
MIN_SECTIONS = 6
MIN_PHOTOS = 10
MIN_OCTETS = 30000


def _charger_reference() -> str:
    """Le site modele envoye a l'IA, en entier.

    Il vit dans _templates/ et non dans un dossier de site : un dossier de site
    peut etre supprime par un nettoyage du depot, ce qui etait deja arrive et
    laissait le prompt avec une reference vide.
    """
    try:
        return REFERENCE_PATH.read_text(encoding="utf-8")
    except Exception as e:
        print(f"   ⚠️  reference illisible ({REFERENCE_PATH}): {e}")
        return ""


def _site_est_correct(html: str) -> tuple[bool, str]:
    """Verifie qu'un site genere est assez riche pour etre montre a un prospect.

    Retourne (True, "") ou (False, raison lisible).
    """
    if not html or not html.strip():
        return False, "vide"
    if "</html>" not in html.lower():
        return False, "HTML incomplet (generation coupee)"

    octets = len(html.encode("utf-8"))
    sections = len(re.findall(r"<section", html, re.IGNORECASE))
    photos = len(set(re.findall(
        r"https?://[^\"'\s]+\.(?:jpe?g|png|webp|avif)", html, re.IGNORECASE)))

    if sections < MIN_SECTIONS:
        return False, f"{sections} sections (minimum {MIN_SECTIONS})"
    if photos < MIN_PHOTOS:
        return False, f"{photos} photos (minimum {MIN_PHOTOS})"
    if octets < MIN_OCTETS:
        return False, f"{octets} octets (minimum {MIN_OCTETS})"
    return True, ""


def generate_demo_site(profile, force=False):
    """Genere un site via DeepSeek V4 Pro (OpenRouter).

    force=True regenere meme si le fichier existe deja (utilise par regenerate.py).
    """
    import requests
    from pathlib import Path

    name = profile["name"]; race = profile["races"][0]
    phone = profile.get("phone",""); ville = profile.get("ville","")
    dept = profile.get("departement",""); desc = profile.get("description","") or ""
    siren = profile.get("siren",""); p_url = profile.get("photo_url","")

    slug = slugify(name)
    target = REPO_ROOT / slug / "index.html"
    if target.exists() and not force:
        return f"https://francoislang.github.io/templates/{slug}"

    photos = get_photos_for_breed(race) or get_photos_for_race(race, count=15) or []

    # Cle OpenRouter
    key = ""
    for fp in (REPO_ROOT / ".env", Path(os.path.expanduser("~/.hermes/.env"))):
        if not fp.exists():
            continue
        for line in fp.read_text(encoding="utf-8").splitlines():
            if line.startswith(("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")) and "=" in line:
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
        if key:
            break

    if not key:
        from generator import generate_site
        r = generate_site(name=name, race=race, phone=phone, city=ville or dept,
                         description=desc, siren=siren, departement=dept,
                         photo_url=p_url, photos_race=photos)
        return r[1] if r else None

    # Site de reference : _templates/reference.html, fige exactement pour cet usage.
    # Il est envoye ENTIER : tronque, le modele ne voit que le <head> et improvise
    # tout le reste, ce qui donne des sites a 4 sections au lieu de 8.
    ref = _charger_reference()

    lieu = f"a {ville} ({dept})" if ville and dept else (dept or "France")
    pl = "\n".join(f"  {p}" for p in photos)

    prompt = f"""Crée un site vitrine HTML complet pour un eleveur de chiens.

REFERENCE (structure a reproduire exactement) :
{ref}

CONTENU :
- Nom: {name}
- Race: {race}
- Tel: {phone}
- Lieu: {lieu}
- Desc: {desc[:500] if desc else ""}
- SIREN: {siren or ""}
- Photos ({len(photos)} dispo):
{pl}

REGLES:
- Reproduis EXACTEMENT la structure HTML, sections et classes du site de reference
- La reference ci-dessus est COMPLETE : reprends TOUTES ses sections, dans le meme
  ordre, sans en supprimer aucune. Un site a moins de 6 sections sera rejete.
- Hero: utilise une photo Cloudinary (JAMAIS chien.com)
- Galerie: utilise TOUTES les {len(photos)} photos fournies. Boucle si besoin.
- Formulaire contact (nom, email, message)
- Footer: © 2026 {name}, {f"SIRET {siren}" if siren else ""}, {ville or dept or "France"}, Mentions legales, CGV, Politique confidentialite
- Animations scroll (IntersectionObserver)
- Schema.org JSON-LD, Open Graph, meta SEO
- CHOISIS des couleurs QUI CORRESPONDENT A LA RACE (pas les memes que la reference)
- Police Cinzel + Raleway

PERFORMANCE DES IMAGES (obligatoire, la reference l'applique deja) :
- Les URLs Cloudinary fournies ci-dessus se terminent par .../image/upload/<chemin>.
  Insere TOUJOURS une transformation de taille juste apres /image/upload/ :
    hero et og:image  -> f_auto,q_auto,w_1920,c_fill,g_auto
    images de section -> f_auto,q_auto,w_900,c_fill,g_auto
    vignettes galerie -> f_auto,q_auto,w_600,c_fill,g_auto
  Sans cette transformation, Cloudinary sert l'original de plusieurs megaoctets.
- Chaque <img> porte loading="lazy", decoding="async" et ses attributs
  width et height, SAUF l'image du hero.
- Dans <head> : <link rel="preconnect" href="https://res.cloudinary.com" crossorigin>
  et un <link rel="preload" as="image" fetchpriority="high"> sur l'image du hero.
- Si une visionneuse agrandit les photos, la vignette porte un data-full avec
  l'URL en w_1600,c_limit et le script lit ce data-full.
- Reponds UNIQUEMENT avec le code HTML complet."""

    def _fallback(raison):
        """Repli sur le template Jinja : mieux vaut un site correct qu'aucun site."""
        print(f"   ⚠️  Repli sur le template universel ({raison})")
        from generator import generate_site
        r2 = generate_site(name=name, race=race, phone=phone, city=ville or dept,
                           description=desc, siren=siren, departement=dept,
                           photo_url=p_url, photos_race=photos)
        return r2[1] if r2 else None

    # Sans reference, le modele improvise et rend un site indigent : autant
    # passer directement par le template, dont la qualite est garantie.
    if not ref.strip():
        return _fallback(f"{REFERENCE_PATH.name} introuvable")

    payload = {
        "model": "deepseek/deepseek-v4-pro",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 24000,
        "stream": True,
    }

    html = None
    last_error = ""
    for tentative in (1, 2):
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
                timeout=(30, 900),   # 30 s pour se connecter, 15 min entre deux morceaux
                stream=True,
            )
            if r.status_code != 200:
                last_error = f"HTTP {r.status_code}"
                print(f"   ⚠️  OpenRouter {last_error} (tentative {tentative}/2)")
                continue
            # Lecture en flux : chaque morceau relance le compteur d'inactivite,
            # donc une generation longue ne declenche plus de timeout.
            # decode_unicode=True ferait confiance a l'en-tete HTTP : sans charset
            # explicite, requests retombe sur ISO-8859-1 et tous les accents
            # ressortent en double encodage. On decode nous-memes en UTF-8.
            morceaux = []
            for ligne_brute in r.iter_lines(decode_unicode=False):
                if not ligne_brute:
                    continue
                ligne = ligne_brute.decode("utf-8", "replace")
                if not ligne.startswith("data: "):
                    continue
                brut = ligne[6:]
                if brut.strip() == "[DONE]":
                    break
                try:
                    delta = json.loads(brut)["choices"][0].get("delta", {})
                except (ValueError, KeyError, IndexError):
                    continue
                if delta.get("content"):
                    morceaux.append(delta["content"])
            html = "".join(morceaux)
            if html.strip():
                break
            last_error = "reponse vide"
            print(f"   ⚠️  OpenRouter: reponse vide (tentative {tentative}/2)")
        except requests.exceptions.RequestException as e:
            last_error = type(e).__name__
            print(f"   ⚠️  OpenRouter injoignable: {last_error} (tentative {tentative}/2)")
            time.sleep(5)

    if not html or not html.strip():
        return _fallback(last_error or "echec inconnu")

    html = re.sub(r"^```html?\n?", "", html); html = re.sub(r"\n?```\s*$", "", html)
    # Ne garder que le HTML pur (enlever texte avant DOCTYPE et apres /html)
    m = re.search(r"(<!DOCTYPE html.*</html>)", html, re.DOTALL | re.IGNORECASE)
    if m: html = m.group(1)

    # Garde-fou : un site trop pauvre dessert la prospection. Mieux vaut le
    # template universel, previsible, qu'une improvisation a 4 sections.
    ok, raison = _site_est_correct(html)
    if not ok:
        return _fallback(f"site genere trop pauvre — {raison}")

    target.parent.mkdir(exist_ok=True); target.write_text(html, encoding="utf-8")
    _sanitize(target, slug, {"email": profile.get("email", ""), "phone": phone})
    _inject_tracking(target)
    subprocess.run(["git", "-C", str(REPO_ROOT), "add", f"{slug}/index.html"], capture_output=True)
    return f"https://francoislang.github.io/templates/{slug}"

def generate_pitch(profile: dict, demo_url: str | None) -> str:
    """
    Genere un pitch personnalise pour l'appel commercial.
    """
    name = profile["name"]
    race = profile["races"][0]
    phone = profile.get("phone", "")
    ville = profile.get("ville", "")
    departement = profile.get("departement", "")

    # Construction du lieu
    lieu = "en France"
    if ville and departement:
        lieu = f"à {ville} ({departement})"
    elif ville:
        lieu = f"à {ville}"
    elif departement:
        lieu = f"dans le {departement}"

    pitch_parts = [
        "Bonjour,",
        "",
        f"Je me permets de vous contacter car j'ai découvert votre élevage de {race} sur chien.com.",
        "",
        "Je suis François-Frédéric, développeur web basé à Nancy. J'ai eu envie de vous proposer quelque chose : un site vitrine moderne qui reflète vraiment la qualité de votre élevage.",
        "",
        "Un beau site, c'est concrètement :",
        "•  Une première impression qui rassure les familles avant même qu'elles vous appellent",
        "•  Moins de questions répétitives — les infos sur vos chiens, vos conditions et vos disponibilités sont accessibles à toute heure",
        "•  Un endroit où centraliser vos photos, vos témoignages et l'histoire de votre élevage",
    ]

    if demo_url:
        pitch_parts += [
            "",
            "J'ai préparé une démo gratuite, sans engagement :",
            demo_url,
            "",
            "Si elle vous plaît et que vous souhaitez en discuter, n'hésitez pas à me répondre.",
        ]
    else:
        pitch_parts += [
            "",
            "Si vous souhaitez en discuter, n'hésitez pas à me répondre.",
        ]

    pitch_parts += [
        "",
        "Bonne continuation à vous et à vos loulous,",
        "",
        "François-Frédéric Lang",
        "langfrancoisfrederic@gmail.com",
        "06 32 81 42 00",
    ]

    pitch = "\n".join(pitch_parts)

    return pitch




def get_repo_root() -> str:
    return str(config.REPO_ROOT)


def _jeton_github() -> str:
    """Lit GITHUB_TOKEN_PUSH_HERMES dans .env (il n'est pas exporte dans l'env)."""
    for fp in (REPO_ROOT / ".env", Path(os.path.expanduser("~/.hermes/.env"))):
        if not fp.exists():
            continue
        for ligne in fp.read_text(encoding="utf-8").splitlines():
            if ligne.startswith("GITHUB_TOKEN_PUSH_HERMES") and "=" in ligne:
                return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _masquer_jeton(texte: str) -> str:
    """Retire le jeton d'un message avant de l'ecrire dans un journal."""
    jeton = _jeton_github()
    if jeton and jeton in texte:
        texte = texte.replace(jeton, "***")
    return re.sub(r"(https://)[^@/\s]+@", r"\1***@", texte)


def _remote_non_interactif(repo_root) -> str:
    """URL de push qui ne declenche aucune demande d'autorisation.

    Le remote `origin` est en SSH et la cle est servie par l'agent 1Password,
    qui demande une validation a chaque usage. C'est tres bien quand Francois
    pousse a la main, mais launchd tourne a 9h sans personne devant l'ecran :
    la demande reste sans reponse et le push echoue en silence.

    On pousse donc en HTTPS avec le jeton du .env, qui ne demande rien.
    `origin` n'est pas modifie : les push manuels gardent leur validation.
    """
    jeton = _jeton_github()
    if jeton:
        return f"https://x-access-token:{jeton}@github.com/{GITHUB_REPO_SLUG}.git"
    print("  ⚠️ Git: GITHUB_TOKEN_PUSH_HERMES absent du .env, repli sur origin (SSH)")
    return "origin"


def commit_and_push(sites_count: int) -> bool:
    """Commit et push les nouveaux sites sur GitHub.

    Le push ne doit jamais attendre une validation humaine : le pipeline
    tourne sous launchd a 9h, sans session interactive.
    """
    repo_root = get_repo_root()
    remote = _remote_non_interactif(repo_root)
    subprocess.run(
        ["git", "-C", str(repo_root), "pull", "--rebase", remote, "main"],
        capture_output=True, timeout=60
    )
    try:
        # JAMAIS `git add -A` : le depot est public et le dossier de travail
        # contient des sauvegardes de la base prospects, des journaux et des
        # fichiers .bak. On ne stage que les sites generes.
        subprocess.run(
            ["git", "-C", str(repo_root), "add", "--", ":(glob)*/index.html"],
            check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(repo_root), "commit",
             "-m", f"Ajout de {sites_count} site(s) de demo via pipeline"],
            check=True, capture_output=True
        )

        # Push non interactif : voir _remote_non_interactif().
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"       # git n'attend jamais une saisie
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"

        r = subprocess.run(
            ["git", "-C", str(repo_root), "push", remote, "main"],
            check=True, capture_output=True, env=env, timeout=120
        )
        # Ne jamais laisser le jeton apparaitre dans un journal.
        sortie = _masquer_jeton((r.stderr or b"").decode("utf-8", "replace"))
        if sortie.strip():
            print(f"  git: {sortie.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        detail = e.stderr.decode("utf-8", "replace") if e.stderr else str(e)
        print(f"  ⚠️ Git: {_masquer_jeton(detail)}")
        return False
    except subprocess.TimeoutExpired:
        # Un push qui n'en finit pas, c'est une invite d'authentification
        # restee bloquee : on echoue franchement plutot que d'attendre.
        print("  ⚠️ Git: push interrompu (delai depasse)")
        return False


def run(dry_run: bool = False):
    """Execute le pipeline complet."""
    if not dry_run:
        telegram.send("🔍 Pipeline démarré — recherche d'éleveurs...")

    # 1. Recuperer les telephones et noms existants (pour dedup)
    print("📋 Recuperation des existants pour dedup...")
    existing_phones = crm.get_existing_phones() if not dry_run else set()
    existing_names = crm.get_existing_names() if not dry_run else set()

    def normalize(p):
        return p.replace(" ", "").replace("-", "").replace(".", "")

    # 2. Lire les prochains prospects non traites depuis la DB
    SITES_PER_DAY = config.SITES_PER_DAY
    print(f"🗄️  Lecture de {DB_PATH} (WHERE processed_at IS NULL)...")
    new_breeders = fetch_unprocessed_profiles(
        SITES_PER_DAY, existing_phones, existing_names, normalize
    )
    for i, b in enumerate(new_breeders, 1):
        print(f"      #{i}: {b['name']} ({b['races'][0]}) — {b['phone']}")
    print(f"   -> {len(new_breeders)} prospect(s) selectionne(s) depuis la DB")
    
    if not new_breeders:
        if not dry_run:
            telegram.send("ℹ️ Aucun nouvel éleveur (déjà tous dans le CRM).")
        return

    # 3. Traiter chaque eleveur
    results = []
    sites_created = 0

    for breeder in new_breeders:
        name = breeder["name"]
        race = breeder["races"][0]
        phone = breeder.get("phone", "")
        print(f"\n{'='*50}")
        print(f"🐕 {name} — {race}")
        print(f"📞 {phone}")

        # 3a. Generer le site demo
        if dry_run:
            print("   🏗️ [dry-run] generation du site ignoree")
            demo_url = f"https://francoislang.github.io/templates/{slugify(name)}"
        else:
            print("   🏗️ Generation du site...")
            try:
                demo_url = generate_demo_site(breeder)
            except Exception as e:
                # Un prospect qui echoue ne doit pas interrompre le lot entier.
                print(f"   ❌ Generation impossible pour {name}: {type(e).__name__}: {e}")
                mark_processed(breeder.get("source_url"), error=f"generation: {type(e).__name__}: {e}"[:300])
                continue
        has_template = demo_url is not None
        if demo_url:
            sites_created += 1
            print(f"   ✅ Site genere: {demo_url}")
        else:
            print(f"   ⚠️ Pas de template pour {race}, site non genere")

        # 3b. Generer le pitch
        print("   💬 Generation du pitch...")
        pitch = generate_pitch(breeder, demo_url)

        # 3c. Ajouter dans le CRM GitHub Issues
        issue_url = None
        crm_error = None
        if not dry_run:
            warnings = []
            if not has_template:
                warnings.append(f"pas de template pour {race}")

            notes_parts = warnings[:]
            if breeder.get("description"):
                notes_parts.append(f"Description: {breeder['description']}")
            if breeder.get("website"):
                notes_parts.append(f"Site actuel: {breeder['website']}")
            if breeder.get("email"):
                notes_parts.append(f"Email: {breeder['email']}")
            notes_parts.append(f"Pitch: {pitch}")
            notes = " | ".join(notes_parts)

            try:
                issue_number = crm.add_entry(
                    elevage=name, races=breeder["races"], phone=phone,
                    demo_url=demo_url, notes=notes
                )
                if issue_number:
                    issue_url = f"https://github.com/{GITHUB_REPO_SLUG}/issues/{issue_number}"
                    print(f"   ✅ Issue CRM: {issue_url}")
                else:
                    crm_error = "crm.add_entry returned empty issue number"
                    print(f"   ⚠️ CRM: creation d'issue echouee")
            except Exception as e:
                crm_error = f"crm.add_entry raised: {e}"
                print(f"   ⚠️ CRM: {e}")

            # 3d. Marquer le prospect comme traite dans la DB
            source_url = breeder.get("source_url")
            if source_url:
                mark_processed(
                    source_url,
                    source_urls=breeder.get("source_urls"),
                    site_slug=(slugify(name) if has_template else None),
                    site_url=demo_url,
                    crm_issue_url=issue_url,
                    error=crm_error,
                )

        results.append({
            "name": name, "race": race, "phone": phone,
            "ville": breeder.get("ville", ""),
            "departement": breeder.get("departement", ""),
            "email": breeder.get("email", ""),
            "demo_url": demo_url,
            "has_template": has_template,
            "pitch": pitch,
        })

        print(f"   💬 Pitch:\n   {pitch[:200]}...")

    # 4. Commit + push
    if sites_created > 0 and not dry_run:
        print(f"\n📤 Commit et push de {sites_created} site(s)...")
        if commit_and_push(sites_created):
            print("   ✅ Push reussi sur GitHub Pages")
        else:
            print("   ⚠️ Echec du push (peut-etre rien a commit)")

    # 5. Notification Telegram — UN message par eleveur
    print(f"\n📱 Notification Telegram...")

    sans_template = [r for r in results if not r["has_template"]]

    for r in results:
        msg_parts = [f"🐕 {r['name']} — {r['race']}"]
        msg_parts.append(f"📞 {r['phone']}")
        if r.get("email"):
            msg_parts.append(f"📧 {r['email']}")
        if r.get("ville"):
            loc = r["ville"]
            if r.get("departement"):
                loc += f" ({r['departement']})"
            msg_parts.append(f"📍 {loc}")
        if r["demo_url"]:
            msg_parts.append(f"🌐 {r['demo_url']}")
        else:
            msg_parts.append(f"⚠️ Pas de template pour {r['race']}")

        # Pitch complet, sans italique, sans troncature
        msg_parts.append("")
        msg_parts.append("--- PITCH À ENVOYER ---")
        msg_parts.append(r['pitch'])
        msg_parts.append("--- FIN DU PITCH ---")

        if dry_run:
            print(f"\nMessage pour {r['name']}:\n" + "\n".join(msg_parts))
        else:
            telegram.send("\n".join(msg_parts))

    # Resumer les resultats en un seul message
    resume = f"🐕 {len(results)} éleveurs trouvés — {sites_created} sites générés"
    if sans_template:
        resume += f"\n📋 Sans template : {', '.join(r['name'] + ' (' + r['race'] + ')' for r in sans_template)}"

    if not dry_run:
        telegram.send(resume)
    print("   ✅ Notifications envoyees")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pipeline prospection eleveurs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulation sans ecrire ni notifier")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
