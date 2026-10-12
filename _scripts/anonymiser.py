#!/usr/bin/env python3
"""Retire d'une maquette publiee les coordonnees reelles du prospect.

La regle, depuis le 8 octobre : la base garde tout ce qu'il faut pour
contacter la personne, la page publique n'en garde rien de joignable. Le
nom, la commune et le metier restent — c'est ce qui donne sa force a la
demonstration — mais le telephone, le courriel, l'adresse precise, le SIREN
et les coordonnees GPS sont remplaces par des valeurs fictives.

Le numero de remplacement est tire des plages que l'ARCEP reserve a la
fiction (01 99 00, 02 61 91, 03 53 01, 04 65 71, 05 36 49 pour les fixes,
06 39 98 pour les mobiles). Il garde l'indicatif regional du vrai numero,
pour qu'un atelier du Doubs affiche toujours un 03. Ces numeros ne sont
attribues a personne : les afficher ne derange aucun abonne.

Deux fonctions, et l'ordre compte :

    html, faits = appliquer(html, prospect)   # remplace
    restes = verifier(html, prospect)         # controle qu'il ne reste rien

`verifier` est le garde-fou : il relit la page finie et renvoie la liste de
ce qu'il trouve encore. Un appelant qui obtient une liste non vide ne doit
pas publier.

Usage en ligne de commande, pour reprendre les maquettes deja en ligne :

    python3 _scripts/anonymiser.py --apercu            # ce qui serait change
    python3 _scripts/anonymiser.py --appliquer         # tout le depot
    python3 _scripts/anonymiser.py --appliquer <slug>  # une seule maquette

Depuis le 12 octobre, plus aucun numero n'est affiche : tout telephone
d'une page publiee devient le masque « 06 XX XX XX XX » (MASQUE_TEL), et
les liens tel:/sms: pointent vers #contact. Un masque ne peut appartenir a
personne, contrairement a un numero tire d'une plage de fiction.

Depuis le 11 octobre, `neutraliser` complete `appliquer` : il remplace aussi
les numeros et courriels que le modele invente (ou qu'un gabarit laisse en
exemple), qui ne sont pas ceux du prospect mais peuvent etre ceux de
quelqu'un. Les pipelines l'appellent en toute derniere passe.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Plages de fiction de l'ARCEP, par indicatif. Jamais attribuees.
PLAGES = {
    "01": "01 99 00", "02": "02 61 91", "03": "03 53 01",
    "04": "04 65 71", "05": "05 36 49", "09": "09 75 18",
    "06": "06 39 98", "07": "06 39 98",
}
PLAGE_DEFAUT = "01 99 00"
DOMAINE_FICTIF = "exemple-atelier.fr"
MASQUE_TEL = "06 XX XX XX XX"
MASQUE_SIREN = "XXX XXX XXX"
MASQUE_RUE = "XX rue de l'Exemple"
MASQUE_SIRET = "XXX XXX XXX XXXXX"
MASQUE_TVA = "FR XX XXX XXX XXX"
# Un SIREN/SIRET n'est reconnu qu'a cote de son libelle (SIREN, SIRET, RCS,
# taxID…) : un nombre de neuf chiffres seul peut etre n'importe quoi.
_LIBELLE_ENTREPRISE = re.compile(
    r'((?:siren|siret|r\.?\s?c\.?\s?s\.?|taxid|vatid|n°\s*d.immatriculation)'
    r'(?:[\s:°#.,"\'=()\-\u2013\u2014/\u00a0]|value|n°|<[^>]*>){0,40}?)'
    r'(\d(?:[\s.\u00a0]?\d){8,13})(?!\d)', re.IGNORECASE)
_TVA = re.compile(r'\bFR\s?\d{2}(?:[\s.]?\d{3}){3}\b')


def _masque_entreprise(chiffres: str) -> str:
    n = len(re.sub(r"\D", "", chiffres))
    return MASQUE_SIRET if n >= 14 else MASQUE_SIREN if n == 9 else "X" * n


# --- adresses postales ---------------------------------------------------
# La commune et le code postal restent (ancrage local du pitch) ; le numero
# et la rue deviennent « XX rue de l'Exemple », les coordonnees GPS sont
# arrondies a deux decimales (la commune, pas la porte).
_VOIE = (r"(?:rue|avenue|av\.|boulevard|bd|chemin|route|rte|impasse|all[ée]e|place"
         r"|quai|cours|square|passage|sentier|lotissement|lieu[- ]dit|hameau"
         r"|r[ée]sidence|faubourg|promenade|esplanade|voie|mont[ée]e|chauss[ée]e"
         r"|rond[- ]point|zone artisanale|zone industrielle|za|zi|zac)")
_MOT_RUE = (r"(?:[A-Z]\.(?=\s)|[A-ZÀ-Ý][\wÀ-ÿ'’\-]*|d[eu]s?|de\s+la|de\s+l['’]|la|le|les"
            r"|l['’]\w*|d['’]\w*|aux?|et|sur|sous|en|saint|st|\d{1,4})")
_RUE = re.compile(r"(?<![\w©/=%#.-])(?!(?:19|20)\d\d\b)\d{1,4}\s?(?:bis|ter|b|t)?\s*,?\s+(?i:" + _VOIE
                  + r")(?:\s+" + _MOT_RUE + r"){1,8}")
_LD_RUE = re.compile(r'("streetAddress"\s*:\s*")([^"]*)(")')
_LIEN_CARTE = re.compile(r'((?:destination|daddr|query|q)=)([^"&\'<>\s]+)')
_GPS_PAIRE = re.compile(r"(-?\d{1,3}\.\d{3,})((?:%2C|,)\s?)(-?\d{1,3}\.\d{3,})", re.IGNORECASE)
_URL_CARTE = re.compile(r"""https?://[^"'\s<>]*(?:map|osm)[^"'\s<>]*""", re.IGNORECASE)
_GPS_CLE = re.compile(r'("?(?:latitude|longitude|lat|lng|lon)"?\s*[:=]\s*"?)(-?\d{1,3}\.\d{3,})',
                      re.IGNORECASE)


