#!/usr/bin/env python3
"""Le mail Kerr (R7, valide le 10/11/2026) et sa relance J+7, en HTML + texte.

    premier(p, metier, demo_url, capture_url) -> Mail(objet, preheader, texte, html)
    relance(p, metier, demo_url, capture_url) -> Mail

Contenu : accroche du metier (_templates/mail/accroches.json, version « sans »
ou « avec » site, variante de saison), 3 chiffres de la famille (stats_mail.py),
prix, bouton « Parlons-en » vers MAIL_LIEN_RDV. Gabarits : _templates/mail/*.j2.

    .venv/bin/python _scripts/mail_kerr.py --apercu boucherie [--avec-site] [--mois 11] [--relance]
    .venv/bin/python _scripts/mail_kerr.py --test      # brouillon adresse a toi seul
"""
from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402,F401  (charge le .env)
import stats_mail  # noqa: E402

import jinja2  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "_templates" / "mail"
CACHE_ASSETS = RACINE / "_data" / "mail_assets.json"
PAGES = "https://francoislang.github.io/templates"
LIEN_RDV_DEFAUT = "https://calendar.app.google/Gfv8vG91cPcGQ78H9"
INTRO_FIXE = "Bonjour, je suis François Lang, développeur web. "
IMAGES = {"bandeau": "kerr-bandeau.jpg", "photo": "francois.jpg", "logo": "kerr-signature.png"}
PETITS_MOTS = {"de", "du", "des", "la", "le", "les", "et", "à", "au", "aux", "en", "sur", "chez", "d", "l"}
SIGLES = {"SARL", "EURL", "SAS", "SASU", "SA", "EI", "SNC", "GAEC", "EARL", "SCEA", "EIRL", "BTP", "TP"}

GENERIQUE = {
    "sans": dict(objet="Une maquette de site pour {nom}", titre=["Votre site, ", "déjà prêt à regarder."],
                 intro="Voici une **maquette de site à votre nom**, sans engagement."),
    "avec": dict(objet="Une nouvelle version du site de {nom}", titre=["Une nouvelle version ", "de votre site."],
                 intro="Voici une **nouvelle version de votre site**, sans engagement."),
}


class Mail(NamedTuple):
    objet: str
    preheader: str
    texte: str
    html: str


# ------------------------------------------------------------------ typographie

def fr(s: str) -> str:
    s = re.sub(r" ([:;?!»])", r"&nbsp;\1", s)
    s = s.replace("« ", "«&nbsp;").replace("≈ ", "≈&nbsp;")
    s = re.sub(r"(\d) (€|%|km|m\b|min|avis)", r"\1&nbsp;\2", s)
    s = re.sub(r"(\d) (\d{3})", r"\1&nbsp;\2", s)
    s = re.sub(r"(\d) h\b", r"\1&nbsp;h", s)
    s = re.sub(r"(\d) × (\d)", r"\1&nbsp;×&nbsp;\2", s)
    s = re.sub(r"(\d) (semaines?|jours?|mois)\b", r"\1&nbsp;\2", s)
    return re.sub(r" sur (\d+)\b", r"&nbsp;sur&nbsp;\1", s)


def T(s: str) -> str:
    """Texte brut -> HTML echappe, espaces insecables."""
    return fr(_html.escape(s or "", quote=False))


def M(s: str, strong: str = "") -> str:
    """**gras** -> <strong{strong}>, le reste echappe."""
    out, pos = [], 0
    for m in re.finditer(r"\*\*(.+?)\*\*", s or ""):
        out.append(T(s[pos:m.start()]))
        out.append(f"<strong{strong}>{T(m.group(1))}</strong>")
        pos = m.end()
    out.append(T((s or "")[pos:]))
    return "".join(out)


def sans_gras(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s or "")


# ------------------------------------------------------------------ donnees

