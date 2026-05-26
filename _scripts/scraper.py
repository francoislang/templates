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

# Mapping slug URL chien.com → nom de race interne
SLUG_TO_RACE = {
    "elevage-border-collie": "Border Collie",
    "elevage-berger-australien": "Berger Australien",
    "elevage-cavalier-king-charles-spaniel": "Cavalier King Charles",
    "elevage-schnauzer-nain": "Schnauzer",
    "elevage-westie-west-highland-white-terrier": "West Highland White Terrier",
    "elevage-lagotto-romagnolo": "Lagotto Romagnolo",
    "elevage-berger-polonais-podhale": "Berger Polonais de Podhale",
    "elevage-carlin-pug-mops": "Carlin",
    "elevage-loulou-de-pomeranie": "Loulou de Poméranie",
}


def _get(url: str) :
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
    # Profils : adresse/elevage-{race}/{slug}-{id}.php (2 segments après adresse/)
    profile_re = re.compile(r"adresse/elevage-[^/]+/[^/]+-\d+\.php$")
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if profile_re.search(href):
            full = href if href.startswith("http") else BASE + "/" + href.lstrip("/")
            urls.append(full)
    return list(dict.fromkeys(urls))


def fetch_profile(url: str):
    """Extrait les infos d'un éleveur depuis sa page profil."""
    # Extraire la race depuis le slug URL — plus fiable que le HTML
    slug_match = re.search(r"/adresse/(elevage-[^/]+)/", url)
    if not slug_match:
        return None
    race = SLUG_TO_RACE.get(slug_match.group(1))
    if not race:
        return None

    r = _get(url)
    if not r:
        return None
    soup = BeautifulSoup(r.text, "html.parser")

    # Nom
    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else ""
    if not name:
        return None

    # Téléphone — regex sur le texte brut de la page
    text = soup.get_text(" ")
    phone_m = re.search(r'(?:0|\+33\s?)[1-9](?:[\s.\-]?\d{2}){4}', text)
    phone = phone_m.group(0).strip() if phone_m else ""

    # Ville — dans le breadcrumb ou le texte après "Ville"
    ville_m = re.search(r'Ville\s*[\xa0:]+\s*(\d{5})', text)
    location = ville_m.group(1) if ville_m else ""

    # Site actuel
    website_link = soup.select_one("a[href*='/t/out-']")
    website = website_link["href"] if website_link else ""
    if website and not website.startswith("http"):
        website = BASE + website

    return {
        "name": name,
        "races": [race],
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
