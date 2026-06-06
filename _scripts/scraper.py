import re
import time
import requests
from bs4 import BeautifulSoup
# Note: supported_breeds importe config qui necessite .env.
# On ne l'importe pas ici pour que le scraper soit utilisable sans .env.
# L'agent.py l'importe via cloudinary_check directement.

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
BASE = "https://www.chien.com"
DELAY = 1.5  # secondes entre requetes

# Mapping slug URL chien.com -> nom de race
SLUG_TO_RACE = {
    # Races avec templates existants
    "elevage-border-collie": "Border Collie",
    "elevage-berger-australien": "Berger Australien",
    "elevage-cavalier-king-charles-spaniel": "Cavalier King Charles",
    "elevage-schnauzer-nain": "Schnauzer",
    "elevage-westie-west-highland-white-terrier": "West Highland White Terrier",
    "elevage-lagotto-romagnolo": "Lagotto Romagnolo",
    "elevage-berger-polonais-podhale": "Berger Polonais de Podhale",
    "elevage-carlin-pug-mops": "Carlin",
    "elevage-loulou-de-pomeranie": "Loulou de Pomeranie",
    # Races sans template — capturees comme prospects, on les garde aussi pour le pitch
    "elevage-berger-americain-miniature": "Berger Americain Miniature",
    "elevage-labrador-retriever": "Labrador Retriever",
    "elevage-golden-retriever": "Golden Retriever",
    "elevage-berger-allemand": "Berger Allemand",
    "elevage-chihuahua": "Chihuahua",
    "elevage-caniche": "Caniche",
    "elevage-bouledogue-francais": "Bouledogue Francais",
    "elevage-shiba-inu": "Shiba Inu",
    "elevage-husky-siberien": "Husky Siberien",
    "elevage-malinois-berger-belge": "Malinois",
    "elevage-samoyede": "Samoyede",
    "elevage-bichon-frise": "Bichon Frise",
    "elevage-spitz-nain": "Spitz Nain",
    "elevage-jack-russell-terrier": "Jack Russell Terrier",
    "elevage-beagle": "Beagle",
    "elevage-bulldog-anglais": "Bulldog Anglais",
    "elevage-dogue-de-bordeaux": "Dogue de Bordeaux",
    "elevage-rottweiler": "Rottweiler",
    "elevage-dalmatien": "Dalmatien",
    "elevage-setter-irlandais": "Setter Irlandais",
    "elevage-cocker-anglais": "Cocker Anglais",
    "elevage-yorkshire-terrier": "Yorkshire Terrier",
    "elevage-maltais": "Maltais",
    "elevage-berger-de-beauce-beauceron": "Beauceron",
    "elevage-leonberg": "Leonberg",
    "elevage-saint-bernard": "Saint-Bernard",
    "elevage-terre-neuve": "Terre-Neuve",
    "elevage-epagneul-breton": "Epagneul Breton",
    "elevage-braque-allemand": "Braque Allemand",
    "elevage-teckel": "Teckel",
    "elevage-pomsky": "Pomsky",
    "elevage-rhodesian-ridgeback": "Rhodesian Ridgeback",
    "elevage-alaskan-malamute": "Alaskan Malamute",
    "elevage-berger-blanc-suisse": "Berger Blanc Suisse",
    "elevage-berger-belge-malinois": "Malinois",
    "elevage-berger-belge-tervueren": "Tervueren",
    "elevage-bouvier-bernois": "Bouvier Bernois",
    "elevage-boxer": "Boxer",
    "elevage-cocker-americain": "Cocker Americain",
    "elevage-coton-de-tulear": "Coton de Tulear",
    "elevage-dobermann": "Dobermann",
    "elevage-dogue-allemand": "Dogue Allemand",
    "elevage-epagneul-breton": "Epagneul Breton",
    "elevage-levrette-italienne": "Levrette Italienne",
    "elevage-pinscher-nain": "Pinscher Nain",
    "elevage-berger-australien-miniature": "Berger Australien Miniature",
    "elevage-cane-corso": "Cane Corso",
    "elevage-berger-belge-groenendael": "Groenendael",
    "elevage-akita-inu": "Akita Inu",
    "elevage-bichon-maltais": "Maltais",
    "elevage-bichon-havanais": "Bichon Havanais",
    "elevage-berger-americain-miniature": "Berger Americain Miniature",
    "elevage-korthals-griffon": "Griffon Korthals",
    "elevage-braque-de-weimar": "Braque de Weimar",
    "elevage-bulldog-americain": "Bulldog Americain",
    "elevage-bouledogue-americain": "Bouledogue Americain",
    "elevage-pitbull-american-pit": "American Pitbull",
    "elevage-staffordshire-terrier": "Staffordshire Terrier",
    "elevage-american-staffordshire": "American Stafforshire",
    "elevage-pug-carling": "Carlin",
    "elevage-poodle-caniche": "Caniche",
    "elevage-shetland-sheltie": "Sheltie",
    "elevage-welsh-corgi-pembroke": "Welsh Corgi Pembroke",
    "elevage-welsh-corgi-cardigan": "Welsh Corgi Cardigan",
    "elevage-basset-hound": "Basset Hound",
    "elevage-dogue-du-tibet": "Dogue du Tibet",
    "elevage-akita-americain": "Akita Americain",
    "elevage-american-bully": "American Bully",
    "elevage-bouvier-australien": "Bouvier Australien",
    "elevage-chien-loup-tchecoslovaque": "Chien Loup Tchecoslovaque",
    "elevage-berger-croate": "Berger Croate",
    "elevage-beauceron": "Beauceron",
    "elevage-vallhund-suedois-spitz-des-wisigoths": "Vallhund Suédois",
    "elevage-spitz-des-wisigoths": "Vallhund Suédois",
}


