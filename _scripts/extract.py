#!/usr/bin/env python3
"""
Script utilitaire : extraire les infos d'un elevage depuis une URL chien.com
et generer un fichier YAML de configuration pour le template.

Usage:
    python _scripts/extract.py https://www.chien.com/adresse/.../elevage-xxx.php
    python _scripts/extract.py --yaml https://www.chien.com/adresse/.../elevage-xxx.php
"""
import sys
import os
import json
import yaml

sys.path.insert(0, os.path.dirname(__file__))

import scraper


def extract(url: str) -> dict:
    """Extrait les infos d'un elevage depuis son URL chien.com."""
    profile = scraper.fetch_profile(url)
    if not profile:
        print(f"❌ Impossible d'extraire les infos depuis : {url}", file=sys.stderr)
        print("   Raisons possibles : race non repertoriee, page inaccessible,", file=sys.stderr)
        print("   ou donnees insuffisantes.", file=sys.stderr)
        return None
    return profile


def to_yaml(profile: dict) -> str:
    """Convertit un profil en fichier YAML pret a etre utilise par le generator."""
    race = profile["races"][0]

    # Slug du template
    from cloudinary_check import BREED_TEMPLATE
    template_folder = BREED_TEMPLATE.get(race)
    template_name = template_folder or ""

    data = {
        "template": template_name,
        "elevage": {
            "nom": profile["name"],
            "race": race,
            "departement": profile.get("departement", ""),
            "region": profile.get("departement", ""),
            "code_postal": profile.get("code_postal", ""),
            "telephone": profile.get("phone", ""),
            "siren": profile.get("siren", ""),
            "url": profile.get("website", ""),
            "description_hero": f"Elevage {profile['name']} — {race}",
            "description_about": profile.get("description", ""),
            "description_seo": f"Elevage {profile['name']} de {race} "
                               f"dans le {profile.get('departement', 'France')}.",
        },
        "couleurs": {
            "primaire": "#1B3A4B",
            "accent": "#D4622A",
            "fond": "#F7F4EF",
        },
        "photos": {
            "hero": "",
            "og": "",
            "about_1": "",
            "about_2": "",
            "race": "",
            "galerie": [],
        },
        "reproducteurs": [],
        "temoignages": [],
    }
    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    args = sys.argv[1:]
    to_yaml_mode = "--yaml" in args
    urls = [a for a in args if not a.startswith("--")]

    for url in urls:
        profile = extract(url)
        if not profile:
            continue

        if to_yaml_mode:
            print(f"# Fichier YAML pour {profile['name']}")
            print(f"# Enregistrer dans _data/{profile['name'].lower().replace(' ', '-')}.yaml")
            print("---")
            print(to_yaml(profile))
        else:
            print(json.dumps(profile, ensure_ascii=False, indent=2))

        print()


if __name__ == "__main__":
    main()
