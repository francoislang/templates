#!/usr/bin/env python3
"""Pipeline prospection: lit la DB `annonces`, genere sites + CRM + Telegram."""
import sys, os, re, time, json, subprocess, sqlite3
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
    import unicodedata
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def fetch_unprocessed_profiles(limit, existing_phones, existing_names, normalize):
    """Retourne jusqu'a `limit` profils non traites depuis _data/annonces.db.

    Applique la meme dedup que l'ancien scraper (par telephone normalise + nom d'elevage)
    pour rester safe si processed_at n'a pas encore ete backfille.
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
    profiles = []
    for row in cur:
        if len(profiles) >= limit:
            break
        if normalize(row["phone"] or "") in existing_phones:
            continue
        if (row["name"] or "").strip().lower() in existing_names:
            continue
        profiles.append({
            "source_url": row["source_url"],
            "name": row["name"],
            "races": [row["race"]] if row["race"] else ["Inconnue"],
            "phone": row["phone"] or "",
            "email": row["email"] or "",
            "website": row["website"] or "",
            "siren": row["siren"] or "",
            "ville": row["ville"] or "",
            "code_postal": row["code_postal"] or "",
            "departement": row["departement"] or "",
            "description": row["description"] or "",
            "photo_url": row["photo_url"] or "",
        })
    conn.close()
    return profiles


def mark_processed(source_url, *, site_slug=None, site_url=None,
                   crm_issue_url=None, error=None):
    """UPDATE la row annonces: processed_at + site_slug + site_url + crm_issue_url + processing_error."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        UPDATE annonces
        SET processed_at = ?, site_slug = ?, site_url = ?,
            crm_issue_url = ?, processing_error = ?
        WHERE source_url = ?
    """, (
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        site_slug, site_url, crm_issue_url, error, source_url,
    ))
    conn.commit()
    conn.close()

def _sanitize(path, slug):
    """Reecrit les URLs inventees par l'IA (canonical, og:url, liens sortants)."""
    try:
        import sanitize_site
        changes = sanitize_site.process(path, apply=True)
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


def generate_demo_site(profile):
    """Genere un site via DeepSeek V4 Pro (OpenRouter)."""
    import requests
    from pathlib import Path

    name = profile["name"]; race = profile["races"][0]
    phone = profile.get("phone",""); ville = profile.get("ville","")
    dept = profile.get("departement",""); desc = profile.get("description","") or ""
    siren = profile.get("siren",""); p_url = profile.get("photo_url","")

    slug = slugify(name)
    target = REPO_ROOT / slug / "index.html"
    if target.exists():
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

    # Reference joyaux-d-anubis
    ref = ""
    try:
        ref = (REPO_ROOT / "joyaux-d-anubis" / "index.html").read_text(encoding="utf-8")[:4000]
    except Exception:
        pass

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
- Hero: utilise une photo Cloudinary (JAMAIS chien.com)
- Galerie: utilise TOUTES les {len(photos)} photos fournies. Boucle si besoin.
- Formulaire contact (nom, email, message)
- Footer: © 2026 {name}, {f"SIRET {siren}" if siren else ""}, {ville or dept or "France"}, Mentions legales, CGV, Politique confidentialite
- Animations scroll (IntersectionObserver)
- Schema.org JSON-LD, Open Graph, meta SEO
- CHOISIS des couleurs QUI CORRESPONDENT A LA RACE (pas les memes que la reference)
- Police Cinzel + Raleway
- Reponds UNIQUEMENT avec le code HTML complet."""

    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": "deepseek/deepseek-v4-pro", "messages": [{"role":"user","content":prompt}], "max_tokens": 24000},
        timeout=300)

    data = r.json()
    if "choices" not in data:
        print(f"  WARNING: {data.get('error',{}).get('message','?')[:100]}")
        from generator import generate_site
        r2 = generate_site(name=name, race=race, phone=phone, city=ville or dept,
                          description=desc, siren=siren, departement=dept,
                          photo_url=p_url, photos_race=photos)
        return r2[1] if r2 else None

    html = data["choices"][0]["message"]["content"]
    html = re.sub(r"^```html?\n?", "", html); html = re.sub(r"\n?```\s*$", "", html)
    # Ne garder que le HTML pur (enlever texte avant DOCTYPE et apres /html)
    m = re.search(r"(<!DOCTYPE html.*</html>)", html, re.DOTALL | re.IGNORECASE)
    if m: html = m.group(1)
    target.parent.mkdir(exist_ok=True); target.write_text(html, encoding="utf-8")
    _sanitize(target, slug)
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

def commit_and_push(sites_count: int) -> bool:
    """Commit et push les nouveaux sites sur GitHub."""
    repo_root = get_repo_root()
    subprocess.run(
        ["git", "-C", str(repo_root), "pull", "--rebase", "origin", "main"],
        capture_output=True, timeout=30
    )
    try:
        subprocess.run(
            ["git", "-C", str(repo_root), "add", "-A"],
            check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(repo_root), "commit",
             "-m", f"Ajout de {sites_count} site(s) de demo via pipeline"],
            check=True, capture_output=True
        )

        # Utiliser le token GitHub si present
        env = os.environ.copy()
        gh_token = os.environ.get("GITHUB_TOKEN_PUSH_HERMES")

        subprocess.run(
            ["git", "-C", str(repo_root), "push", "origin", "main"],
            check=True, capture_output=True, env=env
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ⚠️ Git: {e.stderr.decode() if e.stderr else e}")
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
            demo_url = generate_demo_site(breeder)
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