def _a_une_rue(texte: str) -> bool:
    t = texte.replace("+", " ")
    return bool(re.search(r"\b" + _VOIE + r"\b", t, re.IGNORECASE)
                or re.search(r"(?<!\d)\d{1,4}\s?(?:bis|ter)?\s", re.sub(r"\b\d{5}\b", "", t)))


def _carte_commune(valeur: str) -> str:
    """Parametre d'itineraire : on ne garde que « code postal + commune »."""
    from urllib.parse import unquote, quote
    brut = unquote(valeur.replace("+", " "))
    if not _a_une_rue(brut):
        return valeur
    m = re.search(r"\b(\d{5})\s*,?\s*([^,]+)", brut)
    if m:
        garde = f"{m.group(1)} {m.group(2).strip()}"
    else:                      # pas de code postal : dernier segment = commune
        garde = brut.split(",")[-1].strip()
        if _a_une_rue(garde):
            garde = ""
    return quote(garde)


def masquer_adresses(html: str) -> tuple[str, int]:
    """Rues -> « XX rue de l'Exemple », itineraires -> commune, GPS -> 2 decimales."""
    n = 0
    def _rue(m):
        nonlocal n
        if "Exemple" in m.group(0):
            return MASQUE_RUE if m.group(0).strip() != MASQUE_RUE else m.group(0)
        n += 1
        return MASQUE_RUE
    html = _RUE.sub(_rue, html)
    def _ld(m):
        nonlocal n
        v = m.group(2)
        if not v.strip() or v == MASQUE_RUE or not _a_une_rue(v + " "):
            return m.group(0)
        n += 1
        return m.group(1) + MASQUE_RUE + m.group(3)
    html = _LD_RUE.sub(_ld, html)
    def _carte(m):
        nonlocal n
        v = _carte_commune(m.group(2))
        if v != m.group(2):
            n += 1
        return m.group(1) + v
    html = _LIEN_CARTE.sub(_carte, html)
    def _arr(x):
        return f"{float(x):.2f}"
    def _paire(m):
        nonlocal n
        if len(m.group(1).split(".")[1]) <= 2 and len(m.group(3).split(".")[1]) <= 2:
            return m.group(0)
        n += 1
        return _arr(m.group(1)) + m.group(2) + _arr(m.group(3))
    # paires lat,lon : seulement dans les liens et cartes (une courbe CSS
    # « cubic-bezier(0.175, 0.885…) » a la meme forme)
    html = _URL_CARTE.sub(lambda u: _GPS_PAIRE.sub(_paire, u.group(0)), html)
    def _cle(m):
        nonlocal n
        n += 1
        return m.group(1) + _arr(m.group(2))
    html = _GPS_CLE.sub(_cle, html)
    return html, n


