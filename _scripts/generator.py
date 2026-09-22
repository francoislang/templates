import re
import subprocess
import unicodedata
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

import config
from cloudinary_check import BREED_TEMPLATE, get_photos_for_breed
from photos import get_photos_for_race


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


# Un segment de transformation Cloudinary : "q_auto", "f_auto", "w_600,c_fill"...
_TRANSFO = re.compile(r"^[a-z]{1,3}_[^/]+(?:,[a-z]{1,3}_[^/]+)*$")


def cld(url, width=900, crop="fill", gravity="auto", height=None):
    """Redimensionne une image Cloudinary a la volee, via son URL.

    Sans transformation de largeur, Cloudinary sert l'original : les photos
    scrapees font souvent 2000 a 5000 px pour une vignette affichee a 300 px.
    Une galerie de 15 photos pesait ainsi plusieurs dizaines de megaoctets.

    Les transformations deja presentes en tete d'URL sont remplacees et non
    empilees, pour rester idempotent si le filtre est applique deux fois.
    Une URL non-Cloudinary est renvoyee telle quelle.
    """
    if not url or "res.cloudinary.com" not in url or "/image/upload/" not in url:
        return url

    prefix, reste = url.split("/image/upload/", 1)
    segments = reste.split("/")
    while segments and _TRANSFO.match(segments[0]):
        segments.pop(0)
    chemin = "/".join(segments)
    if not chemin:
        return url

    transfo = ["f_auto", "q_auto", f"w_{int(width)}"]
    if height:
        transfo.append(f"h_{int(height)}")
    if crop:
        transfo.append(f"c_{crop}")
        if crop in ("fill", "thumb", "lfill"):
            transfo.append(f"g_{gravity}")
    return f"{prefix}/image/upload/{','.join(transfo)}/{chemin}"


def make_env() -> Environment:
    """Environnement Jinja commun aux deux points d'entree du generateur."""
    env = Environment(
        loader=FileSystemLoader(str(config.REPO_ROOT / "_templates")),
        autoescape=False,
    )
    env.filters["cld"] = cld
    return env


def generate_from_config(config_path: str):
    """
    Génère un site HTML à partir d'un fichier YAML de configuration.
    Utilise data["template"] pour choisir le fichier .html.j2.
    Retourne (slug, github_pages_url) ou None si le template est introuvable.
    """
    with open(config_path) as f:
        data = yaml.safe_load(f)

    template_name = data.get("template")
    if not template_name:
        return None
    template_file = f"{template_name}.html.j2"
    if not (config.REPO_ROOT / "_templates" / template_file).exists():
        return None

    tmpl = make_env().get_template(template_file)
    html = tmpl.render(**data)

    slug = slugify(data["elevage"]["nom"])
    target = config.REPO_ROOT / slug
    target.mkdir(exist_ok=True)
    (target / "index.html").write_text(html, encoding="utf-8")

    subprocess.run(
        ["git", "-C", str(config.REPO_ROOT), "add", f"{slug}/index.html"],
        check=True,
        capture_output=True,
    )

    github_url = (
        f"https://{config.GITHUB_REPO.split('/')[0]}.github.io"
        f"/{config.GITHUB_REPO.split('/')[1]}/{slug}"
    )
    return slug, github_url


def _truncate_sentences(text: str, max_chars: int) -> str:
    """Coupe au max_chars en respectant les fins de phrases."""
    if not text or len(text) <= max_chars:
        return text
    chunk = text[:max_chars]
    last_dot = max(chunk.rfind(". "), chunk.rfind(".\n"))
    if last_dot > max_chars // 2:
        return chunk[:last_dot + 1].strip()
    last_space = chunk.rfind(" ")
    if last_space > 0:
        return chunk[:last_space].strip() + "…"
    return chunk.strip()


