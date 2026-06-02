#!/usr/bin/env python3
"""Pipeline prospection: scrape, photos, DeepSeek V4 Pro, CRM, Telegram."""
import sys, os, re, time, json, subprocess
sys.path.insert(0, os.path.dirname(__file__))
import config, scraper, telegram, crm
from generator import generate_site
from photos import get_photos_for_race
from cloudinary_check import get_photos_for_breed

def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

def generate_demo_site(profile):
    """Genere un site via DeepSeek V4 Pro (OpenRouter)."""
    import requests
    from pathlib import Path

    name = profile["name"]; race = profile["races"][0]
    phone = profile.get("phone",""); ville = profile.get("ville","")
    dept = profile.get("departement",""); desc = profile.get("description","") or ""
    siren = profile.get("siren",""); p_url = profile.get("photo_url","")

    slug = slugify(name)
    target = Path("/workspace/templates") / slug / "index.html"
    if target.exists():
        return f"https://francoislang.github.io/templates/{slug}"

    photos = get_photos_for_breed(race) or get_photos_for_race(race, count=15) or []

    # Cle OpenRouter
    key = ""
    for fp in (os.path.expanduser("~/.hermes/.env"), "/workspace/templates/.env"):
        for line in open(fp):
            if "ANTHROPIC_API_KEY" in line and "=" in line:
                key = line.split("=",1)[1].strip(); break
        if key: break

    if not key:
        from generator import generate_site
        r = generate_site(name=name, race=race, phone=phone, city=ville or dept,
                         description=desc, siren=siren, departement=dept,
                         photo_url=p_url, photos_race=photos)
        return r[1] if r else None

    # Reference joyaux-d-anubis
    ref = ""
    try: ref = open("/workspace/templates/joyaux-d-anubis/index.html").read()[:4000]
    except: pass

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
    target.parent.mkdir(exist_ok=True); target.write_text(html, encoding="utf-8")
    subprocess.run(["git","-C","/workspace/templates","add",f"{slug}/index.html"], capture_output=True)
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

    # Construction de la demo
    demo_phrase = ""
    if demo_url:
        demo_phrase = (
            f"\n\nJ'ai préparé une démo gratuite pour vous montrer le rendu "
            f"possible pour votre élevage : {demo_url}"
        )
    else:
        demo_phrase = (
            f"\n\nJe peux vous préparer une démo gratuite de site internet "
            f"pour votre élevage si vous êtes intéressé."
        )

    pitch = (
        f"Bonjour,"
        f"\n\nJe suis développeur web spécialisé dans la création de sites "
        f"pour les éleveurs canins."
        f"\n\nJ'ai une offre spéciale : un site vitrine clé en main pour votre "
        f"élevage de {race} {lieu}, hébergé, personnalisé avec vos photos, "
        f"visible sur Google."
        f"{demo_phrase}"
        f"\n\nEst-ce que vous avez 2 minutes pour qu'on en parle ?"
        f"\n\nFrançois-Frédéric Lang"
        f"\nlangfrancoisfrederic@gmail.com"
    )

    return pitch




def get_repo_root() -> str:
    return str(config.REPO_ROOT)

def commit_and_push(sites_count: int) -> bool:
    """Commit et push les nouveaux sites sur GitHub."""
    repo_root = get_repo_root()
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
    telegram.send("🔍 Pipeline demarre — recherche d'eleveurs...")

    # 1. Recuperer les telephones et noms existants (pour dedup)
    print("📋 Recuperation des existants pour dedup...")
    existing_phones = crm.get_existing_phones() if not dry_run else set()
    existing_names = crm.get_existing_names() if not dry_run else set()

    def normalize(p):
        return p.replace(" ", "").replace("-", "").replace(".", "")

    # 2. Scraper profil par profil jusqu'a trouver 10 nouveaux
    print("📡 Scraping chien.com profil par profil...")
    new_breeders = []
    page = 1
    max_pages = 20  # securite: ne pas scraper plus de 20 pages
    SITES_PER_DAY = config.SITES_PER_DAY
    
    while len(new_breeders) < SITES_PER_DAY and page <= max_pages:
        profile_urls = scraper.fetch_listing_page(page)
        if not profile_urls:
            print(f"   Page {page} vide, arret du scraping")
            break
        
        print(f"   Page {page}: {len(profile_urls)} profils trouves")
        
        for url in profile_urls:
            if len(new_breeders) >= SITES_PER_DAY:
                break
            
            profile = scraper.fetch_profile(url)
            if not profile or not profile.get("phone"):
                continue
            
            if normalize(profile["phone"]) in existing_phones:
                continue  # deja connu par telephone
            if profile["name"].strip().lower() in existing_names:
                continue  # deja connu par nom d'elevage
            
            new_breeders.append(profile)
            print(f"      #{len(new_breeders)}: {profile['name']} ({profile['races'][0]}) — {profile['phone']}")
            import time
            time.sleep(scraper.DELAY)
        
        page += 1
        if len(new_breeders) < SITES_PER_DAY:
            import time
            time.sleep(2)
    
    print(f"   -> {len(new_breeders)} nouveaux eleveurs trouves sur {page-1} page(s)")
    
    if not new_breeders:
        telegram.send("ℹ️ Aucun nouvel eleveur (deja tous dans Notion).")
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

        # 3c. Ajouter dans Notion
        if not dry_run:
            warnings = []
            if not has_template:
                warnings.append(f"pas de template pour {race}")

            notes_parts = warnings[:]
            if breeder.get("description"):
                desc = breeder["description"][:200]
                notes_parts.append(f"Description: {desc}...")
            if breeder.get("website"):
                notes_parts.append(f"Site actuel: {breeder['website']}")
            if breeder.get("email"):
                notes_parts.append(f"Email: {breeder['email']}")
            notes_parts.append(f"Pitch: {pitch}")
            notes = " | ".join(notes_parts)

            crm.add_entry(
                elevage=name, races=breeder["races"], phone=phone,
                demo_url=demo_url, notes=notes
            )
            print("   ✅ Ajoute dans Notion")

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
        msg_parts.append("--- PITCH A ENVOYER ---")
        msg_parts.append(r['pitch'])
        msg_parts.append("--- FIN DU PITCH ---")

        if dry_run:
            print(f"\nMessage pour {r['name']}:\n" + "\n".join(msg_parts))
        else:
            telegram.send("\n".join(msg_parts))

    # Resumer les resultats en un seul message
    resume = f"🐕 {len(results)} eleveurs trouves — {sites_created} sites generes"
    if sans_template:
        resume += f"\n📋 Sans template: {', '.join(r['name'] + ' (' + r['race'] + ')' for r in sans_template)}"

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