def adresses_restantes(html: str) -> list[str]:
    restes = [m.group(0) for m in _RUE.finditer(html) if "Exemple" not in m.group(0)]
    restes += [m.group(2) for m in _LD_RUE.finditer(html)
               if m.group(2).strip() and m.group(2) != MASQUE_RUE and _a_une_rue(m.group(2) + " ")]
    restes += [m.group(2) for m in _LIEN_CARTE.finditer(html) if _carte_commune(m.group(2)) != m.group(2)]
    for u in _URL_CARTE.finditer(html):
        restes += [m.group(0) for m in _GPS_PAIRE.finditer(u.group(0))
                   if len(m.group(1).split(".")[1]) > 2 or len(m.group(3).split(".")[1]) > 2]
    restes += [m.group(2) for m in _GPS_CLE.finditer(html)]
    return restes


def masquer_entreprise(html: str) -> tuple[str, int]:
    """SIREN, SIRET et TVA intracommunautaire -> masques XXX. Renvoie (page, nombre)."""
    n = 0
    def _sub(m):
        nonlocal n
        n += 1
        return m.group(1) + _masque_entreprise(m.group(2))
    html = _LIBELLE_ENTREPRISE.sub(_sub, html)
    html, k = _TVA.subn(MASQUE_TVA, html)
    return html, n + k
LIEN_TEL = "#contact"          # cible des anciens liens tel: / sms:
_HREF_TEL = re.compile(r'(href=["\'])(?:tel|sms):[^"\']*(["\'])', re.IGNORECASE)


def masquer_liens(html: str) -> str:
    """Les liens d'appel et de SMS ne menent plus a aucun numero."""
    return _HREF_TEL.sub(lambda m: m.group(1) + LIEN_TEL + m.group(2), html)


def _chiffres(s: str) -> str:
    d = re.sub(r"\D", "", s or "")
    if d.startswith("33") and len(d) == 11:
        d = "0" + d[2:]
    return d


def tel_fictif(tel_reel: str, graine: str) -> str:
    """Le numero affiche sur une maquette : toujours le masque.

    (Avant le 12 octobre : un numero stable tire des plages de fiction.)"""
    return MASQUE_TEL


def _ancien_tel_fictif(tel_reel: str, graine: str) -> str:
    d = _chiffres(tel_reel)
    prefixe = PLAGES.get(d[:2], PLAGE_DEFAUT) if len(d) >= 2 else PLAGE_DEFAUT
    n = int(hashlib.sha256(graine.encode()).hexdigest()[:8], 16) % 10000
    return f"{prefixe} {n // 100:02d} {n % 100:02d}"


def _motif_tel(tel: str) -> re.Pattern | None:
    """Reconnait le numero quelle que soit sa mise en forme.

    Un meme numero s'ecrit « 03.81.44.12.00 », « 03 81 44 12 00 »,
    « 0381441200 », « +33 3 81 44 12 00 » ou « tel:+33381441200 » dans une
    seule et meme page. On construit donc le motif chiffre par chiffre.
    """
    d = _chiffres(tel)
    if len(d) != 10:
        return None
    sep = r"[\s.\-/ ‑–]*"
    corps = sep.join(d[1:])              # sans le 0 initial
    return re.compile(rf"(?:\+\s?33{sep}|00{sep}33{sep}|0)" + corps)