def nom_propre(nom: str) -> str:
    """« BOUCHERIE DUPONT & FILS » -> « Boucherie Dupont & Fils » ; casse mixte laissee telle quelle."""
    nom = re.sub(r"\s+", " ", (nom or "").strip())
    lettres = [c for c in nom if c.isalpha()]
    if not lettres or any(c.islower() for c in lettres):
        return nom
    mots = []
    for i, mot in enumerate(nom.split(" ")):
        if mot in SIGLES:
            mots.append(mot)
            continue
        morceaux = re.split(r"(['’\-])", mot.lower())
        res = []
        for j, x in enumerate(morceaux):
            if x in ("'", "’", "-") or not x:
                res.append(x)
            elif (i > 0 or j > 0) and x in PETITS_MOTS and j + 1 < len(morceaux) and morceaux[j + 1] in ("'", "’"):
                res.append(x)                       # d'..., l'... en milieu de nom
            elif i > 0 and j == 0 and x in PETITS_MOTS and len(morceaux) == 1:
                res.append(x)
            else:
                res.append(x[:1].upper() + x[1:])
        mots.append("".join(res))
    return " ".join(mots)


def _normaliser(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


_ACCROCHES: dict | None = None


def accroches() -> dict:
    global _ACCROCHES
    if _ACCROCHES is None:
        _ACCROCHES = {a["cle"]: a for a in json.loads((DOSSIER / "accroches.json").read_text(encoding="utf-8"))}
    return _ACCROCHES


def famille(metier: str) -> str:
    try:
        import metiers
        for m in metiers.CATALOGUE:
            if m.cle == metier:
                return m.famille
    except Exception:
        pass
    return _normaliser((accroches().get(metier) or {}).get("famille", ""))


def a_un_site(p: dict) -> bool:
    return p.get("site_statut") == "propre" and bool((p.get("site_web") or "").strip())


def accroche(p: dict, metier: str, mois: int | None = None) -> dict:
    """objet, titre [blanc, orange], intro (avec **gras**) pour ce prospect."""
    situ = "avec" if a_un_site(p) else "sans"
    a = accroches().get(metier) or {}
    base = dict(GENERIQUE[situ])
    s = a.get(situ) or {}
    if s.get("objet") and s.get("titre") and s.get("intro"):
        base = dict(objet=s["objet"], titre=list(s["titre"]), intro=s["intro"])
    sai = a.get("saison") or {}
    if sai and (mois or date.today().month) in (sai.get("mois") or []) and sai.get("objet") and sai.get("titre"):
        base["objet"], base["titre"] = sai["objet"], list(sai["titre"])
    nom, ville = nom_propre(p.get("nom") or ""), (p.get("commune") or "").strip()

    def remplir(t: str) -> str:
        t = t.replace("{nom}", nom or "votre entreprise").replace("{ville}", ville or "chez vous")
        return re.sub(r"\{[a-z_]+\}", "", t).strip()
    base["objet"] = remplir(base["objet"])
    base["titre"] = [remplir(base["titre"][0]) + " ", remplir(base["titre"][1])]
    base["titre"][0] = re.sub(r"\s+$", " ", base["titre"][0])
    base["intro"] = remplir(base["intro"])
    base["situation"] = situ
    return base


def origine_adresse(p: dict) -> str:
    """D'ou vient l'adresse (CNIL), une phrase courte pour le pied de page."""
    src = (p.get("mail_source") or "").strip()
    if p.get("mail_cherche_at") and (src == "accueil" or src.startswith("/")):
        site = (p.get("site_web") or "").strip()
        return f"Adresse affichée sur votre site{f' ({site})' if site else ''}."
    return "Adresse trouvée sur OpenStreetMap (données publiques)."


def lien_rdv() -> str:
    return (os.environ.get("MAIL_LIEN_RDV") or "").strip() or LIEN_RDV_DEFAUT


def affiche(url: str) -> str:
    """Adresse lisible dans la barre du faux navigateur : hote/…/dernier-segment."""
    u = re.sub(r"^https?://", "", url or "").rstrip("/")
    morceaux = u.split("/")
    return f"{morceaux[0]}/…/{morceaux[-1]}" if len(morceaux) > 2 else u


def assets() -> dict[str, str]:
    """URL publiques du bandeau, de la photo et du logo (Cloudinary, une seule fois)."""
    try:
        cache = json.loads(CACHE_ASSETS.read_text())
    except Exception:
        cache = {}
    if all(cache.get(k) for k in IMAGES):
        return cache
    try:
        import photos
    except Exception:
        photos = None
    for k, f in IMAGES.items():
        if cache.get(k):
            continue
        url = photos.upload_fichier(DOSSIER / "img" / f, f"mails/kerr-{Path(f).stem}") if photos else None
        if url:
            url = url.replace("/image/upload/", "/image/upload/f_jpg,q_85/" if f.endswith(".jpg") else "/image/upload/f_png/")
            cache[k] = url
    try:
        CACHE_ASSETS.write_text(json.dumps(cache, indent=1))
    except Exception:
        pass
    # repli : les fichiers du repo servis par GitHub Pages
    return {k: cache.get(k) or f"{PAGES}/_templates/mail/img/{f}" for k, f in IMAGES.items()}


# ------------------------------------------------------------------ rendu

_ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(str(DOSSIER)),
                          autoescape=True, undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
CLAIR = ' style="color:#FAF8F5;"'
FONCE = ' class="ti" style="color:#17191E;"'


def _commun(p: dict, demo_url: str, capture_url: str | None) -> dict:
    nom = nom_propre(p.get("nom") or "") or "votre entreprise"
    return dict(nom=nom, demo_url=demo_url, demo_affiche=affiche(demo_url),
                capture_url=capture_url or "", origine=origine_adresse(p),
                lien_rdv=lien_rdv(), img=assets())


def _signature_texte() -> list[str]:
    return ["François Lang", "Développeur web · Kerr", "06 32 81 42 00 · kerr-studio.com"]


def _pied_texte(p: dict) -> list[str]:
    return ["--", "François-Frédéric Lang EI · Kerr · Malzéville (54) · SIRET 928 539 048 00019",
            origine_adresse(p) + " Pour ne plus recevoir de message, répondez simplement en le disant.",
            "Prix nets, TVA non applicable (art. 293 B du CGI)."]


def premier(p: dict, metier: str, demo_url: str, capture_url: str | None, mois: int | None = None) -> Mail:
    a = accroche(p, metier, mois)
    c = _commun(p, demo_url, capture_url)
    stats = [dict(titre_html=T(t), texte_html=M(x, FONCE), source_html=T(s))
             for t, x, s in stats_mail.pour(famille(metier))]
    pre = ("Une nouvelle version de votre site, déjà prête. Dès 1 200 €." if a["situation"] == "avec"
           else "Une maquette de site à votre nom, déjà prête. Dès 1 200 €.")
    html = _ENV.get_template("premier.html.j2").render(
        objet=a["objet"], preheader=pre, nom_kicker=c["nom"].upper(),
        titre1_html=T(a["titre"][0]), titre2_html=T(a["titre"][1]),
        intro_html=M(INTRO_FIXE + a["intro"], CLAIR), stats=stats, **c)
    texte = "\n".join([
        a["titre"][0] + a["titre"][1], "",
        "Bonjour, je suis François Lang, développeur web. " + sans_gras(a["intro"]), "",
        f"La maquette : {demo_url}", "",
        *[f"- {t} : {sans_gras(x)} ({s})" for t, x, s in stats_mail.pour(famille(metier))], "",
        "Dès 1 200 €, ou 3 × 400 €, puis 35 €/mois (hébergement, retouches), sans engagement.", "",
        f"La maquette vous plaît ? Parlons-en au téléphone : {lien_rdv()}",
        "Ou répondez avec l'heure qui vous arrange.", "",
        *_signature_texte(), "", *_pied_texte(p)])
    return Mail(a["objet"], pre, texte, html)


def relance(p: dict, metier: str, demo_url: str, capture_url: str | None, objet: str = "") -> Mail:
    c = _commun(p, demo_url, capture_url)
    phrase = f"Bonjour, je reviens vers vous une seule fois : la maquette préparée pour **{c['nom']}** est toujours en ligne."
    pre = "La maquette préparée pour vous est toujours en ligne."
    obj = objet or accroche(p, metier)["objet"]
    obj = obj if obj.lower().startswith("re:") else f"Re: {obj}"
    html = _ENV.get_template("relance.html.j2").render(
        objet=obj, preheader=pre, phrase_html=M(phrase, FONCE), **c)
    texte = "\n".join([sans_gras(phrase), "", f"La maquette : {demo_url}", "",
                       f"Parlons-en au téléphone : {lien_rdv()}",
                       "Ou répondez avec l'heure qui vous arrange.", "",
                       "Je ne vous relancerai pas après ce message.", "",
                       *_signature_texte(), "", *_pied_texte(p)])
    return Mail(obj, pre, texte, html)


def mots_visibles(html: str) -> int:
    """Mots lisibles avant la signature (preheader et balises exclus)."""
    corps = html.split("<!--SIGNATURE-->", 1)[0]
    corps = re.sub(r"(?s)<head.*?</head>|<!--.*?-->|<div style=\"display:none.*?</div>", " ", corps)
    corps = _html.unescape(re.sub(r"<[^>]+>", " ", corps))
    return sum(1 for w in corps.split() if re.search(r"\w", w))


# ------------------------------------------------------------------ CLI

def _exemple(metier: str, avec_site: bool) -> dict:
    return dict(nom="BOUCHERIE DUPONT & FILS" if metier == "boucherie" else f"{metier.title()} Exemple",
                commune="Nancy", email="exemple@example.com",
                site_statut="propre" if avec_site else "aucun",
                site_web="https://exemple.fr" if avec_site else "")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apercu", metavar="METIER")
    ap.add_argument("--avec-site", action="store_true")
    ap.add_argument("--mois", type=int)
    ap.add_argument("--relance", action="store_true")
    ap.add_argument("--sortie")
    ap.add_argument("--test", action="store_true", help="depose un brouillon adresse a toi seul")
    a = ap.parse_args()
    metier = a.apercu or "boucherie"
    p = _exemple(metier, a.avec_site)
    demo = f"{PAGES}/boucherie-de-geneve/"
    cap = os.environ.get("MAIL_CAPTURE_TEST") or f"{PAGES}/_templates/mail/img/kerr-bandeau.jpg"
    if a.test:
        try:
            import capture
            cap = capture.capturer(demo, "essai-boucherie-de-geneve") or cap
        except Exception as e:
            print(f"capture indisponible ({e}) : image de secours")
    m = relance(p, metier, demo, cap) if a.relance else premier(p, metier, demo, cap, a.mois)
    if a.test:
        import envoi_mail
        envoi_mail.deposer_brouillon(envoi_mail.construire(envoi_mail.ADRESSE, "[ESSAI] " + m.objet, m.texte, html=m.html))
        print(f"Brouillon « [ESSAI] {m.objet} » depose dans Gmail ({envoi_mail.ADRESSE}).")
        return
    sortie = Path(a.sortie or RACINE / "_data" / "tmp_apercu" / f"mail-{metier}{'-relance' if a.relance else ''}.html")
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(m.html, encoding="utf-8")
    print(f"Objet : {m.objet}\nMots visibles : {mots_visibles(m.html)} · {len(m.html.encode()) // 1024} Ko\n-> {sortie}")


if __name__ == "__main__":
    main()