def _get(url: str):
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
    profile_re = re.compile(r"adresse/elevage-[^/]+/[^/]+-\d+\.php$")
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if profile_re.search(href):
            full = href if href.startswith("http") else BASE + "/" + href.lstrip("/")
            urls.append(full)
    return list(dict.fromkeys(urls))


def fetch_profile(url: str):
    """Extrait les infos d'un eleveur depuis sa page profil.

    Retourne un dict avec toutes les infos disponibles, ou None si la race
    n'est pas dans SLUG_TO_RACE ou si la page est invalide.
    """
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
    text = soup.get_text(" ")

    # Nom
    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else ""
    if not name:
        return None

    # --- Telephone (monde francophone: FR, BE, CH, CA, LU, MC, DOM-TOM...) ---
    phone = ""
    text_clean = text.replace("\xa0", " ")

    # Pattern unique : tous les formats de numéros internationaux
    # +XX, 00XX, ou numéro local
    m = re.search(r"""
        (?:
            \+33[\s.\-]?\d[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2} |  # France +33
            \+590[\s.\-]?\d{3}[\s.\-]?\d{2}[\s.\-]?\d{2} |  # Guadeloupe
            \+596[\s.\-]?\d{3}[\s.\-]?\d{2}[\s.\-]?\d{2} |  # Martinique
            \+594[\s.\-]?\d{3}[\s.\-]?\d{2}[\s.\-]?\d{2} |  # Guyane
            \+262[\s.\-]?\d{3}[\s.\-]?\d{2}[\s.\-]?\d{2} |  # Réunion
            \+687[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2} |  # Nouvelle-Calédonie
            \+689[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2} |  # Polynésie
            \+32[\s.\-]?\d{1,3}[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2} |  # Belgique
            \+41[\s.\-]?\d{2}[\s.\-]?\d{3}[\s.\-]?\d{2}[\s.\-]?\d{2} |  # Suisse
            \+352[\s.\-]?\d{2,3}[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2} |  # Luxembourg
            \+377[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2} |  # Monaco
            \+376[\s.\-]?\d{2,3}[\s.\-]?\d{2}[\s.\-]?\d{2} |  # Andorre
            \+1[\s.\-]?\d{3}[\s.\-]?\d{3}[\s.\-]?\d{4} |  # Canada/US
            \b0[1-9](?:[\s.\-]?\d{2}){4}\b |  # France local
            \b04(?:[\s.\-]?\d{2}){4}\b  # Belgique local
        )
    """, text_clean, re.VERBOSE)

    if m:
        phone = m.group(0).strip(" -.")
    else:
        # Fallback: tout pattern qui ressemble a un telephone (7+ chiffres)
        m2 = re.search(r"\d{3}[\s.\-]\d{3}[\s.\-]\d{4}", text_clean)
        if m2:
            phone = m2.group(0).strip(" -.")

    # --- Email ---
    email = ""
    mailto = re.search(r'mailto:([^"\']+)', r.text)
    if mailto:
        email = mailto.group(1).strip()
    if not email:
        emails_found = re.findall(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", r.text
        )
        # Filtrer les emails du site chien.com
        real_emails = [
            e for e in emails_found
            if "chien.com" not in e and "example" not in e
        ]
        if real_emails:
            email = real_emails[0]

    # --- Site web ---
    website = ""
    site_links = soup.select('a[href*="/t/out-"]')
    if site_links:
        website = site_links[0].get("href", "")
        if website and not website.startswith("http"):
            website = BASE + website

    # --- SIREN ---
    siren = ""
    siren_m = re.search(r"SIREN\s*[:\xa0]+\s*(\d{9})", text)
    if siren_m:
        siren = siren_m.group(1)

    # --- ACACED / Certificat de capacite ---
    acaced = ""
    acaced_m = re.search(r"Certificat de capacit[ée]\s*[:\xa0]+\s*([^\s<]+)", text)
    if acaced_m:
        acaced = acaced_m.group(1).strip()

    # --- Statut (Pro / Particulier) ---
    statut = ""
    statut_m = re.search(r"Statut\s*[:\xa0]+\s*([^\s<]+)", text)
    if statut_m:
        statut = statut_m.group(1).strip()

    # --- Ville et code postal ---
    ville = ""
    code_postal = ""
    ville_m = re.search(r"Ville\s*[:\xa0]+\s*(\d{5})\s*[:\xa0]+\s*(\S+)", text)
    if ville_m:
        code_postal = ville_m.group(1)
        ville = ville_m.group(2)
    else:
        ville_m2 = re.search(r"Ville\s*[:\xa0]+\s*(\d{5})", text)
        if ville_m2:
            code_postal = ville_m2.group(1)

    # --- Departement via le breadcrumb ---
    departement = ""
    breadcrumb = soup.select_one("#breadcrumb")
    if breadcrumb:
        links = breadcrumb.select("a")
        for link in links:
            link_text = link.get_text(strip=True)
            if "-Savoie" in link_text or "-et-" in link_text or link_text.endswith("s"):
                departement = link_text

    # --- Description ---
    description = ""
    desc_div = soup.find(id="adresse_introduction")
    if desc_div:
        description = desc_div.get_text(" ", strip=True)
        description = re.sub(r"\s+", " ", description)

    # --- Photo principale ---
    photo_url = ""
    main_img = soup.select_one(
        'a[href*="upload.chien.com/img/"] img[src*="upload.chien.com/img/"]'
    )
    if main_img:
        src = main_img.get("src", "")
        if src:
            photo_url = src if src.startswith("http") else BASE + "/" + src.lstrip("/")

    return {
        "name": name,
        "races": [race],
        "phone": phone,
        "email": email,
        "website": website,
        "siren": siren,
        "acaced": acaced,
        "statut": statut,
        "ville": ville,
        "code_postal": code_postal,
        "departement": departement,
        "description": description,
        "photo_url": photo_url,
        "source_url": url,
    }