def appliquer(html: str, p: dict) -> tuple[str, list[str]]:
    """Remplace les coordonnees reelles. Renvoie la page et ce qui a change."""
    faits: list[str] = []
    graine = (p.get("cle") or p.get("source_url") or p.get("nom") or "x")

    # --- telephone -------------------------------------------------------
    reel = (p.get("telephone") or p.get("phone") or "").strip()
    faux = tel_fictif(reel, graine)
    motif = _motif_tel(reel)
    if motif:
        n = len(motif.findall(html))
        if n:
            html = motif.sub(lambda m: faux, html)
            faits.append(f"telephone remplace ({n} occurrence(s)) -> {faux}")
    # les liens tel:/sms: ne menent plus a aucun numero
    html = masquer_liens(html)

    # --- courriel --------------------------------------------------------
    mail = (p.get("email") or "").strip()
    if mail:
        n = html.lower().count(mail.lower())
        if n:
            html = re.sub(re.escape(mail), f"contact@{DOMAINE_FICTIF}", html,
                          flags=re.IGNORECASE)
            faits.append(f"courriel remplace ({n} occurrence(s))")

    # --- adresse postale precise ----------------------------------------
    # La commune reste (c'est l'ancrage local du pitch), le numero et la rue
    # partent : c'est ce qui mene au domicile quand l'atelier est chez lui.
    adresse = (p.get("adresse") or "").strip()
    if adresse:
        rue = re.sub(r"\s*\d{5}.*$", "", adresse).strip(" ,")
        if len(rue) > 6 and rue.lower() in html.lower():
            html = re.sub(re.escape(rue), MASQUE_RUE, html,
                          flags=re.IGNORECASE)
            faits.append("adresse precise remplacee")

    # --- SIREN / SIRET ---------------------------------------------------
    for champ in ("siren", "siret"):
        v = (p.get(champ) or "").strip()
        if v and v in html:
            html = html.replace(v, MASQUE_SIRET if len(re.sub(r"\D", "", v)) >= 14 else MASQUE_SIREN)
            faits.append(f"{champ} masque")

    # --- coordonnees GPS -------------------------------------------------
    # Un couple lat/lon au dix-millieme designe le batiment. On tronque a
    # deux decimales : la carte reste sur la bonne commune, pas sur la porte.
    for champ in ("latitude", "longitude"):
        v = p.get(champ)
        if v in (None, ""):
            continue
        exact = f"{float(v)}"
        arrondi = f"{float(v):.2f}"
        if exact in html:
            html = html.replace(exact, arrondi)
            faits.append(f"{champ} arrondie")
        else:
            prefixe = f"{float(v):.4f}"[:7]
            motif_gps = re.compile(re.escape(prefixe) + r"\d*")
            if motif_gps.search(html):
                html = motif_gps.sub(arrondi, html)
                faits.append(f"{champ} arrondie")
    return html, faits


# Un texte de presentation repris d'un annuaire contient souvent le numero
# ou le courriel en clair, au milieu d'une phrase. Il part aussi.
_TEL_LIBRE = re.compile(
    r"(?:\+\s?33|0)\s?[1-9](?:[\s.\-/\u00a0]?\d{2}){4}")
_MAIL_LIBRE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", re.IGNORECASE)
_SIREN_LIBRE = re.compile(r"\b\d{3}[\s.]?\d{3}[\s.]?\d{3}(?:[\s.]?\d{5})?\b")


def _porte_coordonnee(phrase: str) -> bool:
    return bool(_MAIL_LIBRE.search(phrase) or _TEL_LIBRE.search(phrase)
                or _SIREN_LIBRE.search(phrase))


def nettoyer_texte(texte: str) -> str:
    """Retire d'un texte libre les coordonnees qui s'y seraient glissees.

    On enleve la PHRASE entiere, pas seulement le numero : effacer les
    chiffres au milieu d'une phrase laisse « Contactez-nous au ou par mail
    a ! », qui se remarque bien plus qu'une phrase en moins. Et une phrase
    dont l'objet est de donner un numero ne porte rien d'autre.

    S'il ne reste rien, on rend une chaine vide : le prompt sait se passer
    d'une presentation, il ne sait pas rattraper une phrase estropiee.
    """
    if not texte:
        return texte
    phrases = re.split(r"(?<=[.!?])\s+", texte)
    gardees = [ph for ph in phrases if not _porte_coordonnee(ph)]
    return " ".join(gardees).strip()


def fiche_publique(p: dict) -> dict:
    """La fiche telle qu'elle peut servir a fabriquer une page publique.

    C'est la version a donner au modele : il ne doit jamais voir les vraies
    coordonnees, sinon il les recopie quelque part ou le remplacement
    posterieur ne les rattrape pas (un attribut data-, un commentaire, un
    JSON-LD reformate). Le nom, la commune et le code postal restent : ce
    sont eux qui donnent son interet a la demonstration.

    Ce qui disparait : telephone reel, courriel, rue, SIREN, GPS precis.
    """
    graine = (p.get("cle") or p.get("source_url") or p.get("nom") or "x")
    public = dict(p)
    public["telephone"] = tel_fictif(p.get("telephone") or p.get("phone") or "", graine)
    public["phone"] = public["telephone"]
    public["email"] = ""
    public["adresse"] = ""
    public["siren"] = ""
    public["siret"] = ""
    for champ in ("latitude", "longitude"):
        v = p.get(champ)
        public[champ] = round(float(v), 2) if v not in (None, "") else v
    return public


