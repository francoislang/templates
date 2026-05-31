"""
Scraper de photos d'animaux — cherche des images 4K pour n'importe quelle race/mot-cle.
Utilise Pexels (API gratuite) + Unsplash + DuckDuckGo en fallback.

Usage:
    python _scripts/photos.py --search "Berger Allemand"
    python _scripts/photos.py --search "Shiba Inu" --count 5
    python _scripts/photos.py --search "chat persan"
    python _scripts/photos.py --list-sources   # liste les sources disponibles
    python _scripts/photos.py --url-only       # juste les URLs, pas d'upload
"""
import os
import sys
import time
import json
import re
import urllib.parse
import requests

sys.path.insert(0, os.path.dirname(__file__))
import config

CLOUDINARY_UPLOAD_URL = (
    f"https://api.cloudinary.com/v1_1/{config.CLOUDINARY_CLOUD_NAME}/image/upload"
)

# Pexels API (gratuite, 200 req/h sans compte, beaucoup plus avec une cle)
PEXELS_API_KEY = config.PEXELS_API_KEY or ""
PIXABAY_API_KEY = config.PIXABAY_API_KEY or ""
UNSPLASH_ACCESS_KEY = config.UNSPLASH_ACCESS_KEY or ""


def search_pexels(query: str, count: int = 5) -> list[dict]:
    """
    Cherche des photos sur Pexels (API gratuite).
    Retourne une liste de {url, auteur, lien_pexels, largeur, hauteur}.
    """
    url = "https://api.pexels.com/v1/search"
    params = {
        "query": query,
        "per_page": min(count, 80),
        "orientation": "landscape",
        "size": "large",
    }
    headers = {"Authorization": PEXELS_API_KEY}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()

        results = []
        for photo in data.get("photos", []):
            src = photo.get("src", {})
            # Prendre la meilleure resolution : original > large > landscape
            img_url = (
                src.get("original")
                or src.get("large")
                or src.get("landscape")
                or src.get("medium")
            )
            if img_url:
                results.append({
                    "url": img_url,
                    "author": photo["photographer"],
                    "author_url": photo["photographer_url"],
                    "source_url": photo["url"],
                    "width": photo.get("width", 0),
                    "height": photo.get("height", 0),
                    "source": "pexels",
                })
        return results
    except Exception as e:
        print(f"  ⚠️ Pexels: {e}", file=sys.stderr)
        return []


