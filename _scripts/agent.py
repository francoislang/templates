#!/usr/bin/env python3
"""
Agent principal : scrape chien.com → vérifie Notion → génère les sites → notifie Telegram.
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


def _build_pitch(name: str, race: str, city: str, demo_url: str) -> str:
    lieu = f"dans le {city}" if city else "en France"
    demo = f"J'ai d'ailleurs préparé une démo pour vous : {demo_url}" if demo_url else "Je peux vous préparer une démo gratuite."
    return (
        f"Bonjour, je suis développeur web spécialisé pour les éleveurs. "
        f"J'ai vu votre annonce sur chien.com pour votre élevage {name} de {race} {lieu}. "
        f"{demo} "
        f"Est-ce que vous avez 2 minutes pour en parler ?"
    )


def run() -> None:
    telegram.send("🔍 Agent démarré — recherche d'éleveurs sur chien.com…")

    # 1. Récupérer les téléphones déjà dans Notion
    existing = notion.get_existing_phones()

    # 2. Scraper chien.com
    candidates = scraper.scrape(pages=5)

    # 3. Filtrer les nouveaux (pas dans Notion, téléphone présent)
    new_breeders = [
        b for b in candidates
        if b.get("phone") and _normalize(b["phone"]) not in existing
    ][:config.SITES_PER_DAY]

    if not new_breeders:
        telegram.send("ℹ️ Aucun nouvel éleveur trouvé aujourd'hui.")
        return

    results = []
    sites_created = 0

    for breeder in new_breeders:
        name = breeder["name"]
        races = breeder["races"]
        phone = breeder["phone"]
        city = breeder.get("location", "")
        race = races[0]

        has_photos = cloudinary_check.has_photos_for_breed(race)
        site_result = generator.generate_site(name=name, race=race, phone=phone, city=city)

        warnings = []
        if not has_photos:
            warnings.append(f"photos {race} manquantes sur Cloudinary")
        if not site_result:
            warnings.append(f"pas de template pour {race}")

        demo_url = site_result[1] if site_result else None

        pitch = _build_pitch(name=name, race=race, city=city, demo_url=demo_url)
        notes_parts = warnings + ([f"Pitch : {pitch}"] if pitch else [])
        notes = " | ".join(notes_parts) if notes_parts else None

        notion.add_entry(elevage=name, races=races, phone=phone, demo_url=demo_url, notes=notes)

        if site_result:
            sites_created += 1

        results.append({
            "name": name, "race": race, "phone": phone, "city": city,
            "demo_url": demo_url, "has_photos": has_photos,
            "has_template": site_result is not None, "warnings": warnings,
            "pitch": pitch,
        })

    # 4. Commit + push si des sites ont été générés
    if sites_created > 0:
        subprocess.run(
            ["git", "-C", str(config.REPO_ROOT), "commit",
             "-m", f"Add {sites_created} demo site(s) via agent"],
            check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(config.REPO_ROOT), "push", "origin", "main"],
            check=True, capture_output=True
        )

    # 5. Notification Telegram
    lines = [f"✅ *{len(results)} éleveurs traités* ({sites_created} sites générés)\n"]

    for r in results:
        icon = "✅" if r["demo_url"] and r["has_photos"] else "⚠️"
        lines.append(f"{icon} *{r['name']}* — {r['race']}")
        lines.append(f"   📞 {r['phone']}")
        if r["city"]:
            lines.append(f"   📍 {r['city']}")
        if r["demo_url"]:
            lines.append(f"   🌐 {r['demo_url']}")
        if r.get("pitch"):
            lines.append(f"\n💬 _{r['pitch']}_")
        for w in r["warnings"]:
            lines.append(f"   ⚠️ {w}")
        lines.append("")

    telegram.send("\n".join(lines))


if __name__ == "__main__":
    run()