def verifier(html: str, p: dict) -> list[str]:
    """Ce qui subsiste de reel dans la page. Vide = publiable."""
    restes: list[str] = []
    reel = (p.get("telephone") or p.get("phone") or "").strip()
    motif = _motif_tel(reel)
    if motif and motif.search(html):
        restes.append(f"telephone reel ({reel})")
    mail = (p.get("email") or "").strip()
    if mail and mail.lower() in html.lower():
        restes.append(f"courriel reel ({mail})")
    for champ in ("siren", "siret"):
        v = (p.get(champ) or "").strip()
        if v and len(v) >= 9 and v in html:
            restes.append(f"{champ} reel")
    adresse = (p.get("adresse") or "").strip()
    rue = re.sub(r"\s*\d{5}.*$", "", adresse).strip(" ,")
    if len(rue) > 6 and rue.lower() in html.lower():
        restes.append(f"adresse precise ({rue})")
    for champ in ("latitude", "longitude"):
        v = p.get(champ)
        if v in (None, ""):
            continue
        if f"{float(v):.4f}"[:7] in html:
            restes.append(f"{champ} au dix-millieme")
    return restes


# --------------------------------------------------------------------------
# coordonnees inventees par le modele

# Ce que `appliquer` ne peut pas voir : le modele invente volontiers un
# « 06 12 34 56 78 » ou un « contact@garage-dupont.fr ». Ce ne sont pas les
# vraies coordonnees du prospect, mais ce sont peut-etre celles de quelqu'un
# d'autre. Regle : sur une page publiee, tout numero hors des plages de
# fiction et tout courriel hors du domaine fictif est remplace.

_FICTIFS = tuple(sorted({v.replace(" ", "") for v in PLAGES.values()} | {"0199"}))
# Ni precede ni suivi d'un caractere de mot, d'un chiffre ou d'un separateur
# d'URL : une version Cloudinary « v1712345678 » ou un identifiant ne sont
# pas des numeros.
_TEL_INVENTE = re.compile(
    r"(?<![\w/=.#-])(?:\+\s?33\s?(?:\(0\))?\s?|0)[1-9](?:[\s.\-\u00a0]?\d{2}){4}(?![\w-])")
_MAIL_INVENTE = re.compile(r"(?<![\w.+-])[\w.+-]+@([\w-]+(?:\.[\w-]+)*\.[a-z]{2,})(?![\w.-])",
                           re.IGNORECASE)
_EXTENSIONS_FICHIER = {"png", "jpg", "jpeg", "webp", "svg", "gif", "avif", "css", "js"}
_PLACEHOLDER = re.compile(r'placeholder\s*=\s*("[^"]*"|\'[^\']*\')', re.IGNORECASE)


def _est_fictif(tel: str) -> bool:
    # Depuis le 12 octobre, aucun numero chiffre n'est tolere : seul le
    # masque (qui ne contient pas de chiffres apres l'indicatif) passe.
    return False


def neutraliser(html: str, graine: str) -> tuple[str, list[str]]:
    """Remplace les numeros et courriels inventes. Renvoie la page et le bilan."""
    faits: list[str] = []
    remplaces: dict[str, str] = {}
    def _tel(m):
        remplaces[_chiffres(m.group(0))] = MASQUE_TEL
        return MASQUE_TEL
    # d'abord les liens tel:/sms:, qui ne menent plus a aucun numero
    avant = html
    html = masquer_liens(html)
    html = _TEL_INVENTE.sub(_tel, html)
    if remplaces:
        faits.append(f"{len(remplaces)} numero(s) masque(s) en {MASQUE_TEL}")
    elif html != avant:
        faits.append("liens d'appel neutralises")

    # Les courriels d'exemple des formulaires (placeholder="votre@email.fr")
    # restent : ils ne menent a personne. Les numeros d'exemple, eux, sont
    # deja passes en fictif ci-dessus.
    gardes: list[str] = []
    def _garder(m):
        gardes.append(m.group(0))
        return f"\x00{len(gardes) - 1}\x00"
    html = _PLACEHOLDER.sub(_garder, html)

    n_mail = 0
    def _mail(m):
        nonlocal n_mail
        domaine = m.group(1).lower()
        if domaine.rsplit(".", 1)[-1] in _EXTENSIONS_FICHIER:
            return m.group(0)        # logo@2x.png n'est pas un courriel
        if domaine == DOMAINE_FICTIF or domaine.endswith((".example", ".invalid")):
            return m.group(0)
        n_mail += 1
        return f"contact@{DOMAINE_FICTIF}"
    html = _MAIL_INVENTE.sub(_mail, html)
    if n_mail:
        faits.append(f"{n_mail} courriel(s) invente(s) remplace(s)")

    html = re.sub(r"\x00(\d+)\x00", lambda m: gardes[int(m.group(1))], html)

    # SIREN / SIRET / TVA, reels ou inventes : jamais un numero, toujours XXX
    html = html.replace("000 000 000", MASQUE_SIREN)
    html, n_ent = masquer_entreprise(html)
    if n_ent:
        faits.append(f"{n_ent} SIREN/SIRET/TVA masque(s)")
    html, n_adr = masquer_adresses(html)
    if n_adr:
        faits.append(f"{n_adr} adresse(s)/GPS masque(s)")
    return html, faits


