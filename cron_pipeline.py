#!/usr/bin/env python3
"""Pipeline auto-contenue pour le cron (no_agent mode)."""
import sys, json, subprocess, os
sys.path.insert(0, "/workspace/templates/_scripts")
os.chdir("/workspace/templates")

import scraper, crm, time
from cloudinary_check import get_photos_for_breed
from photos import get_photos_for_race
from generator import generate_site
import telegram

# 1. Scraper
existing = {*crm.get_existing_phones()}
existing_n = {n.strip().lower() for n in crm.get_existing_names()}
def norm(p): return p.replace(" ","").replace("-","").replace(".","")

new = []; page = 1
while len(new) < 3 and page <= 20:
    for url in scraper.fetch_listing_page(page):
        if len(new) >= 3: break
        p = scraper.fetch_profile(url)
        if not p or not p.get("phone"): continue
        if norm(p["phone"]) in existing: continue
        if p["name"].strip().lower() in existing_n: continue
        new.append(p)
        print(f"#{len(new)} {p['name']} ({p['races'][0]})")
    page += 1; time.sleep(2)

# 2. Generer
results = []
for p in new:
    race = p["races"][0]
    photos = get_photos_for_breed(race) or get_photos_for_race(race, count=15)
    r = generate_site(name=p["name"], race=race, phone=p["phone"],
        city=p.get("ville",""), departement=p.get("departement",""),
        description=p.get("description",""), siren=p.get("siren",""),
        photos_race=photos)
    url = r[1] if r else None
    crm.add_entry(elevage=p["name"], races=p["races"], phone=p["phone"], demo_url=url)
    results.append(p)
    print(f"  => {url}")

# 3. Git push
subprocess.run(["git","add","-A"], cwd="/workspace/templates")
subprocess.run(["git","commit","-m",f"Sites du {__import__('datetime').datetime.now().strftime('%d/%m')}"], cwd="/workspace/templates", check=False)
subprocess.run(["git","pull","--rebase","origin","main"], cwd="/workspace/templates", capture_output=True, timeout=30)
subprocess.run(["git","push","origin","main"], cwd="/workspace/templates", capture_output=True, timeout=60)

# 4. Telegram
total = len(results)
msg = f"🐾 PROSPECTION DU JOUR - {total} nouveau(x) eleveur(s)\n"
msg += "━" * 30 + "\n"
for p in results:
    race = p["races"][0]
    slug = p["name"].lower().replace("'","").replace(" ","-").strip("-")
    ville = p.get("ville","") or ""
    dept = p.get("departement","") or ""
    msg += f"\n🐕 {p['name']}\n📌 {race}\n📞 {p['phone']}"
    if ville or dept: msg += f"\n📍 {ville} {dept}"
    msg += f"\n🌐 https://francoislang.github.io/templates/{slug}\n"
    lieu = f" a {ville} ({dept})" if ville and dept else (f" a {ville}" if ville else (f" dans le {dept}" if dept else ""))
    msg += "\n" + "─" * 30
    msg += "\n\n--- PITCH A ENVOYER ---\n"
    msg += "Bonjour,\n\n"
    msg += "Je suis developpeur web et je creer des sites internet pour les eleveurs canins.\n\n"
    msg += f"J'ai prepare une demo gratuite pour votre elevage de {race}{lieu} :\nhttps://francoislang.github.io/templates/{slug}\n\n"
    msg += "C'est un site vitrine cle en main, heberge, avec vos photos, reference sur Google.\n\n"
    msg += "Je vous laisse regarder la demo et si le rendu vous plait, on en parle par telephone.\n\n"
    msg += "Bonne journee,\n\n"
    msg += "Francois-Frederic Lang\nlangfrancoisfrederic@gmail.com\n"
    msg += "--- FIN DU PITCH ---"

telegram.send(msg)
print("✅ Fini")
