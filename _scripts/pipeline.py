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
import notion
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
    """
    Genere un site vitrine de demo pour un eleveur.
    Retourne l'URL GitHub Pages ou None si pas de template.
    """
    name = profile["name"]
    race = profile["races"][0]
    phone = profile.get("phone", "")
    ville = profile.get("ville", "")
    departement = profile.get("departement", "")

    # Essayer de generer avec le template existant
    site_result = generator.generate_site(
        name=name, race=race, phone=phone,
        city=ville or departement,
    )

    if site_result:
        return site_result[1]  # URL GitHub Pages

    # Pas de template : on retourne None, le site sera cree manuellement
    return None


def generate_pitch(profile: dict, demo_url: str | None) -> str:
    """
    Genere un pitch personnalise pour l'appel commercial.
    """
    name = profile["name"]
    race = profile["races"][0]
    phone = profile.get("phone", "")
    ville = profile.get("ville", "")
    departement = profile.get("departement", "")
    description = profile.get("description", "")
    siren = profile.get("siren", "")
    acaced = profile.get("acaced", "")
    email = profile.get("email", "")

    # Construction du lieu
    lieu = "en France"
    if ville and departement:
        lieu = f"a {ville} ({departement})"
    elif ville:
        lieu = f"a {ville}"
    elif departement:
        lieu = f"dans le {departement}"

    # Construction de la demo
    demo_phrase = ""
    if demo_url:
        demo_phrase = (
            f"\n\nJ'ai prepare une demo gratuite pour vous voir le rendu possible "
            f"pour votre elevage : {demo_url}"
        )
    else:
        demo_phrase = (
            f"\n\nJe peux vous preparer une demo gratuite de site internet "
            f"pour votre elevage si vous etes interesse."
        )

    # Extraire un accroche de la description
    accroche = ""
    if description and len(description) > 20:
        # Prendre une phrase courte et percutante
        phrases = re.split(r'[.!?\n]', description)
        for p in phrases:
            p = p.strip()
            if 30 < len(p) < 200:
                accroche = f' J\'ai vu votre description : "{p[:150]}..."'
                break

    # Credibilite (SIREN, ACACED)
    credibilite = ""
    if siren:
        credibilite += f" Je vois que vous etes un elevage professionnel (SIREN {siren})."
    if acaced:
        credibilite += " Certifie ACACED, c'est serieux."
    if email:
        credibilite += f" Je vous ecris aussi a {email}."

    pitch = (
        f"Bonjour {name},"
        f"\n\nJe suis developpeur web specialise dans la creation de sites "
        f"pour les eleveurs canins.{credibilite}"
        f"{accroche}"
        f"\n\nJ'ai une offre speciale : un site vitrine cle en main pour votre "
        f"elevage de {race} {lieu}, heberge, personnalise avec vos photos, "
        f"visible sur Google."
        f"{demo_phrase}"
        f"\n\nEst-ce que vous avez 2 minutes pour qu'on en parle ?"
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

    # 1. Scraper
    print("📡 Scraping chien.com...")
    candidates = scraper.scrape(pages=config.PAGES_TO_SCRAPE,
                                max_results=config.SITES_PER_DAY)
    print(f"   -> {len(candidates)} eleveurs potentiels trouves")

    if not candidates:
        telegram.send("ℹ️ Aucun eleveur trouve aujourd'hui.")
        return

    # 2. Filtrer les deja dans Notion
    print("📋 Verification Notion (doublons)...")
    existing_phones = notion.get_existing_phones() if not dry_run else set()

    def normalize(p):
        return p.replace(" ", "").replace("-", "").replace(".", "")

    new_breeders = [
        b for b in candidates
        if b.get("phone") and normalize(b["phone"]) not in existing_phones
    ][:config.SITES_PER_DAY]

    print(f"   -> {len(new_breeders)} nouveaux eleveurs a traiter")

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

            notion.add_entry(
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
