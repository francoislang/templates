"""
Migre les prospects depuis Notion vers GitHub Issues + Projects.
Ne migre PAS les "A contacter" (le cron les retrouvera).
"""
import sys; sys.path.insert(0, '_scripts')
import config, requests, json, crm

HEADERS = {
    "Authorization": f"Bearer {config.NOTION_SECRET}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# 1. Recuperer tous les prospects Notion
r = requests.post(
    f"https://api.notion.com/v1/databases/{config.NOTION_DATABASE_ID}/query",
    headers=HEADERS, json={"page_size": 100}, timeout=15
).json()

total = 0
migrated = 0
ignored = 0

for page in r.get("results", []):
    props = page["properties"]
    title = props.get("Elevage", {}).get("title", [{}])
    name = title[0].get("text", {}).get("content", "") if title and len(title) > 0 else ""
    statut = props.get("Statut", {}).get("status", {}).get("name", "")
    phone = props.get("Contact", {}).get("phone_number", "")
    ms = props.get("Race", {}).get("multi_select", [])
    race = ms[0].get("name", "") if ms else ""
    demo = props.get("Demo envoyee", {}).get("url", "") or props.get("Démo envoyée", {}).get("url", "")
    rt = props.get("Notes", {}).get("rich_text", [])
    notes = rt[0].get("text", {}).get("content", "") if rt else ""

    total += 1

    # Ignorer les "A contacter" — le cron les retrouvera
    if statut == "A contacter":
        ignored += 1
        print(f"  ⏭️  [IGNORE] {name or phone} — {race} (statut: {statut})")
        continue

    # Construire les notes comme le pipeline le ferait
    notes_str = notes

    # Creer l issue dans GitHub
    print(f"  ➡️  [MIGRATE] {name or phone} — {race} (statut: {statut})")
    issue_num = crm.add_entry(
        elevage=name or f"Elevage {phone}",
        races=[race] if race else [],
        phone=phone,
        demo_url=demo or None,
        notes=notes_str or None,
    )
    print(f"      -> Issue #{issue_num} creee")
    migrated += 1

print(f"\n=== RESULTAT ===")
print(f"Total dans Notion: {total}")
print(f"Ignores (A contacter): {ignored}")
print(f"Migres vers GitHub: {migrated}")
print(f"\nLe cron retrouvera les {ignored} prospects 'A contacter' automatiquement.")
