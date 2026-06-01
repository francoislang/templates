"""
Pipeline principal unifie :
1. Scrape chien.com
2. Filtre les doublons (Notion)
3. Genere un site vitrine personnalise
4. Prepare le pitch
5. Ajoute dans Notion
6. Commit + push sur GitHub
7. Notifie Telegram

Usage:
    python _scripts/pipeline.py
    python _scripts/pipeline.py --dry-run  # sans ecrire ni push
"""
import os
import sys
import subprocess
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

import config
import scraper
import crm       # GitHub Projects (remplace notion)
import telegram
import generator

# Mapping des races -> template existant ou fallback
BREED_TEMPLATE = {
    "Border Collie": "elevage-border-collie-mas-andre",
    "Berger Australien": "bois-de-chantalouette",
    "Cavalier King Charles": "domaine-du-quinquis",
    "Schnauzer": "mellan-schnauzers",
    "West Highland White Terrier": "ferme-aredienne-des-salines",
    "Lagotto Romagnolo": "la-dolce-vita",
    "Berger Polonais de Podhale": "gaec-du-chateau-d-alboy",
    "Carlin": "joyaux-d-anubis",
    "Loulou de Pomeranie": "des-cotons-de-soie-d-or",
    "Berger de Brie": "bois-de-chantalouette",
}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def get_repo_root() -> Path:
    return config.REPO_ROOT


def generate_demo_site(profile: dict) -> str | None:
    """Genere un site vitrine via Claude Sonnet 4 (API OpenRouter)."""
    import requests, json, os, re, time
    from pathlib import Path
    from generator import slugify
    from photos import get_photos_for_race

    name = profile["name"]
    race = profile["races"][0]
    phone = profile.get("phone", "")
    ville = profile.get("ville", "")
    departement = profile.get("departement", "")
    description = profile.get("description", "") or ""
    siren = profile.get("siren", "")
    photo_url = profile.get("photo_url", "")

    slug = slugify(name)
    target_dir = Path("/workspace/templates") / slug
    target_dir.mkdir(exist_ok=True)
    target_file = target_dir / "index.html"
    if target_file.exists():
        return f"https://francoislang.github.io/templates/{slug}"

    # Photos Cloudinary
    photos_race = get_photos_for_race(race, count=15) or []

    # Lire les sites de reference (tous les contacts)
    ref_sites = ["joyaux-d-anubis", "domaine-du-quinquis", "la-dolce-vita",
                 "des-cotons-de-soie-d-or", "mas-andre", "de-windy-stia",
                 "mellan-schnauzers", "la-ferme-aredienne-des-salines",
                 "du-bois-de-chantalouette", "des-marais-de-bremes"]
    refs = []
    for s in ref_sites:
        try:
            html = open(f"/workspace/templates/{s}/index.html", encoding="utf-8").read()
            refs.append(f"--- {s} ---\n{html[:3000]}")
        except:
            pass

    # Cle API OpenRouter
    key = ""
    for f_path in [os.path.expanduser("~/.hermes/.env"), "/workspace/templates/.env"]:
        try:
            for line in open(f_path):
                if "ANTHROPIC_API_KEY" in line and "=" in line:
                    key = line.split("=", 1)[1].strip()
                    if key: break
        except:
            pass

    if not key:
        # Fallback template universel
        from generator import generate_site
        r = generate_site(name=name, race=race, phone=phone, city=ville or departement,
                         description=description, siren=siren, departement=departement,
                         photo_url=photo_url, photos_race=photos_race)
        return r[1] if r else None

    lieu = f"à {ville} ({departement})" if ville and departement else "en France"
    photos_list = "\n".join(f"  - {p}" for p in photos_race[:5])

    prompt = f"""Crée un site vitrine HTML complet pour un éleveur de chiens.

INSPIRE-TOI DE CES SITES DE RÉFÉRENCE pour la structure, le style, les sections et la qualité (ce sont des sites déjà réalisés pour d'autres éleveurs) :
{chr(10).join(refs[:6000]) if refs else "Crée un site professionnel, unique et moderne avec Hero, About, Race, Galerie, Contact."}

CONTENU À ADAPTER :
- Nom élevage : {name}
- Race : {race}
- Téléphone : {phone}
- Localisation : {lieu}
- Description : {description[:500] if description else ""}
- SIREN : {siren or "Particulier"}
- Photo principale : {photo_url}
- Photos de la race : 
{photos_list}

INSTRUCTIONS :
- Garde la MÊME structure HTML, les mêmes classes CSS, les mêmes sections que le site de référence
- Remplace TOUT le contenu par les données ci-dessus
- Utilise les photos fournies (hero, about, galerie)
- Adapte les couleurs à la race (tons chauds pour chiens de chasse, vifs pour races dynamiques, doux pour races calmes)
- Garde Cinzel + Raleway comme polices
- Schema.org JSON-LD, Open Graph, meta description SEO
- Le site doit être RESPONSIVE, animations au scroll
- Réponds UNIQUEMENT avec le code HTML complet"""

    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": "anthropic/claude-sonnet-4", "messages": [{"role": "user", "content": prompt}], "max_tokens": 64000},
        timeout=300)

    html = r.json()["choices"][0]["message"]["content"]
    html = re.sub(r'^```html?\n?', '', html)
    html = re.sub(r'\n?```\s*$', '', html)

    target_file.write_text(html, encoding="utf-8")

    import subprocess
    subprocess.run(["git", "-C", "/workspace/templates", "add", f"{slug}/index.html"],
                   check=True, capture_output=True)

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