def clean_description(desc: str) -> str:
    """Nettoie une description : enleve les troncatures visibles."""
    if not desc:
        return ""
    desc = desc.strip()
    desc = re.sub(r"\bc\.\s*$", "", desc)      # finit par "c."
    desc = re.sub(r"\.{3,}$", "", desc)          # finit par "..."
    desc = re.sub(r"\betc\.?\s*$", "", desc)     # finit par "etc."
    desc = re.sub(r"\s{2,}", " ", desc).strip(" .,")
    if len(desc) < 30:
        return ""
    return desc


_BREED_COLORS = {
    "Carlin": {"primaire": "#8B5A3A", "accent": "#D4A76A", "fond": "#FAF3E8"},
    "Berger Australien": {"primaire": "#2D5A3D", "accent": "#C4A35A", "fond": "#F5F0E8"},
    "Shiba Inu": {"primaire": "#C0392B", "accent": "#F0C040", "fond": "#FDF8F0"},
    "Golden Retriever": {"primaire": "#3B2F1E", "accent": "#B07D1E", "fond": "#FDF9F0"},
    "Bouledogue Francais": {"primaire": "#4A3728", "accent": "#C4956A", "fond": "#F7F0E8"},
    "Border Collie": {"primaire": "#1A5276", "accent": "#85C1E9", "fond": "#F0F4F8"},
    "Cavalier King Charles": {"primaire": "#6B3A5A", "accent": "#E8B4C8", "fond": "#FDF5F8"},
    "Pomsky": {"primaire": "#5D4037", "accent": "#A1887F", "fond": "#F5F0EB"},
    "Berger Allemand": {"primaire": "#4E342E", "accent": "#BF8F6B", "fond": "#F5F0E8"},
    "Labrador Retriever": {"primaire": "#2E4053", "accent": "#5DADE2", "fond": "#F0F5FA"},
    "Husky": {"primaire": "#2C3E50", "accent": "#85C1E9", "fond": "#F0F5FA"},
    "Cane Corso": {"primaire": "#1B1B1B", "accent": "#8B4513", "fond": "#F0ECE6"},
    "Chihuahua": {"primaire": "#8B4513", "accent": "#DEB887", "fond": "#FFF8F0"},
    "Rhodesian Ridgeback": {"primaire": "#8B2500", "accent": "#D2691E", "fond": "#FDF5E6"},
    "Yorkshire Terrier": {"primaire": "#4A6741", "accent": "#8FBC8F", "fond": "#F5FAF0"},
    "Bichon Frise": {"primaire": "#3A3340", "accent": "#8E6C88", "fond": "#FCFAFB"},
    "Rottweiler": {"primaire": "#1A1A2E", "accent": "#B8860B", "fond": "#F0ECE6"},
    "Beagle": {"primaire": "#2F2A24", "accent": "#A0561F", "fond": "#FAF6F0"},
    "Loulou de Pomeranie": {"primaire": "#3A2E26", "accent": "#B96A28", "fond": "#FDF8F2"},
    "Schnauzer": {"primaire": "#36454F", "accent": "#C0C0C0", "fond": "#F0F0F0"},
    "West Highland White Terrier": {"primaire": "#2E3A33", "accent": "#6B5B7B", "fond": "#FBFAF7"},
    "Berger Blanc Suisse": {"primaire": "#243642", "accent": "#5E7F94", "fond": "#F6F8F9"},
    "Akita Inu": {"primaire": "#3B2415", "accent": "#B2661A", "fond": "#FFF8E7"},
    "American Bully": {"primaire": "#2F1B0E", "accent": "#8B4513", "fond": "#F5ECE6"},
    "Malinois": {"primaire": "#2B2621", "accent": "#6E7A3C", "fond": "#F6F3EC"},
}


DEFAUT_COULEURS = {"primaire": "#1B3A4B", "accent": "#D4622A", "fond": "#F7F4EF"}


