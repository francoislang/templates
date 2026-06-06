#!/usr/bin/env python3
"""Regenere tous les sites existants avec l'IA scraper + description complete."""
import sys, os, json, re
sys.path.insert(0, "/workspace/templates/_scripts")
os.chdir("/workspace/templates")

import requests
from bs4 import BeautifulSoup

# Pour chaque dossier site, tenter de retrouver son URL chien.com et rescraper
sites = [d for d in os.listdir(".") if os.path.isfile(f"{d}/index.html") and d not in ("_scripts","_templates","_data")]

for slug in sorted(sites):
    html = open(f"{slug}/index.html").read()
    
    # Chercher l'URL source ou le nom dans le HTML
    name_m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    name = name_m.group(1).strip() if name_m else slug.replace("-"," ").title()
    
    print(f"\n🔄 {name} ({slug})")
    
    # Chercher le profil sur chien.com en parcourant les pages
    found = False
    for page in range(1, 10):
        r = requests.get(
            f"https://www.chien.com/adresse/1-0-0-0-0-elevage-de-chiens-{page}.php",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=15
        )
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a[href*='/adresse/elevage-']"):
            href = a.get("href","")
            a_text = a.get_text(strip=True).lower()
            if name.lower()[:20] in a_text or slug.replace("-","") in href.lower():
                url = f"https://www.chien.com{href}"
                # Utiliser l'IA scraper
                from scraper import fetch_profile_ai
                p = fetch_profile_ai(url)
                if p:
                    from generator import generate_site, clean_description
                    desc = clean_description(p.get("description","") or "")
                    race = p["races"][0]
                    print(f"   ✓ IA: {race}, {len(desc)} chars desc")
                    r2 = generate_site(
                        name=p["name"], race=race, phone=p.get("phone",""),
                        city=p.get("ville",""), departement=p.get("departement",""),
                        description=desc, siren=p.get("siren",""),
                        photo_url=p.get("photo_url",""),
                    )
                    if r2:
                        print(f"   ✓ Site regenere: {r2[0]}")
                    found = True
                break
        if found: break
    
    if not found:
        print(f"   ⚠️ Profil non trouve sur chien.com")

print("\n✅ Fini")
