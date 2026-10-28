#!/usr/bin/env python3
"""Site de demonstration SANS IA pour les marches pro (garage, menuisier).

C'est l'equivalent, pour pipeline_pro.py, du template universel des eleveurs
(generator.py + universal.html.j2) : quand le modele ne repond pas (credit
epuise, panne, page trop pauvre), on remplit le gabarit de reference avec les
faits verifies du prospect, sans rien inventer. Le site sort quand meme.

Le gabarit de reference est lu tel quel dans _templates/ : une retouche du
gabarit profite donc aussi a ce repli. Chaque remplacement est controle ; si
le gabarit a change au point qu'un repere manque, la fonction leve une
erreur plutot que de publier une page a moitie remplie, et un dernier
controle refuse toute trace de l'entreprise modele (nom, ville, code postal).

Ce qui est rempli : nom, commune, code postal, departement, horaires (format
OpenStreetMap), JSON-LD, adresse de la page. Le telephone, la rue et le
SIREN restent masques (06 XX XX XX XX, XX rue de l'Exemple) comme sur toute
maquette publiee.

    html = remplir(fiche, "menuisier", slug)
"""
from __future__ import annotations

import html as _html
import json
import re
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).parent.parent

GABARITS = {"garage": "reference-garage.html", "menuisier": "reference-menuisier.html"}
PAGES = "https://francoislang.github.io/templates"

# L'entreprise modele de chaque gabarit : rien de tout cela ne doit survivre.
MODELE = {
    "garage": {"nom": "Garage Patton", "ville": "Rennes", "cp": "35700",
               "traces": ("Patton", "Rennes", "35700", "Bretagne", "567923341")},
    "menuisier": {"nom": "Menuiserie Vautrin", "ville": "Nancy", "cp": "54000",
                  "traces": ("Vautrin", "Nancy", "54000")},
}

# Departements, avec la preposition qui convient (« en Meurthe-et-Moselle »,
# « dans le Doubs »), pour les fiches qui n'ont pas de commune.
DEPARTEMENTS = {
    "01": "dans l'Ain", "02": "dans l'Aisne", "03": "dans l'Allier",
    "04": "dans les Alpes-de-Haute-Provence", "05": "dans les Hautes-Alpes",
    "06": "dans les Alpes-Maritimes", "07": "en Ardèche", "08": "dans les Ardennes",
    "09": "en Ariège", "10": "dans l'Aube", "11": "dans l'Aude", "12": "en Aveyron",
    "13": "dans les Bouches-du-Rhône", "14": "dans le Calvados", "15": "dans le Cantal",
    "16": "en Charente", "17": "en Charente-Maritime", "18": "dans le Cher",
    "19": "en Corrèze", "2A": "en Corse-du-Sud", "2B": "en Haute-Corse",
    "21": "en Côte-d'Or", "22": "dans les Côtes-d'Armor", "23": "dans la Creuse",
    "24": "en Dordogne", "25": "dans le Doubs", "26": "dans la Drôme", "27": "dans l'Eure",
    "28": "en Eure-et-Loir", "29": "dans le Finistère", "30": "dans le Gard",
    "31": "en Haute-Garonne", "32": "dans le Gers", "33": "en Gironde", "34": "dans l'Hérault",
    "35": "en Ille-et-Vilaine", "36": "dans l'Indre", "37": "en Indre-et-Loire",
    "38": "en Isère", "39": "dans le Jura", "40": "dans les Landes", "41": "en Loir-et-Cher",
    "42": "dans la Loire", "43": "en Haute-Loire", "44": "en Loire-Atlantique",
    "45": "dans le Loiret", "46": "dans le Lot", "47": "en Lot-et-Garonne",
    "48": "en Lozère", "49": "en Maine-et-Loire", "50": "dans la Manche", "51": "dans la Marne",
    "52": "en Haute-Marne", "53": "en Mayenne", "54": "en Meurthe-et-Moselle",
    "55": "dans la Meuse", "56": "dans le Morbihan", "57": "en Moselle", "58": "dans la Nièvre",
    "59": "dans le Nord", "60": "dans l'Oise", "61": "dans l'Orne", "62": "dans le Pas-de-Calais",
    "63": "dans le Puy-de-Dôme", "64": "dans les Pyrénées-Atlantiques",
    "65": "dans les Hautes-Pyrénées", "66": "dans les Pyrénées-Orientales",
    "67": "dans le Bas-Rhin", "68": "dans le Haut-Rhin", "69": "dans le Rhône",
    "70": "en Haute-Saône", "71": "en Saône-et-Loire", "72": "dans la Sarthe",
    "73": "en Savoie", "74": "en Haute-Savoie", "75": "à Paris", "76": "en Seine-Maritime",
    "77": "en Seine-et-Marne", "78": "dans les Yvelines", "79": "dans les Deux-Sèvres",
    "80": "dans la Somme", "81": "dans le Tarn", "82": "en Tarn-et-Garonne", "83": "dans le Var",
    "84": "dans le Vaucluse", "85": "en Vendée", "86": "dans la Vienne", "87": "en Haute-Vienne",
    "88": "dans les Vosges", "89": "dans l'Yonne", "90": "dans le Territoire de Belfort",
    "91": "dans l'Essonne", "92": "dans les Hauts-de-Seine", "93": "en Seine-Saint-Denis",
    "94": "dans le Val-de-Marne", "95": "dans le Val-d'Oise",
    "971": "en Guadeloupe", "972": "en Martinique", "973": "en Guyane",
    "974": "à La Réunion", "976": "à Mayotte",
}


