#!/usr/bin/env python3
"""Verifie l'extraction sur des pages fabriquees d'apres les pieges reels."""
import importlib.util
import pathlib
import sys

_ici = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ms", _ici / "mails_sites.py")
ms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ms)

def meilleur(page, hote):
    c = ms.moissonner(page)
    if not c:
        return None
    m = max(c, key=lambda a: (ms.noter(a, c[a], hote), -len(a)))
    return m if ms.noter(m, c[m], hote) >= 1 else None

CAS = [
    # (libelle, html, hote du site, attendu)
    ("mailto simple",
     '<a href="mailto:contact@garage-picard.fr">Nous écrire</a>',
     "garage-picard.fr", "contact@garage-picard.fr"),

    ("mailto encodé + sujet",
     '<a href="mailto:contact%40garage-picard.fr?subject=Devis">mail</a>',
     "garage-picard.fr", "contact@garage-picard.fr"),

    ("entité HTML",
     '<p>Écrivez à contact&#64;garage-picard.fr</p>',
     "garage-picard.fr", "contact@garage-picard.fr"),

    ("Cloudflare data-cfemail",
     '<a href="/cdn-cgi/l/email-protection" class="__cf_email__" '
     'data-cfemail="4b25242e2e0b3a2f38242e3d652825">[email&#160;protected]</a>',
     "x.fr", None),  # rempli plus bas par un vrai chiffrage

    ("piège : logo@2x.png",
     '<img src="/img/logo@2x.png"><img srcset="sprite@3x.webp 3x">',
     "garage-x.fr", None),

    ("piège : Wix + Sentry seuls",
     '<script>Sentry.init({dsn:"https://a1b@o12.ingest.sentry.io/4"})</script>'
     '<a href="mailto:support@wix.com">aide</a>',
     "garagemartin.wixsite.com", None),

    ("piège : exemple de formulaire",
     '<input placeholder="votre-email@exemple.fr"><span>nom@domaine.fr</span>',
     "garage-y.fr", None),

    ("Gmail seule, acceptée",
     '<footer>Garage Sallaberry — garagesallaberry64@gmail.com — 05 59 ..</footer>',
     "garage-sallaberry.fr", "garagesallaberry64@gmail.com"),

    ("domaine propre battu contre gmail",
     '<a href="mailto:garage.dupont31@gmail.com">g</a>'
     '<a href="mailto:contact@garage-dupont.fr">c</a>',
     "garage-dupont.fr", "contact@garage-dupont.fr"),

    ("compta écartée au profit de contact",
     '<p>compta@carrosserie-z.fr</p><p>contact@carrosserie-z.fr</p>',
     "carrosserie-z.fr", "contact@carrosserie-z.fr"),

    ("recrutement seul : pris quand même (domaine propre)",
     '<p>recrutement@carrosserie-z.fr</p>',
     "carrosserie-z.fr", "recrutement@carrosserie-z.fr"),

    ("maquillé (at)/(dot)",
     '<p>Nous joindre : contact (at) garage-maquille (dot) fr</p>',
     "garage-maquille.fr", "contact@garage-maquille.fr"),

    ("maquillé [arobase] . fr",
     '<p>accueil [arobase] autoservice . fr</p>',
     "autoservice.fr", "accueil@autoservice.fr"),

    ("sous-domaine www compté comme le domaine",
     '<a href="mailto:contact@garage-w.fr">c</a>',
     "www.garage-w.fr", "contact@garage-w.fr"),

    ("JSON échappé \\u003e",
     '<script>{"a":"\\u003e"}</script><p>contact@garage-json.fr</p>',
     "garage-json.fr", "contact@garage-json.fr"),

    ("noreply écarté, contact gardé",
     '<p>noreply@garage-n.fr</p><p>contact@garage-n.fr</p>',
     "garage-n.fr", "contact@garage-n.fr"),

    ("noreply seul : rien",
     '<p>no-reply@garage-n.fr</p>',
     "garage-n.fr", None),

    ("fournisseur tiers écarté face au domaine propre",
     '<p>commande@fournisseur-pieces-pro.com</p><p>garage@garage-p.fr</p>',
     "garage-p.fr", "garage@garage-p.fr"),

    ("page vide",
     '<html><body><h1>Garage</h1></body></html>', "garage-v.fr", None),
]

# vrai chiffrage Cloudflare de contact@garage-picard.fr
def chiffre(adresse, cle=0x4b):
    return f"{cle:02x}" + "".join(f"{ord(c) ^ cle:02x}" for c in adresse)

CAS[3] = ("Cloudflare data-cfemail",
          f'<a class="__cf_email__" data-cfemail="{chiffre("contact@garage-picard.fr")}">'
          '[email&#160;protected]</a>',
          "garage-picard.fr", "contact@garage-picard.fr")

ok = ko = 0
for libelle, page, hote, attendu in CAS:
    obtenu = meilleur(page, hote)
    if obtenu == attendu:
        ok += 1
        print(f"  ok   {libelle:<48} → {obtenu}")
    else:
        ko += 1
        print(f"  ÉCHEC {libelle:<48} → {obtenu!r}  (attendu {attendu!r})")

# extraction des liens de contact
page = '''<a href="/contact">Contact</a><a href="/mentions-legales.html">Mentions</a>
<a href="/reparation">Réparation</a><a href="https://facebook.com/x">FB</a>
<a href="mailto:a@b.fr">m</a><a href="/nous-joindre/">Nous joindre</a>'''
liens = ms.pages_contact(page, "https://garage-a.fr/")
print("\nliens de contact retenus :", liens)
assert liens[0].endswith("/contact"), liens
assert not any("facebook" in l for l in liens)
assert not any("reparation" in l for l in liens)

# --- adresses d'enseigne : la fiche est une succursale, pas un independant
assert ms.est_enseigne("danielle.capelli.stismier02@reseau.renault.fr") == "renault.fr"
assert ms.est_enseigne("contact@garage-renault-du-coin.fr") == ""
assert ms.est_enseigne("x@ad.fr") == "ad.fr"
assert ms.est_enseigne("x@ad-carrosserie.fr") == ""
print("enseignes : ok")

# --- un domaine porte par plusieurs fiches est ecarte du vivier
import sqlite3, tempfile, os
_db = tempfile.mktemp(suffix=".db"); _c = sqlite3.connect(_db)
_c.execute("CREATE TABLE prospects (cle TEXT PRIMARY KEY, nom TEXT, commune TEXT,"
           " departement TEXT, site_web TEXT, site_statut TEXT, email TEXT)")
_l = [(f"ad{i}", f"AD {i}", "X", "01", "ad.fr", "propre", "") for i in range(5)]
_l += [("a", "Garage A", "X", "02", "garage-a.fr", "propre", ""),
       ("b", "Garage B", "X", "03", "www.garage-b.fr", "propre", "")]
_c.executemany("INSERT INTO prospects VALUES (?,?,?,?,?,?,?)", _l); _c.commit()
ms.migrer(_c)
assert sorted(x["cle"] for x in ms.vivier(_c, 0, False, "tous")) == ["a", "b"]
print("domaines partages : ok")
os.unlink(_db)

print(f"\n{ok} cas passés, {ko} échecs")
sys.exit(1 if ko else 0)
