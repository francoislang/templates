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
import crm  # GitHub CRM (remplace notion)
import scraper
import cloudinary_check
import generator
from photos import get_photos_for_race


def _normalize(phone: str) -> str:
    return phone.replace(" ", "").replace("-", "").replace(".", "")


def _build_pitch(name: str, race: str, ville: str, departement: str,
                 description: str, demo_url: str, email: str = "",
                 website: str = "", siren: str = "") -> str:
    """Génère un pitch personnalisé pour l'appel commercial."""
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

    return "\n".join(pitch_parts)


def run() -> None:
    telegram.send("🔍 Agent démarré — recherche d'eleveurs sur chien.com…")

    # 1. Recuperer les telephones deja dans Notion
    existing = crm.get_existing_phones()

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

        photos = cloudinary_check.get_photos_for_breed(race) or get_photos_for_race(race, count=15)
        has_photos = bool(photos)
        site_result = generator.generate_site(
            name=name, race=race, phone=phone,
            city=ville or departement,
            photos_race=photos,
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
            notes_parts.append(f"Description: {description}")
        notes_parts.append(f"Pitch: {pitch}")
        notes = " | ".join(notes_parts) if notes_parts else None

        crm.add_entry(
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

    # 5. Notification Telegram — un message par éleveur
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
        for w in r["warnings"]:
            msg_parts.append(f"⚠️ {w}")
        msg_parts.append("")
        msg_parts.append("--- PITCH À ENVOYER ---")
        msg_parts.append(r["pitch"])
        msg_parts.append("--- FIN DU PITCH ---")
        telegram.send("\n".join(msg_parts))

    resume = f"🐕 {len(results)} éleveurs trouvés — {sites_created} sites générés"
    if sans_template:
        resume += f"\n📋 Sans template : {', '.join(r['name'] + ' (' + r['race'] + ')' for r in sans_template)}"
    telegram.send(resume)


if __name__ == "__main__":
    run()
