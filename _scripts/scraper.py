import re
import time
import requests
from bs4 import BeautifulSoup
from cloudinary_check import supported_breeds

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
BASE = "https://www.chien.com"
DELAY = 1.5  # secondes entre requêtes


def _get(url: str) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        return r if r.status_code == 200 else None
    except Exception:
        return None


def fetch_listing_page(page: int) -> list[str]:
    """Retourne les URLs de profils depuis une page de listing."""
    url = f"{BASE}/adresse/1-0-0-0-0-elevage-de-chiens-{page}.php"
    r = _get(url)
    if not r:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    urls = []
    for a in soup.select("a[href]"):
        href = a["href"]
        if "elevage-" in href and href.endswith(".php") and "/adresse/" in href:
            full = href if href.startswith("http") else BASE + "/" + href.lstrip("/")
            urls.append(full)
    return list(dict.fromkeys(urls))


def fetch_profile(url: str) -> dict | None:
    """Extrait les infos d'un éleveur depuis sa page profil."""
    r = _get(url)
    if not r:
        return None
    soup = BeautifulSoup(r.text, "html.parser")

    # Races
    races = []
    for h3 in soup.find_all("h3"):
        text = h3.get_text(strip=True)
        if text.startswith("Élevage de "):
            races.append(text.replace("Élevage de ", "").strip())
        elif text.startswith("Éleveur de "):
            races.append(text.replace("Éleveur de ", "").strip())

    # Filtrer : on ne garde que les races pour lesquelles on a un template
    supported = set(supported_breeds())
    matching_races = [r for r in races if r in supported]
    if not matching_races:
        return None

    # Nom
    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else ""
    if not name:
        return None

    # Téléphone
    phone = _extract_after_label(soup, r"Téléphone")

    # Adresse
    location = _extract_after_label(soup, r"Adresse")

    # Site actuel
    website_link = soup.select_one("a[href*='/t/out-']")
    website = website_link["href"] if website_link else ""
    if website and not website.startswith("http"):
        website = BASE + website

    return {
        "name": name,
        "races": matching_races,
        "phone": phone,
        "location": location,
        "website": website,
        "source_url": url,
    }


def _extract_after_label(soup: BeautifulSoup, label_pattern: str) -> str:
    label = soup.find("strong", string=re.compile(label_pattern))
    if not label:
        return ""
    parts = []
    for node in label.next_siblings:
        if hasattr(node, "name") and node.name == "strong":
            break
        text = node.get_text(strip=True) if hasattr(node, "get_text") else str(node).strip()
        if text:
            parts.append(text)
        if len(parts) >= 3:
            break
    return " ".join(parts)


def scrape(pages: int = 5) -> list[dict]:
    """Scrape `pages` pages de listing et retourne les profils correspondant aux races connues."""
    results = []
    for page in range(1, pages + 1):
        profile_urls = fetch_listing_page(page)
        for url in profile_urls:
            profile = fetch_profile(url)
            if profile and profile.get("phone"):
                results.append(profile)
            time.sleep(DELAY)
        time.sleep(2)
    return results
