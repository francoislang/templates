#!/usr/bin/env python3
"""Site de demonstration pour n'importe quel metier du catalogue (metiers.py).

Equivalent de gabarit_fixe.py pour les metiers qui n'ont pas de gabarit de
reference dessine a la main : _templates/artisan.html.j2, rempli avec les
faits verifies du prospect, la famille du metier (palette, icone, etapes,
formulaire) et ses deux familles de prestations. Aucun appel au modele :
le site sort meme quand le credit IA est a zero.

Memes regles que partout ailleurs : telephone « 06 XX XX XX XX », rue
« XX rue de l'Exemple », aucun courriel, aucun avis, aucun tarif.

    html = remplir(fiche_publique, "plombier", slug)
"""
from __future__ import annotations

import html as _html
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))

import gabarit_fixe as gf      # noqa: E402  (horaires, lieux, departements)
import metiers                 # noqa: E402

from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
PALETTES = REPO_ROOT / "_templates" / "fiche-accueil"
PAGES = "https://francoislang.github.io/templates"
MASQUE_TEL = "06 XX XX XX XX"

_env = Environment(loader=FileSystemLoader(str(REPO_ROOT / "_templates")),
                   autoescape=select_autoescape(["html", "j2"]),
                   trim_blocks=True, lstrip_blocks=True)


class GabaritInattendu(RuntimeError):
    pass


# --------------------------------------------------------------------------
# gabarits par famille : _templates/familles/<famille>/
#   page.html.j2        la page (contrat de variables : familles/CONTRAT.md)
#   metiers.json        textes propres a chaque metier : {"_defaut": {...}, "<cle>": {...}}
#   illus/<cle>.html    illustration du hero dessinee pour ce metier (facultatif)
#   illus/_famille.html illustration neutre de la famille (secours)
# Sans page.html.j2 pour la famille, on retombe sur artisan.html.j2.

FAMILLES_DIR = REPO_ROOT / "_templates" / "familles"
_JOURS_LONGS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def gabarit_famille(famille: str) -> Path | None:
    f = FAMILLES_DIR / famille / "page.html.j2"
    return f if f.exists() else None