def search_unsplash(query: str, count: int = 5) -> list[dict]:
    """
    Cherche des photos sur Unsplash (API sans cle pour le search basique).
    Fallback si Pexels ne donne rien.
    """
    # Unsplash permet des recherches sans cle via l'API publique (limite)
    # Mais c'est plus fiable avec une cle. On utilise le mode demo.
    try:
        # Methode: scraper la page de recherche Unsplash (pas d'API key needed)
        search_url = (
            "https://unsplash.com/napi/search/photos"
            f"?query={urllib.parse.quote(query)}"
            f"&per_page={min(count, 20)}"
            f"&orientation=landscape"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }
        r = requests.get(search_url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()

        results = []
        for photo in data.get("results", data.get("photos", {}).get("results", [])):
            urls = photo.get("urls", {})
            img_url = urls.get("raw") or urls.get("full") or urls.get("regular")
            if img_url:
                results.append({
                    "url": img_url,
                    "author": photo["user"]["name"],
                    "author_url": photo["user"]["links"]["html"],
                    "source_url": photo["links"]["html"],
                    "width": photo.get("width", 0),
                    "height": photo.get("height", 0),
                    "source": "unsplash",
                })
        return results
    except Exception as e:
        print(f"  ⚠️ Unsplash: {e}", file=sys.stderr)
        return []


def search_duckduckgo(query: str, count: int = 5) -> list[dict]:
    """
    Cherche des images via DuckDuckGo (pas d'API key necessaire).
    Fallback ultime — qualite variable.
    """
    try:
        url = "https://duckduckgo.com/i.js"
        params = {
            "q": query,
            "o": "json",
            "vqd": "4",
            "f": ",,,,,",
            "p": "1",
            "s": "0",
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36"
            ),
            "Referer": "https://duckduckgo.com/",
        }
        r = requests.get(url, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()

        results = []
        for img in data.get("results", [])[:count]:
            img_url = img.get("image") or img.get("thumbnail")
            if img_url:
                results.append({
                    "url": img_url,
                    "title": img.get("title", ""),
                    "source": "duckduckgo",
                    "source_url": img.get("url", ""),
                })
        return results
    except Exception as e:
        print(f"  ⚠️ DuckDuckGo: {e}", file=sys.stderr)
        return []


def search_pixabay(query: str, count: int = 5) -> list[dict]:
    """
    Cherche des photos sur Pixabay (API gratuite, 5000 req/h).
    Retourne une liste de {url, auteur, source}.
    """
    if not PIXABAY_API_KEY:
        return []

    url = "https://pixabay.com/api/"
    params = {
        "key": PIXABAY_API_KEY,
        "q": query,
        "per_page": min(count, 200),
        "image_type": "photo",
        "orientation": "horizontal",
        "min_width": 1920,
        "min_height": 1080,
        "safesearch": "true",
        "category": "animals",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        results = []
        for hit in data.get("hits", [])[:count]:
            img_url = hit.get("largeImageURL") or hit.get("webformatURL")
            if img_url:
                results.append({
                    "url": img_url,
                    "author": hit.get("user", "Pixabay"),
                    "source": "pixabay",
                })
        return results
    except Exception as e:
        print(f"  ⚠️ Pixabay: {e}", file=sys.stderr)
        return []


def search_images(query: str, count: int = 5, sources: list[str] = None) -> list[dict]:
    """
    Cherche des photos depuis plusieurs sources avec fallback.

    Args:
        query: Terme de recherche (ex: "Golden Retriever", "chat persan")
        count: Nombre de photos souhaite
        sources: Ordre des sources a essayer ["pexels", "unsplash", "duckduckgo"]

    Retourne une liste de dicts tries par qualite.
    """
    if sources is None:
        sources = ["pexels", "pixabay", "unsplash", "duckduckgo"]

    print(f"  🔍 Recherche de photos pour '{query}'...")
    all_results = []

    for source in sources:
        print(f"     -> Source: {source}")
        fn = {
            "pexels": search_pexels,
            "pixabay": search_pixabay,
            "unsplash": search_unsplash,
            "duckduckgo": search_duckduckgo,
        }.get(source)

        if not fn:
            continue

        results = fn(query, count=count)
        if results:
            all_results.extend(results[:count])
            # Si on a assez de resultats, on s'arrete
            if len(all_results) >= count:
                break
        time.sleep(1)  # Rate limiting entre les sources

    # Deduplication par URL
    seen = set()
    unique = []
    for r in all_results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    print(f"  ✅ {len(unique)} photos trouvees pour '{query}'")
    return unique[:count]


def upload_to_cloudinary(image_url: str, public_id: str, race: str = "") -> str | None:
    """
    Uploade une image vers Cloudinary via API signee.
    Utilise le dossier photo-{race} si fourni.
    """
    if not image_url or not config.CLOUDINARY_API_SECRET:
        return None

    import hashlib
    timestamp = int(time.time())
    
    # Dossier: photo-{race} par ex photo-carlin
    safe_race = re.sub(r"[^a-z0-9]+", "_", race.lower()).strip("_") if race else ""
    folder = f"photo-{safe_race}" if safe_race else ""
    
    # Signature de l'upload
    params = {
        "timestamp": timestamp,
        "public_id": public_id,
    }
    if folder:
        params["folder"] = folder
    
    sig_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    sig_str += config.CLOUDINARY_API_SECRET
    signature = hashlib.sha1(sig_str.encode()).hexdigest()
    
    data = {
        "file": image_url,
        "api_key": config.CLOUDINARY_API_KEY,
        "timestamp": timestamp,
        "public_id": public_id,
        "signature": signature,
    }
    if folder:
        data["folder"] = folder
    
    try:
        r = requests.post(CLOUDINARY_UPLOAD_URL, data=data, timeout=30)
        r.raise_for_status()
        result = r.json()
        url = result.get("secure_url") or result.get("url")
        # Ajouter les transformations q_auto/f_auto comme les autres photos
        if url and "/image/upload/" in url:
            url = url.replace("/image/upload/", "/image/upload/q_auto/f_auto/")
        return url
    except Exception as e:
        print(f"  ⚠️ Cloudinary upload: {e}", file=sys.stderr)
        return None


def get_photos_for_race(race: str, count: int = 15, force_refresh: bool = False) -> list[str]:
    """
    Recupere les photos pour une race.
    - Si la race a deja des photos sur Cloudinary -> les retourne
    - Sinon -> scrape depuis Pexels + upload sur Cloudinary

    Args:
        race: Nom de la race
        count: Nombre de photos souhaite (defaut: 15)
        force_refresh: Si True, rescrape meme si deja en Cloudinary

    Retourne une liste d'URLs Cloudinary.
    """
    # 1. Verifier si la race a deja des photos sur Cloudinary
    if not force_refresh:
        existing = get_cloudinary_photos_for_race(race)
        if existing:
            print(f"  ✅ {len(existing)} photos deja sur Cloudinary pour '{race}'")
            return existing[:count]

    # 2. Scraper depuis Pexels
    print(f"  📸 Aucune photo Cloudinary trouvee, scraping Pexels pour '{race}'...")
    images = search_images(race, count=count)

    if not images:
        print(f"  ❌ Aucune photo trouvee pour '{race}'")
        return []

    # 3. Uploader sur Cloudinary
    urls = []
    for i, img in enumerate(images[:count]):
        safe_race = re.sub(r"[^a-z0-9]+", "_", race.lower()).strip("_")
        public_id = f"{safe_race}_{i+1}"
        cloud_url = upload_to_cloudinary(img["url"], public_id, race=race)
        if cloud_url:
            urls.append(cloud_url)
            print(f"  ✅ [{i+1}/{count}] Uploadee: {cloud_url[:60]}...")
        else:
            urls.append(img["url"])
            print(f"  ⚠️ [{i+1}/{count}] Upload failed, URL directe")
        time.sleep(0.5)

    print(f"  ✅ {len(urls)} photos pretes pour '{race}'")
    return urls


def get_cloudinary_photos_for_race(race: str) -> list[str]:
    """
    Recupere les URLs Cloudinary d'une race deja uploadee.
    Verifie via l'API Cloudinary si des photos existent dans le dossier breeds/.
    """
    import hashlib
    safe_race = re.sub(r"[^a-z0-9]+", "_", race.lower()).strip("_")

    # Methode: chercher les photos via Cloudinary Admin API
    # Si CLOUDINARY_API_SECRET est defini, on peut chercher
    if not config.CLOUDINARY_API_SECRET:
        return []

    try:
        # Dans le dossier photo-{race}
        folder_name = f"photo-{safe_race}"
        test_url = (
            f"https://res.cloudinary.com/{config.CLOUDINARY_CLOUD_NAME}/"
            f"image/upload/q_auto/f_auto/{folder_name}/{safe_race}_1.jpg"
        )
        r = requests.head(test_url, timeout=5)
        if r.status_code == 200:
            # La race existe, construire les URLs
            urls = []
            for i in range(1, 16):
                url = (
                    f"https://res.cloudinary.com/{config.CLOUDINARY_CLOUD_NAME}/"
                    f"image/upload/q_auto/f_auto/{folder_name}/{safe_race}_{i}.jpg"
                )
                urls.append(url)
            # Verifier combien existent reellement
            existing_urls = []
            for url in urls:
                r2 = requests.head(url, timeout=3)
                if r2.status_code == 200:
                    existing_urls.append(url)
            return existing_urls
        return []
    except Exception as e:
        print(f"  ⚠️ Cloudinary check: {e}")
        return []


def get_photos(query: str, count: int = 5, upload: bool = False,
               sources: list[str] = None) -> list[str]:
    """
    Cherche des photos et retourne les URLs (soit Cloudinary, soit direct).

    Args:
        query: Terme de recherche
        count: Nombre de photos
        upload: Si True, uploade sur Cloudinary et retourne URLs Cloudinary
        sources: Liste des sources a utiliser

    Retourne une liste d'URLs.
    """
    images = search_images(query, count=count, sources=sources)

    if not images:
        print(f"  ❌ Aucune photo trouvee pour '{query}'")
        return []

    urls = []
    for i, img in enumerate(images[:count]):
        if upload:
            # Creer un public_id lisible
            safe_query = re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")
            public_id = f"{safe_query}_{i+1}"
            cloud_url = upload_to_cloudinary(img["url"], public_id)
            if cloud_url:
                urls.append(cloud_url)
                print(f"  ✅ [Cloudinary] {cloud_url}")
            else:
                # Fallback: URL directe
                urls.append(img["url"])
                print(f"  ⚠️ [Cloudinary failed] Fallback URL directe")
        else:
            urls.append(img["url"])
            print(f"  📷 [{img.get('source', '?')}] {img['url'][:80]}...")

    return urls


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Scraper de photos d'animaux (Pexels + Unsplash + DuckDuckGo)"
    )
    parser.add_argument("--search", "-s", help="Terme de recherche")
    parser.add_argument("--race", help="Nom de la race (verifie Cloudinary d'abord)")
    parser.add_argument("--count", "-c", type=int, default=3,
                        help="Nombre de photos (defaut: 3)")
    parser.add_argument("--upload", "-u", action="store_true",
                        help="Uploader sur Cloudinary")
    parser.add_argument("--sources", nargs="*",
                        default=["pexels", "unsplash", "duckduckgo"],
                        help="Sources dans l'ordre (pexels unsplash duckduckgo)")
    parser.add_argument("--list-sources", action="store_true",
                        help="Afficher les sources disponibles")
    parser.add_argument("--url-only", action="store_true",
                        help="Afficher seulement les URLs")

    args = parser.parse_args()

    if args.list_sources:
        print("Sources disponibles...")
        print("  pexels     - Photos professionnelles (API gratuite, 200 req/h)")
        print("  pixabay    - Photos libres de droit (API gratuite, 5000 req/h)")
        print("  unsplash   - Photos haute resolution")
        print("  duckduckgo - Fallback Internet")
        return

    if args.race:
        urls = get_photos_for_race(args.race, count=args.count)
        if args.url_only and urls:
            for url in urls:
                print(url)
        if not urls:
            print(f"\n❌ Aucune photo trouvee pour '{args.race}'")
        return

    if not args.search:
        parser.print_help()
        return

    urls = get_photos(
        query=args.search,
        count=args.count,
        upload=args.upload,
        sources=args.sources,
    )

    if args.url_only and urls:
        for url in urls:
            print(url)

    if not urls:
        print(f"\n❌ Aucune photo trouvee pour '{args.search}'")
        print("   Essayez d'autres mots-cles (anglais souvent mieux):")
        print(f"   python _scripts/photos.py --search \"{args.search} animal\"")


if __name__ == "__main__":
    main()