def _nom_dep(phrase: str) -> str:
    """« dans le Doubs » -> « Doubs », « en Isère » -> « Isère »."""
    return re.sub(r"^(?:dans (?:le |la |les |l')|en |à )", "", phrase)


# --------------------------------------------------------------------------
# horaires OpenStreetMap

_JOURS_OSM = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]          # lundi d'abord
_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_JOURS_COURTS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
_JOURS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def lire_horaires(osm: str) -> list[list[tuple[int, int]]] | None:
    """« Mo-Fr 08:00-12:00,14:00-18:00; Sa 08:00-12:00 » -> 7 jours (lundi
    d'abord) de creneaux en minutes. None si le texte n'est pas lisible :
    mieux vaut ne pas afficher d'horaires que d'en afficher de faux."""
    if not osm or not osm.strip():
        return None
    s = osm.strip().strip('"').strip()
    if s == "24/7":
        return [[(0, 1440)] for _ in range(7)]
    semaine: list[list[tuple[int, int]]] = [[] for _ in range(7)]
    vu = False
    for regle in [r.strip() for r in s.split(";") if r.strip()]:
        if re.fullmatch(r"PH\s+(?:off|closed)", regle, re.I):
            continue
        m = re.fullmatch(r"((?:[A-Z][a-z](?:-[A-Z][a-z])?)(?:\s*,\s*[A-Z][a-z](?:-[A-Z][a-z])?)*)"
                         r"(?:\s*,\s*PH)?\s+(.+)", regle)
        if not m:
            return None
        jours: list[int] = []
        for bloc in re.split(r"\s*,\s*", m.group(1)):
            bornes = bloc.split("-")
            if any(b not in _JOURS_OSM for b in bornes):
                return None
            a = _JOURS_OSM.index(bornes[0])
            b = _JOURS_OSM.index(bornes[-1])
            jours += list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
        reste = m.group(2).strip()
        if re.fullmatch(r"(?:off|closed)", reste, re.I):
            for j in jours:
                semaine[j] = []
            vu = True
            continue
        creneaux = []
        for c in re.split(r"\s*,\s*", reste):
            t = re.fullmatch(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", c)
            if not t:
                return None
            a = int(t.group(1)) * 60 + int(t.group(2))
            b = int(t.group(3)) * 60 + int(t.group(4))
            if not (0 <= a < b <= 1440):
                return None
            creneaux.append((a, b))
        for j in jours:
            semaine[j] = sorted(creneaux)
        vu = True
    if not vu or not any(semaine):
        return None
    return semaine


def _hm(v: int, style: str) -> str:
    h, m = divmod(v, 60)
    if style == "garage":
        return f"{h}h{m:02d}" if m else f"{h}h"
    return f"{h} h {m:02d}" if m else f"{h} h"


def _creneaux(cs, style: str, liaison: str = " · ") -> str:
    tiret = "–" if style == "garage" else " – "
    return liaison.join(f"{_hm(a, style)}{tiret}{_hm(b, style)}" for a, b in cs)


def _liste(mots: list[str]) -> str:
    return mots[0] if len(mots) == 1 else ", ".join(mots[:-1]) + " et " + mots[-1]


def _jours_ouverts(sem) -> str:
    """« Du lundi au vendredi », « Du lundi au samedi », « Les lundi et jeudi »."""
    ouv = [i for i in range(7) if sem[i]]
    if len(ouv) >= 2 and ouv == list(range(ouv[0], ouv[-1] + 1)):
        return f"Du {_JOURS[ouv[0]]} au {_JOURS[ouv[-1]]}"
    if len(ouv) == 1:
        return f"Le {_JOURS[ouv[0]]}"
    return "Les " + _liste([_JOURS[i] for i in ouv])


def _jours_fermes(sem) -> list[str]:
    return [_JOURS[i] for i in range(7) if not sem[i]]


def _resume(sem, style: str) -> dict:
    """Les petites phrases que les gabarits affichent autour du tableau."""
    ouv = [i for i in range(7) if sem[i]]
    # creneaux du jour le plus frequent : sert de ligne principale
    freq: dict = {}
    for i in ouv:
        freq.setdefault(tuple(sem[i]), []).append(i)
    principal = max(freq.items(), key=lambda kv: len(kv[1]))[0]
    autres = [i for i in ouv if tuple(sem[i]) != principal]
    exceptions = "; ".join(f"le {_JOURS[i]} {_creneaux(sem[i], style)}" for i in autres)
    fermes = _jours_fermes(sem)
    debut = min(cs[0][0] for cs in (sem[i] for i in ouv))
    fin = max(cs[-1][1] for cs in (sem[i] for i in ouv))
    pause = ""
    if len(principal) == 2:
        pause = f"Coupure de {_hm(principal[0][1], 'menuisier')} à {_hm(principal[1][0], 'menuisier')}"
    if fermes:
        txt_fermes = "Fermé le " + _liste(fermes) + " et les jours fériés"
    else:
        txt_fermes = "Ouvert tous les jours"
    ouv_c = [_JOURS_COURTS[i] for i in ouv]
    if len(ouv) >= 2 and ouv == list(range(ouv[0], ouv[-1] + 1)):
        court = f"{ouv_c[0].capitalize()}–{ouv_c[-1]}"
    else:
        court = ", ".join(ouv_c).capitalize()
    return {"jours": _jours_ouverts(sem), "principal": _creneaux(principal, style),
            "principal_et": _creneaux(principal, style, " et "), "exceptions": exceptions,
            "fermes": txt_fermes, "fermes_liste": fermes, "court": court,
            "debut": debut, "fin": fin, "pause": pause}


def _data_h(sem) -> str:
    """Attribut data-h des gabarits : dimanche d'abord, paires a plat."""
    ordre = [6, 0, 1, 2, 3, 4, 5]
    return json.dumps([[v for c in sem[i] for v in c] or None for i in ordre],
                      separators=(",", ":"))


def _table(sem, style: str, feries: bool) -> str:
    lignes = []
    for i in range(7):
        if sem[i]:
            lignes.append(f'<div><dt>{_JOURS[i].capitalize()}</dt><dd>{_creneaux(sem[i], style)}</dd></div>')
        else:
            lignes.append(f'<div class="hor--off"><dt>{_JOURS[i].capitalize()}</dt><dd>Fermé</dd></div>')
    if feries:
        lignes.append('<div class="hor--off"><dt>Jours fériés</dt><dd>Fermé</dd></div>')
    ind = "\n          "
    return ind + ind.join(lignes) + "\n        "


def _ld_horaires(sem) -> list[dict]:
    spec = []
    groupes: dict = {}
    for i in range(7):
        if sem[i]:
            groupes.setdefault(tuple(sem[i]), []).append(_JOURS_EN[i])
    for cs, jours in groupes.items():
        for a, b in cs:
            spec.append({"@type": "OpeningHoursSpecification",
                         "dayOfWeek": jours if len(jours) > 1 else jours[0],
                         "opens": f"{a // 60:02d}:{a % 60:02d}",
                         "closes": f"{b // 60:02d}:{b % 60:02d}"})
    return spec


# --------------------------------------------------------------------------
# remplissage

class GabaritInattendu(RuntimeError):
    """Un repere du gabarit de reference a disparu : on ne publie pas."""


def _un(html: str, ancien: str, neuf: str, n: int | None = 1) -> str:
    """Remplace `ancien` ; leve si le nombre d'occurrences n'est pas celui attendu."""
    trouve = html.count(ancien)
    if (n is not None and trouve != n) or trouve == 0:
        raise GabaritInattendu(f"repere {ancien[:50]!r} trouve {trouve} fois (attendu {n})")
    return html.replace(ancien, neuf)


def _re(html: str, motif: str, neuf: str, n: int = 1, flags=re.S) -> str:
    html2, k = re.subn(motif, lambda m: neuf, html, flags=flags)
    if k != n:
        raise GabaritInattendu(f"motif {motif[:50]!r} trouve {k} fois (attendu {n})")
    return html2


def _lieux(p: dict) -> dict:
    commune = (p.get("commune") or "").strip()
    cp = (p.get("code_postal") or "").strip()
    dep = (p.get("departement") or "").strip().upper()
    if not dep and cp:
        dep = cp[:3] if cp.startswith("97") else ("2A" if cp[:2] == "20" else cp[:2])
    dep = dep.zfill(2) if dep.isdigit() and len(dep) < 2 else dep
    phrase_dep = DEPARTEMENTS.get(dep, "")
    if commune:
        a_lieu, court = f"à {commune}", commune
    elif phrase_dep:
        a_lieu, court = phrase_dep, _nom_dep(phrase_dep)
    else:
        a_lieu, court = "", ""
    cp_commune = " ".join(x for x in (cp, commune) if x) or court
    return {"commune": commune, "cp": cp, "dep": dep, "a_lieu": a_lieu,
            "court": court, "cp_commune": cp_commune}


def _ld(p: dict, metier: str, slug: str, lx: dict, sem, desc: str) -> str:
    d = {"@context": "https://schema.org",
         "@type": "AutoRepair" if metier == "garage" else "HomeAndConstructionBusiness",
         "name": p["nom"], "description": desc,
         "url": f"{PAGES}/{slug}/", "telephone": "06 XX XX XX XX",
         "address": {"@type": "PostalAddress", "streetAddress": "XX rue de l'Exemple",
                     "addressCountry": "FR"}}
    if lx["cp"]:
        d["address"]["postalCode"] = lx["cp"]
    if lx["commune"]:
        d["address"]["addressLocality"] = lx["commune"]
    elif lx["court"]:
        d["address"]["addressRegion"] = lx["court"]
    if sem:
        d["openingHoursSpecification"] = _ld_horaires(sem)
    if metier == "garage":
        d["makesOffer"] = [{"@type": "Offer", "itemOffered": {"@type": "Service", "name": n}}
                           for n in ("Entretien courant", "Réparation mécanique")]
    corps = json.dumps(d, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{corps}\n</script>'


def remplir(p: dict, metier: str, slug: str) -> str:
    """Le gabarit du metier, rempli avec la fiche publique `p` (deja anonymisee)."""
    if metier not in GABARITS:
        # metiers du catalogue (metiers.py) : gabarit generique
        import gabarit_generique
        return gabarit_generique.remplir(p, metier, slug)
    html = (REPO_ROOT / "_templates" / GABARITS[metier]).read_text(encoding="utf-8")
    nom = (p.get("nom") or "").strip()
    if not nom:
        raise GabaritInattendu("fiche sans nom")
    e = _html.escape
    N = e(nom)
    lx = _lieux(p)
    a_lieu, court, cpc = e(lx["a_lieu"]), e(lx["court"]), e(lx["cp_commune"])
    sem = lire_horaires(p.get("horaires") or "")
    style = metier
    itin = (f"https://www.google.com/maps/dir/?api=1&amp;destination={quote(lx['cp_commune'])}"
            if lx["cp_commune"] else "#contact")
    mod = MODELE[metier]

    # le commentaire qui presente l'entreprise fictive n'a rien a faire en ligne
    html = re.sub(r"<!--\s*GABARIT DE REFERENCE.*?-->\n?", "", html, flags=re.S)
    html = re.sub(r'<script type="application/ld\+json">.*?</script>', "@@LD@@", html, count=1, flags=re.S)

    if metier == "garage":
        html = _garage(html, N, a_lieu, court, cpc, itin, sem, lx)
        desc = f"Garage indépendant {lx['a_lieu']} : entretien courant et réparation mécanique.".replace("  ", " ")
    else:
        html = _menuisier(html, N, a_lieu, court, cpc, itin, sem, lx)
        desc = f"Menuisier {lx['a_lieu']} : menuiserie intérieure et extérieure en bois, sur mesure.".replace("  ", " ")

    html = html.replace(mod["nom"], N)             # tout ce qui reste du nom modele
    html = html.replace("@@LD@@", _ld(p, metier, slug, lx, sem, desc.replace(" :", " :")))
    html = html.replace(f"/{_slug_modele(metier)}/", f"/{slug}/")

    traces = [t for t in mod["traces"] if t in html and t not in nom and t not in lx["cp_commune"]]
    if traces:
        raise GabaritInattendu("restes de l'entreprise modele : " + ", ".join(traces))
    return html


def _slug_modele(metier: str) -> str:
    return {"garage": "garage-patton", "menuisier": "menuiserie-vautrin"}[metier]


def _phrase(a_lieu: str, avant: str = " ") -> str:
    return (avant + a_lieu) if a_lieu else ""


def _garage(html, N, a_lieu, court, cpc, itin, sem, lx) -> str:
    al = _phrase(a_lieu)
    html = _un(html, "<title>Garage Patton — entretien et réparation mécanique à Rennes</title>",
               f"<title>{N} — entretien et réparation mécanique{al}</title>")
    html = _re(html, r'<meta name="description" content="[^"]*">',
               f'<meta name="description" content="{N}, garage indépendant{al}. '
               f'Entretien courant et réparation mécanique.'
               + (f" {_resume(sem, 'garage')['jours']}." if sem else "") + '">')
    html = _un(html, '<span class="mq__v">Rennes · indépendant</span>',
               f'<span class="mq__v">{court + " · " if court else ""}indépendant</span>')
    html = _un(html, "<b>Garage indépendant</b>, à l'est de Rennes",
               f"<b>Garage indépendant</b>{(', ' + a_lieu) if a_lieu else ''}")
    html = _un(html, "<small>George S. Patton, 35700 Rennes</small>", f"<small>{cpc}</small>")
    html = _un(html, '<b>Rennes<i> est</i></b><span>XX rue de l\'Exemple, 35700</span>',
               f"<b>{court or 'L’atelier'}</b><span>XX rue de l'Exemple{', ' + e_(lx['cp']) if lx['cp'] else ''}</span>")
    html = _un(html, "XX rue de l'Exemple<br>35700 Rennes", f"XX rue de l'Exemple<br>{cpc}")
    html = _re(html, r"<b>XX rue de l'Exemple</b>\s*35700 Rennes", f"<b>XX rue de l'Exemple</b>\n            {cpc}")
    html = _un(html, "https://www.google.com/maps/dir/?api=1&amp;destination=35700%20Rennes", itin)
    html = _un(html, "© 2026 Garage Patton — XX rue de l'Exemple, 35700 Rennes",
               f"© 2026 {N} — XX rue de l'Exemple{', ' + cpc if cpc else ''}")
    html = _un(html, "Horaires et position relevés sur OpenStreetMap, nœud 567923341",
               "Horaires relevés sur OpenStreetMap" if sem else "Informations relevées sur des sources publiques")

    if sem:
        r = _resume(sem, "garage")
        dh = _data_h(sem)
        html = _re(html, r"data-h='[^']*'", f"data-h='{dh}'", n=2)
        html = _un(html, ">Du lundi au vendredi</span></dd>", f">{r['jours']}</span></dd>")
        html = _un(html, "<dd>8h–12h · 14h–19h<small>vendredi jusqu'à 18h30</small></dd>",
                   f"<dd>{r['principal']}<small>{r['exceptions']}</small></dd>")
        fermes = [j.capitalize() if k == 0 else j for k, j in enumerate(r["fermes_liste"])]
        html = _un(html, "<dd>Samedi et dimanche<small>et les jours fériés</small></dd>",
                   f"<dd>{_liste(fermes) if fermes else 'Jours fériés'}<small>{'et les jours fériés' if fermes else ''}</small></dd>")
        html = _un(html, "<div><b>Lun–ven<i>.</i></b><span>Fermé le samedi, le dimanche et les jours fériés</span></div>",
                   f"<div><b>{r['court']}<i>.</i></b><span>{r['fermes']}</span></div>")
        html = _un(html, "<div><b>8<i>h</i>–19<i>h</i></b><span>Coupure de 12 h à 14 h. Le vendredi, jusqu'à 18 h 30</span></div>",
                   f"<div><b>{r['debut'] // 60}<i>h{(r['debut'] % 60) or ''}</i>–{r['fin'] // 60}<i>h{(r['fin'] % 60) or ''}</i></b>"
                   f"<span>{r['pause'] or 'Selon le jour, voir le détail plus bas'}{('. ' + r['exceptions'].capitalize()) if r['exceptions'] else ''}</span></div>")
        html = _re(html, r"Ouvert sans interruption sur la journée, midi excepté", f"Ouvert {r['jours'][0].lower() + r['jours'][1:]}")
        html = _un(html, ">Du lundi au vendredi, 8h–12h et 14h–19h.</p>", f">{r['jours']}, {r['principal_et']}.</p>")
        html = _re(html, r'(<dl class="hor">).*?(</dl>)', "@@TABLE@@")
        html = html.replace("@@TABLE@@", '<dl class="hor">' + _table(sem, "garage", True) + "</dl>")
        html = _re(html, r"<b>Du lundi au vendredi</b>\s*8h–12h et 14h–19h, le vendredi jusqu'à 18h30",
                   f"<b>{r['jours']}</b>\n            {r['principal_et']}{(', ' + r['exceptions']) if r['exceptions'] else ''}")
    else:
        html = _re(html, r"""<span class="etat" id="etat"\s*data-h='[^']*'>Du lundi au vendredi</span>""",
                   '<span class="etat" id="etat">Sur appel</span>')
        html = _un(html, "<dd>8h–12h · 14h–19h<small>vendredi jusqu'à 18h30</small></dd>",
                   "<dd>Horaires non publiés<small>un appel avant de passer</small></dd>")
        html = _re(html, r"<div><dt>Fermeture</dt><dd>Samedi et dimanche<small>et les jours fériés</small></dd></div>\s*", "")
        html = _un(html, "<div><b>Lun–ven<i>.</i></b><span>Fermé le samedi, le dimanche et les jours fériés</span></div>",
                   "<div><b>Sur appel<i>.</i></b><span>Horaires non publiés : appelez avant de passer</span></div>")
        html = _un(html, "<div><b>8<i>h</i>–19<i>h</i></b><span>Coupure de 12 h à 14 h. Le vendredi, jusqu'à 18 h 30</span></div>",
                   "<div><b>1<i> numéro</i></b><span>Il sonne directement à l'atelier</span></div>")
        html = _un(html, "Ouvert sans interruption sur la journée, midi excepté", "Un appel suffit pour prendre rendez-vous")
        html = _re(html, r"""<p class="etat" id="etat2"\s*data-h='[^']*'>Du lundi au vendredi, 8h–12h et 14h–19h\.</p>\s*<dl class="hor">.*?</dl>""",
                   '<p>Les horaires de l\'atelier ne sont pas publiés. Un appel avant de passer '
                   'évite de trouver porte close.</p>')
        html = _re(html, r"<b>Du lundi au vendredi</b>\s*8h–12h et 14h–19h, le vendredi jusqu'à 18h30",
                   "<b>Horaires sur appel</b>\n            un coup de fil avant de passer")
        html = _un(html, "L'état affiché se calcule à l'heure où vous lisez cette\n        page, pour éviter le déplacement pour rien.",
                   "Un appel avant de venir évite le déplacement pour rien.")
    return html


def e_(s: str) -> str:
    return _html.escape(s or "")


def _menuisier(html, N, a_lieu, court, cpc, itin, sem, lx) -> str:
    al = _phrase(a_lieu)
    html = _un(html, "<title>Menuiserie Vautrin — menuisier à Nancy</title>",
               f"<title>{N} — menuisier{al}</title>")
    html = _re(html, r'<meta name="description" content="[^"]*">',
               f'<meta name="description" content="{N}, menuisier{al} : menuiserie intérieure '
               f'et extérieure en bois, sur mesure.">')
    html = _un(html, 'aria-label="Menuiserie Vautrin, accueil"', f'aria-label="{N}, accueil"')
    html = _un(html, '<span class="mq__v">Menuisier à Nancy</span>',
               f'<span class="mq__v">Menuisier{al}</span>')
    html = _un(html, "<span>menuiserie sur mesure à Nancy</span>", f"<span>menuiserie sur mesure{al}</span>")
    html = _re(html, r"<p class=\"ouv__t\">Menuiserie Vautrin, XX rue de l'Exemple à Nancy\.",
               f"<p class=\"ouv__t\">{N}{(', ' + a_lieu) if a_lieu else ''}.")
    html = _un(html, "<div><b>Nancy</b><span>XX rue de l'Exemple, 54000</span></div>",
               f"<div><b>{court or 'L’atelier'}</b><span>XX rue de l'Exemple{', ' + e_(lx['cp']) if lx['cp'] else ''}</span></div>")
    html = _un(html, "XX rue de l'Exemple<br>54000 Nancy", f"XX rue de l'Exemple<br>{cpc}")
    html = _un(html, "<span><b>XX rue de l'Exemple</b>54000 Nancy</span>", f"<span><b>XX rue de l'Exemple</b>{cpc}</span>")
    html = _un(html, "https://www.google.com/maps/dir/?api=1&amp;destination=54000%20Nancy", itin)
    html = _un(html, "© 2026 Menuiserie Vautrin, XX rue de l'Exemple, 54000 Nancy",
               f"© 2026 {N}, XX rue de l'Exemple{', ' + cpc if cpc else ''}")
    html = _un(html, "Horaires et position relevés sur OpenStreetMap",
               "Horaires relevés sur OpenStreetMap" if sem else "Informations relevées sur des sources publiques")

    if sem:
        r = _resume(sem, "menuisier")
        dh = _data_h(sem)
        html = _re(html, r"data-h='[^']*'", f"data-h='{dh}'", n=2)
        html = _un(html, ">du lundi au vendredi</span></p>", f">{r['jours'][0].lower() + r['jours'][1:]}</span></p>")
        html = _un(html, "<div><b>Lundi au vendredi</b><span>Fermé le samedi, le dimanche et les jours fériés</span></div>",
                   f"<div><b>{r['jours'].replace('Du ', '').replace(' au ', ' au ').capitalize()}</b><span>{r['fermes']}</span></div>")
        html = _un(html, "<div><b>8 h – 18 h</b><span>Coupure de 12 h à 13 h 30. Le vendredi, jusqu'à 17 h</span></div>",
                   f"<div><b>{_hm(r['debut'], 'menuisier')} – {_hm(r['fin'], 'menuisier')}</b>"
                   f"<span>{r['pause'] or 'Selon le jour, voir le détail plus bas'}{('. ' + r['exceptions'].capitalize()) if r['exceptions'] else ''}</span></div>")
        html = _un(html, ">Du lundi au vendredi, 8 h – 12 h et 13 h 30 – 18 h.</p>",
                   f">{r['jours']}, {r['principal_et']}.</p>")
        html = _re(html, r'(<dl class="hor">).*?(</dl>)', "@@TABLE@@")
        html = html.replace("@@TABLE@@", '<dl class="hor">' + _table(sem, "menuisier", False) + "</dl>")
        html = _un(html, "<span><b>Du lundi au vendredi</b>8 h – 12 h et 13 h 30 – 18 h, le vendredi jusqu'à 17 h</span>",
                   f"<span><b>{r['jours']}</b>{r['principal_et']}{(', ' + r['exceptions']) if r['exceptions'] else ''}</span>")
    else:
        html = _re(html, r"""<span class="etat" id="etat"\s*data-h='[^']*'>du lundi au vendredi</span>""",
                   '<span class="etat" id="etat">sur rendez-vous</span>')
        html = _un(html, "<div><b>Lundi au vendredi</b><span>Fermé le samedi, le dimanche et les jours fériés</span></div>",
                   "<div><b>Sur rendez-vous</b><span>Horaires non publiés : un appel avant de passer</span></div>")
        html = _un(html, "<div><b>8 h – 18 h</b><span>Coupure de 12 h à 13 h 30. Le vendredi, jusqu'à 17 h</span></div>",
                   "<div><b>Un seul numéro</b><span>Il sonne directement à l'atelier</span></div>")
        html = _re(html, r"""<p class="etat" id="etat2"\s*data-h='[^']*'>Du lundi au vendredi, 8 h – 12 h et 13 h 30 – 18 h\.</p>\s*<dl class="hor">.*?</dl>""",
                   "<p>Les horaires de l'atelier ne sont pas publiés : un menuisier est souvent "
                   "sur un chantier. Un appel avant de passer évite de trouver porte close.</p>")
        html = _un(html, "<span><b>Du lundi au vendredi</b>8 h – 12 h et 13 h 30 – 18 h, le vendredi jusqu'à 17 h</span>",
                   "<span><b>Sur rendez-vous</b>un appel avant de passer</span>")
        html = _un(html, "L'état affiché se calcule à l'heure où vous lisez la page.",
                   "Un appel avant de venir évite le déplacement pour rien.")
    return html
