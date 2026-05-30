#!/usr/bin/env python3
"""
Agent principal : scrape chien.com -> verifie Notion -> genere les sites -> notifie Telegram.
Usage : python _scripts/agent.py
"""
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import config
import telegram
import notion
import scraper
import cloudinary_check
import generator


def _normalize(phone: str) -> str:
    return phone.replace(" ", "").replace("-", "").replace(".", "")


def _build_pitch(name: str, race: str, ville: str, departement: str,
                 description: str, demo_url: str, email: str = "",
                 website: str = "", siren: str = "") -> str:
    """Genere un pitch personnalise avec les infos extraites."""
    lieu = ""
    if ville:
        lieu = f"a {ville}"
        if departement:
            lieu += f" ({departement})"
    elif departement:
        lieu = f"dans le {departement}"
    else:
        lieu = "en France"

    demo = ""
    if demo_url:
        demo = f"J'ai d'ailleurs prepare une demo pour vous : {demo_url}"
    else:
        demo = "Je peux vous preparer une demo gratuite."

    pitch = (
        f"Bonjour, je suis developpeur web specialise pour les eleveurs. "
        f"J'ai vu votre annonce sur chien.com pour votre elevage {name} "
        f"de {race} {lieu}. "
        f"{demo} "
        f"Est-ce que vous avez 2 minutes pour en parler ?"
    )

    if not demo_url and description:
        pitch += (
            f"\n\nJ'ai lu votre presentation : "
            f"\"{description[:200]}...\" "
            f"Je pense pouvoir creer un site qui reflete vraiment votre travail."
        )

    return pitch


def run() -> None:
    telegram.send("🔍 Agent démarré — recherche d'eleveurs sur chien.com…")

    # 1. Recuperer les telephones deja dans Notion
    existing = notion.get_existing_phones()

    # 2. Scraper chien.com (PAGES_TO_SCRAPE pages, max SITES_PER_DAY eleveurs)
    candidates = scraper.scrape(pages=config.PAGES_TO_SCRAPE, max_results=config.SITES_PER_DAY)

    # 3. Filtrer les nouveaux (pas dans Notion, telephone present)
    new_breeders = [
        b for b in candidates
        if b.get("phone") and _normalize(b["phone"]) not in existing
    ][:config.SITES_PER_DAY]

    if not new_breeders:
        telegram.send("ℹ️ Aucun nouvel eleveur trouve aujourd'hui.")
        return

    results = []
    sites_created = 0

    for breeder in new_breeders:
        name = breeder["name"]
        races = breeder["races"]
        phone = breeder["phone"]
        race = races[0]
        ville = breeder.get("ville", "")
        departement = breeder.get("departement", "")
        description = breeder.get("description", "")
        email = breeder.get("email", "")
        siren = breeder.get("siren", "")

        has_photos = cloudinary_check.has_photos_for_breed(race)
        site_result = generator.generate_site(
            name=name, race=race, phone=phone,
            city=ville or departement
        )

        warnings = []
        if not has_photos:
            warnings.append(f"photos {race} manquantes sur Cloudinary")
        if not site_result:
            warnings.append(f"pas de template pour {race}")

        demo_url = site_result[1] if site_result else None

        pitch = _build_pitch(
            name=name, race=race, ville=ville, departement=departement,
            description=description, demo_url=demo_url, email=email,
            website=breeder.get("website", ""), siren=siren,
        )

        # Notes enrichies
        notes_parts = warnings[:]
        if email:
            notes_parts.append(f"Email: {email}")
        if breeder.get("website"):
            notes_parts.append(f"Site actuel: {breeder['website']}")
        if siren:
            notes_parts.append(f"SIREN: {siren}")
        if description:
            notes_parts.append(f"Description: {description[:200]}...")
        notes_parts.append(f"Pitch: {pitch}")
        notes = " | ".join(notes_parts) if notes_parts else None

        notion.add_entry(
            elevage=name, races=races, phone=phone,
            demo_url=demo_url, notes=notes
        )

        if site_result:
            sites_created += 1

        results.append({
            "name": name, "race": race, "phone": phone, "ville": ville,
            "departement": departement, "email": email,
            "demo_url": demo_url, "has_photos": has_photos,
            "has_template": site_result is not None, "warnings": warnings,
            "pitch": pitch,
            "description": description,
        })

    # 4. Commit + push si des sites ont ete generes
    if sites_created > 0:
        subprocess.run(
            ["git", "-C", str(config.REPO_ROOT), "commit",
             "-m", f"Ajout de {sites_created} site(s) de demo via agent"],
            check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(config.REPO_ROOT), "push", "origin", "main"],
            check=True, capture_output=True
        )

    # 5. Notification Telegram enrichie
    avec_site = [r for r in results if r["demo_url"]]
    sans_template = [r for r in results if not r["has_template"]]

    lines = [f"🐕 *{len(results)} eleveurs trouves* — {sites_created} sites generes\n"]

    for r in avec_site:
        icon = "✅" if r["has_photos"] else "⚠️"
        lines.append(f"{icon} *{r['name']}* — {r['race']}")
        lines.append(f"   📞 {r['phone']}")
        if r.get("email"):
            lines.append(f"   📧 {r['email']}")
        if r.get("ville"):
            loc = r['ville']
            if r.get('departement'):
                loc += f" ({r['departement']})"
            lines.append(f"   📍 {loc}")
        lines.append(f"   🌐 {r['demo_url']}")
        if r.get("pitch"):
            lines.append(f"   💬 _{r['pitch']}_")
        for w in r["warnings"]:
            lines.append(f"   ⚠️ {w}")
        lines.append("")

    if sans_template:
        lines.append("📋 *Sans template — a creer si interessant :*")
        for r in sans_template:
            extra = ""
            if r.get("ville"):
                extra = f" — {r['ville']}"
            lines.append(f"   • {r['name']} ({r['race']}){extra} — {r['phone']}")
        lines.append("")

    telegram.send("\n".join(lines))


if __name__ == "__main__":
    run()