def fetch_profile_ai(url: str) -> dict | None:
    """
    Extrait les infos d'un profil via DeepSeek V4 Flash (OpenRouter).
    Plus robuste que les regex, detecte tous les formats de telephone.
    Fallback vers fetch_profile() si l'appel API echoue.
    """
    import os, json

    # Cle API OpenRouter
    key = ""
    for fp in [os.path.expanduser("~/.hermes/.env"), "/workspace/templates/.env"]:
        for line in open(fp):
            if "ANTHROPIC_API_KEY" in line and "=" in line:
                key = line.split("=", 1)[1].strip()
                if key: break
        if key: break

    if not key:
        return fetch_profile(url)

    r = _get(url)
    if not r:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)[:4000]  # 4000 chars suffisent

    prompt = f"""Extrais les informations de cet élevage canin au format JSON.

Page HTML :
{text}

Réponds UNIQUEMENT avec un JSON valide (pas de texte autour) :
{{
  "name": "nom élevage",
  "races": ["race principale"],
  "phone": "téléphone",
  "email": "email",
  "website": "site web",
  "siren": "SIREN ou numéro entreprise",
  "acaced": "numéro ACACED ou CCC",
  "statut": "Pro ou Particulier",
  "ville": "ville",
  "code_postal": "code postal",
  "departement": "département ou région",
  "description": "description complète"
}}"""

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek/deepseek-v4-flash",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
            },
            timeout=30,
        )
        data = resp.json()
        if "choices" not in data:
            return fetch_profile(url)

        content = data["choices"][0]["message"]["content"]
        # Extraire le JSON
        import re
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if not m:
            return fetch_profile(url)

        parsed = json.loads(m.group(0))

        # Ajouter photo et source
        main_img = soup.select_one("img[src*='upload.chien.com'], img[src*='chien.com/img']")
        parsed["photo_url"] = main_img["src"] if main_img else ""

        # Nettoyer le telephone
        phone = parsed.get("phone", "") or ""
        phone = re.sub(r"[^\d+\-\s\.]", "", phone).strip()
        parsed["phone"] = phone

        parsed["source_url"] = url
        return parsed

    except Exception as e:
        print(f"  ⚠️ AI scraper error: {e}, fallback regex")
        return fetch_profile(url)


def scrape(
    pages: int = 5, max_results: int = 10, start_page: int = 1
) -> list[dict]:
    """
    Scrape `pages` pages de listing et retourne jusqu'a `max_results` profils
    correspondant aux races connues.

    Args:
        pages: Nombre de pages de listing a parcourir
        max_results: Nombre max de profils a retourner
        start_page: Page de depart (utilise pour reprendre la ou on s'est arrete)

    Retourne une liste de dicts tries par page (les plus recents d'abord).
    """
    results = []
    for page in range(start_page, start_page + pages):
        profile_urls = fetch_listing_page(page)
        for url in profile_urls:
            if len(results) >= max_results:
                break
            profile = fetch_profile(url)
            if profile and profile.get("phone"):
                results.append(profile)
            time.sleep(DELAY)
        if len(results) >= max_results:
            break
        time.sleep(2)
    return results
