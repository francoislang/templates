#!/usr/bin/env python3
"""
Script de vérification des relances — cron quotidien.

1. Parcourt les items "A relancer" du board CRM GitHub
2. Initialise le champ "Relance J+7" à la date de mise à jour si vide
3. Si 7 jours écoulés depuis "Relance J+7", envoie une notification Telegram

Usage (no_agent): python3 relance_check.py
"""
import requests, json, re, sys, os
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ── Chargement .env ──────────────────────────────────────
# Chercher .env : d'abord /workspace/templates/.env, puis relatif au script
_script_dir = Path(__file__).resolve().parent
_candidates = [
    Path("/workspace/templates/.env"),
    _script_dir.parent / ".env",
    _script_dir.parent.parent / ".env",
]
env_path = None
for c in _candidates:
    if c.exists():
        env_path = c
        break
if not env_path:
    print("❌ .env introuvable")
    sys.exit(1)

GITHUB_TOKEN = ""
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

if env_path.exists():
    for line in env_path.read_text().split('\n'):
        line = line.strip()
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k == 'GITHUB_TOKEN_PUSH_HERMES':
            GITHUB_TOKEN = v
        elif k == 'TELEGRAM_BOT_TOKEN':
            TELEGRAM_BOT_TOKEN = v
        elif k == 'TELEGRAM_CHAT_ID':
            TELEGRAM_CHAT_ID = v

if not GITHUB_TOKEN:
    print("❌ GITHUB_TOKEN_PUSH_HERMES manquant dans .env")
    sys.exit(1)
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant dans .env")
    sys.exit(1)

# ── Constantes GitHub ────────────────────────────────────
PROJECT_ID = "PVT_kwHOBcibjc4BZSav"
RELANCE_FIELD_ID = "PVTF_lAHOBcibjc4BZSavzhUSM38"  # Relance J+7 (DATE)
A_RELANCER_OPTION_ID = "a3615a82"

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# ── GraphQL helpers ──────────────────────────────────────

