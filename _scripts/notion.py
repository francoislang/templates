import requests
import config

HEADERS = {
    "Authorization": f"Bearer {config.NOTION_SECRET}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
BASE = "https://api.notion.com/v1"


def get_existing_phones() -> set[str]:
    phones = set()
    has_more, cursor = True, None
    while has_more:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(
            f"{BASE}/databases/{config.NOTION_DATABASE_ID}/query",
            headers=HEADERS, json=body, timeout=10
        ).json()
        for page in r.get("results", []):
            phone = page["properties"].get("Contact", {}).get("phone_number")
            if phone:
                phones.add(_normalize(phone))
        has_more = r.get("has_more", False)
        cursor = r.get("next_cursor")
    return phones


def add_entry(elevage: str, races: list[str], phone: str,
              demo_url: str = None, notes: str = None) -> str:
    props = {
        "Élevage": {"title": [{"text": {"content": elevage}}]},
        "Race": {"multi_select": [{"name": r} for r in races]},
        "Contact": {"phone_number": phone},
        "Statut": {"status": {"name": "À contacter"}},
    }
    if demo_url:
        props["Démo envoyée"] = {"url": demo_url}
    if notes:
        props["Notes"] = {"rich_text": [{"text": {"content": notes}}]}
    r = requests.post(
        f"{BASE}/pages", headers=HEADERS,
        json={"parent": {"database_id": config.NOTION_DATABASE_ID}, "properties": props},
        timeout=10
    ).json()
    return r.get("id", "")


def update_entry(page_id: str, demo_url: str = None, notes: str = None) -> None:
    props = {}
    if demo_url:
        props["Démo envoyée"] = {"url": demo_url}
    if notes:
        props["Notes"] = {"rich_text": [{"text": {"content": notes}}]}
    if props:
        requests.patch(
            f"{BASE}/pages/{page_id}", headers=HEADERS,
            json={"properties": props}, timeout=10
        )


def _normalize(phone: str) -> str:
    return phone.replace(" ", "").replace("-", "").replace(".", "")