def _luminance(hexa: str) -> float:
    c = [int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contraste(a: str, b: str) -> float:
    """Rapport de contraste WCAG entre deux couleurs (1 = identique, 21 = max)."""
    l1, l2 = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def palette_lisible(c: dict) -> bool:
    """La primaire sert d'encre : elle doit trancher franchement sur le fond.

    Une palette calquee sur le pelage du chien donnait du blanc sur blanc
    pour le Berger Blanc Suisse (contraste 1,17) — le site etait illisible.

    Seule l'encre est bloquante. L'accent sert a des titres decoratifs en
    grande taille et a des degrades : plusieurs palettes existantes l'ont
    volontairement discret (or sur creme), et les rejeter reviendrait a
    uniformiser des sites qui fonctionnent bien.
    """
    try:
        return contraste(c["primaire"], c["fond"]) >= 4.5
    except Exception:
        return False


def _breed_colors(race: str) -> dict:
    for key in _BREED_COLORS:
        if key.lower() in race.lower():
            c = _BREED_COLORS[key]
            if palette_lisible(c):
                return c
            print(f"  WARNING palette '{key}' illisible "
                  f"(contraste {contraste(c['primaire'], c['fond']):.2f}) "
                  f"— repli sur la palette par defaut")
            return DEFAUT_COULEURS
    return DEFAUT_COULEURS


def generate_site(name: str, race: str, phone: str, city: str = "",
                  website: str = "", description: str = "",
                  siren: str = "", departement: str = "",
                  photo_url: str = "",
                  photos_race: list[str] = None) -> tuple | None:
    """Genere un site vitrine via Jinja2 avec les donnees du scraper."""
    # Le template est toujours universal.html.j2
    template_file = "universal.html.j2"
    if not (config.REPO_ROOT / "_templates" / template_file).exists():
        return None

    slug = slugify(name)
    target_dir = config.REPO_ROOT / slug
    target_dir.mkdir(exist_ok=True)
    target_file = target_dir / "index.html"

    if target_file.exists():
        # Forcer la regeneration pour mettre a jour la description
        pass

    ph = photos_race if photos_race is not None else (get_photos_for_breed(race) or get_photos_for_race(race, count=15))
    couleurs = _breed_colors(race)
    data = {
        "template": "universal",
        "elevage": {
            "nom": name, "race": race,
            # Le pixel de comptage a besoin du slug pour distinguer les demos.
            "slug": slugify(name),
            "departement": departement or city or "",
            "region": departement or city or "",
            "code_postal": "", "telephone": phone,
            "siren": siren or "", "url": website or "",
            "facebook": "", "facebook_label": "", "since": "",
            "description_seo": (_truncate_sentences(description, 150) if description else f"Elevage {name} de {race}"),
            "description_hero": (_truncate_sentences(description, 300) if description else f"Elevage {name} — {race}"),
            "description_about": description or "",
        },
        "couleurs": couleurs,
        "photos": {
            "hero":    ph[0] if ph else "",
            "og":      ph[0] if ph else "",
            "about_1": ph[1] if len(ph) > 1 else (ph[0] if ph else ""),
            "about_2": ph[2] if len(ph) > 2 else "",
            "race":    ph[3] if len(ph) > 3 else (ph[0] if ph else ""),
            "galerie": ph[4:] if len(ph) > 4 else [],
        },
        "reproducteurs": [], "temoignages": [],
    }

    # Rendre le template Jinja2
    tmpl = make_env().get_template(template_file)
    html = tmpl.render(**data)

    target_file.write_text(html, encoding="utf-8")

    # Stage dans git
    import subprocess
    subprocess.run(
        ["git", "-C", str(config.REPO_ROOT), "add", f"{slug}/index.html"],
        check=True, capture_output=True,
    )

    github_url = (
        f"https://{config.GITHUB_REPO.split('/')[0]}.github.io"
        f"/{config.GITHUB_REPO.split('/')[1]}/{slug}"
    )
    return slug, github_url