def graphql(query: dict) -> dict:
    r = requests.post(
        "https://api.github.com/graphql",
        json=query,
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def get_all_items() -> list[dict]:
    """Récupère tous les items du board avec pagination."""
    items = []
    cursor = None
    while True:
        after = f', after: "{cursor}"' if cursor else ""
        q = {
            "query": f"""
            {{
              node(id: "{PROJECT_ID}") {{
                ... on ProjectV2 {{
                  items(first: 100{after}) {{
                    pageInfo {{ hasNextPage endCursor }}
                    nodes {{
                      id
                      fieldValues(first: 20) {{
                        nodes {{
                          __typename
                          ... on ProjectV2ItemFieldSingleSelectValue {{
                            name
                            field {{ ... on ProjectV2SingleSelectField {{ name }} }}
                          }}
                          ... on ProjectV2ItemFieldTextValue {{
                            text
                            field {{ ... on ProjectV2Field {{ name }} }}
                          }}
                          ... on ProjectV2ItemFieldDateValue {{
                            date
                            field {{ ... on ProjectV2Field {{ name }} }}
                          }}
                        }}
                      }}
                      content {{
                        ... on Issue {{
                          title
                          number
                          url
                          updatedAt
                          body
                        }}
                      }}
                    }}
                  }}
                }}
              }}
            }}
            """
        }
        data = graphql(q)
        items_data = data.get("data", {}).get("node", {}).get("items", {})
        items.extend(items_data.get("nodes", []))
        page_info = items_data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    return items


def set_relance_date(item_id: str, date_str: str) -> bool:
    """Met à jour le champ Relance J+7 d'un item."""
    q = {
        "query": f"""
        mutation {{
          updateProjectV2ItemFieldValue(input: {{
            projectId: "{PROJECT_ID}",
            itemId: "{item_id}",
            fieldId: "{RELANCE_FIELD_ID}",
            value: {{ date: "{date_str}" }}
          }}) {{
            projectV2Item {{ id }}
          }}
        }}
        """
    }
    try:
        graphql(q)
        return True
    except Exception as e:
        print(f"  ⚠️ Erreur mise à jour date pour {item_id}: {e}")
        return False


def send_telegram(text: str) -> bool:
    """Envoie un message Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True,
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"  ⚠️ Erreur Telegram: {e}")
        return False


# ── Main ─────────────────────────────────────────────────

def main():
    today = datetime.now(timezone.utc).date()
    print(f"📅 Relance check — {today}")
    print(f"{'─' * 50}")

    items = get_all_items()
    print(f"📊 {len(items)} items sur le board")

    # Filtrer "A relancer"
    a_relancer = []
    for item in items:
        status = None
        relance_date = None
        phone = ""
        demo_url = ""

        for fv in item.get("fieldValues", {}).get("nodes", []):
            field_name = (fv.get("field") or {}).get("name", "")
            typename = fv.get("__typename", "")

            if "SingleSelect" in typename and field_name == "Status":
                status = fv.get("name")
            elif "Date" in typename and field_name == "Relance J+7":
                relance_date = fv.get("date")
            elif "Text" in typename:
                if field_name == "Telephone":
                    phone = fv.get("text", "")
                elif field_name == "Demo envoyee":
                    demo_url = fv.get("text", "")

        if status != "A relancer":
            continue

        content = item.get("content") or {}
        title = content.get("title", "")
        issue_number = content.get("number", "")
        url = content.get("url", "")
        updated_at = content.get("updatedAt", "")

        # Extraire nom + race du titre "[Race] Nom — tel"
        # Le regex greedy .+ capture jusqu'au DERNIER — ou -
        race = ""
        elevage = ""
        m = re.match(r"\[([^\]]+)\]\s+(.+)\s+[—\-]\s+(.+)$", title)
        if m:
            race = m.group(1)
            elevage = m.group(2).strip()

        # Phone depuis le titre si pas dans le champ
        if not phone:
            m = re.search(r"[—\-]\s*([\d\s\.\+\-]+)$", title)
            if m:
                phone = m.group(1).strip()

        a_relancer.append({
            "item_id": item.get("id"),
            "issue_number": issue_number,
            "title": title,
            "elevage": elevage,
            "race": race,
            "url": url,
            "phone": phone,
            "demo_url": demo_url,
            "relance_date": relance_date,
            "updated_at": updated_at,
        })

    if not a_relancer:
        print("✅ Aucun item en « A relancer » — rien à faire.")
        return

    print(f"🔔 {len(a_relancer)} item(s) en « A relancer »\n")

    relances_envoyees = 0
    initialisations = 0

    for item in a_relancer:
        print(f"  #{item['issue_number']} | {item['elevage']} ({item['race']})")
        print(f"     📞 {item['phone']}")

        # Si pas de date Relance J+7, l'initialiser avec la date de updatedAt
        if not item["relance_date"]:
            # Utiliser updatedAt comme proxy de la date de mise en colonne
            try:
                updated_date = datetime.strptime(
                    item["updated_at"][:10], "%Y-%m-%d"
                ).date()
            except (ValueError, IndexError):
                updated_date = today

            date_str = updated_date.strftime("%Y-%m-%d")
            print(f"     📅 Initialisation Relance J+7 → {date_str}")
            if set_relance_date(item["item_id"], date_str):
                initialisations += 1
            continue  # On vient d'initialiser, pas de relance aujourd'hui

        # Vérifier si 7 jours sont passés
        try:
            relance_date = datetime.strptime(
                item["relance_date"], "%Y-%m-%d"
            ).date()
        except ValueError:
            print(f"     ⚠️ Date invalide: {item['relance_date']}")
            continue

        delta = (today - relance_date).days
        print(f"     ⏱️  J+{delta} (relance depuis le {item['relance_date']})")

        if delta >= 7:
            # Construire le message Telegram
            msg = (
                f"🔔 RELANCE À FAIRE — J+{delta}\n"
                f"{'─' * 30}\n"
                f"🐕 {item['elevage']} — {item['race']}\n"
                f"📞 {item['phone']}\n"
            )
            if item["demo_url"]:
                msg += f"🌐 {item['demo_url']}\n"
            msg += (
                f"\n"
                f"📝 PHRASE DE RELANCE :\n"
                f"Bonjour,\n\n"
                f"Je me permets de vous recontacter suite à mon message de la semaine "
                f"dernière concernant votre élevage de {item['race']}.\n\n"
                f"Avez-vous eu le temps de jeter un œil à la démo que je vous ai envoyée ? "
                f"N'hésitez pas si vous avez des questions, je reste disponible pour en discuter.\n\n"
                f"Bonne journée à vous,\n"
                f"François-Frédéric Lang\n"
                f"langfrancoisfrederic@gmail.com\n"
                f"06 32 81 42 00"
            )

            print(f"     🚀 Envoi Telegram...")
            if send_telegram(msg):
                relances_envoyees += 1
                print(f"     ✅ Envoyé !")
            else:
                print(f"     ❌ Échec envoi")

    print(f"\n{'─' * 50}")
    print(f"📊 Bilan : {initialisations} date(s) initialisée(s), {relances_envoyees} relance(s) envoyée(s)")


if __name__ == "__main__":
    main()