def coordonnees_non_fictives(html: str) -> list[str]:
    """Ce qui reste de joignable apres `neutraliser`. Vide = publiable."""
    sans_exemples = _PLACEHOLDER.sub("", html)
    restes = [m.group(0) for m in _TEL_INVENTE.finditer(html)
              if not _est_fictif(m.group(0))]
    for m in _MAIL_INVENTE.finditer(sans_exemples):
        d = m.group(1).lower()
        if d.rsplit(".", 1)[-1] in _EXTENSIONS_FICHIER or d == DOMAINE_FICTIF:
            continue
        restes.append(m.group(0))
    restes += [m.group(2) for m in _LIBELLE_ENTREPRISE.finditer(html)]
    restes += [m.group(0) for m in _TVA.finditer(html)]
    restes += adresses_restantes(html)
    return restes


# --------------------------------------------------------------------------
# reprise des maquettes deja publiees

def _prospects(db: Path) -> dict[str, dict]:
    """Les fiches des deux bases, indexees par slug de dossier."""
    par_slug: dict[str, dict] = {}
    for base, table, champs, slug_col in (
        ("prospection.db", "prospects",
         "nom, telephone, email, adresse, latitude, longitude, cle", "site_genere"),
        ("annonces.db", "annonces",
         "name, phone, email, '' , '' , '' , source_url", "site_slug"),
    ):
        chemin = db.parent / base
        if not chemin.exists():
            continue
        c = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        try:
            lignes = c.execute(
                f"SELECT {champs}, {slug_col} AS reperage FROM {table} "
                f"WHERE COALESCE({slug_col},'') <> ''").fetchall()
        except sqlite3.OperationalError:
            c.close()
            continue
        for r in lignes:
            cles = list(r.keys())
            slug = (r["reperage"] or "").rstrip("/").rsplit("/", 1)[-1]
            if not slug:
                continue
            par_slug[slug] = {
                "nom": r[cles[0]], "telephone": r[cles[1]], "email": r[cles[2]],
                "adresse": r[cles[3]], "latitude": r[cles[4]],
                "longitude": r[cles[5]], "cle": r[cles[6]],
                "siren": "",
            }
        c.close()
    return par_slug


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?", help="une seule maquette")
    ap.add_argument("--appliquer", action="store_true")
    ap.add_argument("--apercu", action="store_true")
    args = ap.parse_args()
    if not (args.appliquer or args.apercu):
        ap.error("choisis --apercu ou --appliquer")

    fiches = _prospects(REPO_ROOT / "_data" / "x")
    print(f"{len(fiches)} fiche(s) rattachees a une maquette\n")
    touches = intacts = sans_fiche = 0
    for dossier in sorted(REPO_ROOT.glob("*/index.html")):
        slug = dossier.parent.name
        if args.slug and slug != args.slug:
            continue
        if slug.startswith(("_", ".")):
            continue
        p = fiches.get(slug)
        if not p:
            sans_fiche += 1
            p = {"cle": slug}      # pas de fiche : seules les inventions partent
        html = dossier.read_text(encoding="utf-8", errors="replace")
        neuf, faits = appliquer(html, p)
        neuf, inventes = neutraliser(neuf, p.get("cle") or slug)
        faits += inventes
        if not faits:
            intacts += 1
            continue
        touches += 1
        print(f"  {slug}")
        for f in faits:
            print(f"      {f}")
        restes = verifier(neuf, p)
        if restes:
            print(f"      /!\\ il reste : {', '.join(restes)}")
        if args.appliquer:
            dossier.write_text(neuf, encoding="utf-8")

    print(f"\n{touches} maquette(s) a corriger, {intacts} deja propres, "
          f"{sans_fiche} sans fiche en base.")
    if args.apercu:
        print("Apercu : aucun fichier n'a ete modifie.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