def _fusion(base: dict, sur: dict) -> dict:
    out = dict(base)
    for k, v in sur.items():
        out[k] = _fusion(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def profil_metier(famille: str, cle: str) -> dict:
    f = FAMILLES_DIR / famille / "metiers.json"
    if not f.exists():
        return {}
    d = json.loads(f.read_text(encoding="utf-8"))
    return _fusion(d.get("_defaut", {}), d.get(cle, {}))


def illustration(famille: str, cle: str, prof: dict) -> tuple[str, str]:
    """(html de l'illustration, nom retenu) : celle du metier, sinon celle que le
    profil designe, sinon la neutre de la famille."""
    d = FAMILLES_DIR / famille / "illus"
    for nom in (cle, prof.get("illus") or "", "_famille"):
        if nom and (d / f"{nom}.html").exists():
            return (d / f"{nom}.html").read_text(encoding="utf-8"), nom
    return "", ""


def _semaine(sem) -> list[dict]:
    """Les 7 jours, lundi d'abord, pour les gabarits qui dessinent leurs horaires."""
    out = []
    for i in range(7):
        cs = sem[i] if sem else []
        out.append({"jour": _JOURS_LONGS[i], "court": _JOURS_LONGS[i][:3],
                    "ouvert": bool(cs), "creneaux": [(a, b) for a, b in cs],
                    "texte": gf._creneaux(cs, "menuisier") if cs else "Fermé"})
    return out


def _palette(nom: str) -> str:
    f = PALETTES / f"couleur-{nom}.css"
    if not f.exists():
        return ""
    css = f.read_text(encoding="utf-8")
    m = re.search(r":root\s*\{[^}]*\}", css, re.S)
    return m.group(0) if m else ""


def _a_lieu(lieu: str) -> str:
    """« au salon », « à la boutique », « à l'atelier »."""
    if lieu.startswith("le "):
        return "au " + lieu[3:]
    if lieu.startswith("les "):
        return "aux " + lieu[4:]
    return "à " + lieu


def _ld(p: dict, m: metiers.Metier, slug: str, lx: dict, sem, desc: str) -> str:
    d = {"@context": "https://schema.org", "@type": m.schema,
         "name": p["nom"], "description": desc, "url": f"{PAGES}/{slug}/",
         "address": {"@type": "PostalAddress", "streetAddress": "XX rue de l'Exemple",
                     "addressCountry": "FR"}}
    if (p.get("telephone") or "").strip():
        d["telephone"] = MASQUE_TEL
    if lx["cp"]:
        d["address"]["postalCode"] = lx["cp"]
    if lx["commune"]:
        d["address"]["addressLocality"] = lx["commune"]
    elif lx["court"]:
        d["address"]["addressRegion"] = lx["court"]
    if sem:
        d["openingHoursSpecification"] = gf._ld_horaires(sem)
    d["makesOffer"] = [{"@type": "Offer", "itemOffered": {"@type": "Service", "name": t}}
                       for t, _ in m.presta[:2]]
    corps = json.dumps(d, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{corps}\n</script>'


def remplir(p: dict, metier: str, slug: str) -> str:
    """La page du metier, remplie avec la fiche publique `p` (deja anonymisee)."""
    m = metiers.PAR_CLE.get(metier)
    if m is None:
        raise GabaritInattendu(f"metier inconnu du catalogue : {metier!r}")
    nom = (p.get("nom") or "").strip()
    if not nom:
        raise GabaritInattendu("fiche sans nom")
    fam = m.fam
    lx = gf._lieux(p)
    sem = gf.lire_horaires(p.get("horaires") or "")
    r = gf._resume(sem, "menuisier") if sem else {}
    al = f" {lx['a_lieu']}" if lx["a_lieu"] else ""
    itin = (f"https://www.google.com/maps/dir/?api=1&destination={quote(lx['cp_commune'])}"
            if lx["cp_commune"] else "#contact")
    desc = (f"{nom}, {m.nom.lower()}{al}. "
            f"{m.presta[0][0]} et {m.presta[1][0].lower()}.")
    from markupsafe import Markup
    tpl = gabarit_famille(m.famille)
    prof = profil_metier(m.famille, m.cle) if tpl else {}
    illus, illus_nom = illustration(m.famille, m.cle, prof) if tpl else ("", "")
    nom_tpl = f"familles/{m.famille}/page.html.j2" if tpl else "artisan.html.j2"
    page = _env.get_template(nom_tpl).render(
        prof=prof, illus=Markup(illus), illus_nom=illus_nom,
        commune=lx["commune"], semaine=_semaine(sem),
        N=nom, m=m, fam=fam, al=al, lieu=fam["lieu"], a_lieu_etab=_a_lieu(fam["lieu"]),
        court=lx["court"], cp=lx["cp"], cpc=lx["cp_commune"], itin=itin,
        sem=bool(sem), r=r, data_h=gf._data_h(sem) if sem else "",
        table_html=Markup(gf._table(sem, "menuisier", False)) if sem else "",
        ld_json=Markup(_ld(p, m, slug, lx, sem, desc)),
        palette_css=Markup(_palette(m.palette(slug))),
        a_tel=bool((p.get("telephone") or "").strip()), tel=MASQUE_TEL,
        description=desc, annee=date.today().year,
        nom_js=Markup(json.dumps(nom, ensure_ascii=False).replace("</", "<\\/")),
    )
    if "{{" in page or "{%" in page:
        raise GabaritInattendu("balise Jinja non resolue")
    return page


if __name__ == "__main__":
    import argparse
    a = argparse.ArgumentParser()
    a.add_argument("metier")
    a.add_argument("--nom", default="Atelier Exemple")
    a.add_argument("--commune", default="Malzéville")
    a.add_argument("--cp", default="54220")
    a.add_argument("--horaires", default="Mo-Fr 08:30-12:00,14:00-18:30; Sa 09:00-12:00")
    a.add_argument("--sortie", default=None)
    x = a.parse_args()
    fiche = {"nom": x.nom, "commune": x.commune, "code_postal": x.cp, "departement": x.cp[:2],
             "horaires": x.horaires, "telephone": "06 XX XX XX XX"}
    html = remplir(fiche, x.metier, gf._slug_modele("menuisier") if False else "apercu")
    if x.sortie:
        Path(x.sortie).write_text(html, encoding="utf-8")
        print(x.sortie)
    else:
        print(html[:500])
