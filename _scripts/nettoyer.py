#!/usr/bin/env python3
"""Remet au propre la base de prospects apres une collecte.

Deux passes, toutes deux nees de defauts constates sur les vraies donnees :

  --reseaux   Reclasse les enseignes de reseau qui ont echappe au filtre.
              La liste d'origine ignorait toute la categorie pare-brise :
              GlassAuto pesait a lui seul 104 faux prospects, plus Carglass,
              Mondial Pare-Brise, France Pare-Brise, Motrio, BestDrive...
              Environ 200 lignes sur 2400. Aucun appel reseau.

  --communes  Complete commune et code postal par geocodage inverse.
              66 % des prospects n'avaient ni l'un ni l'autre, alors que tous
              ont des coordonnees GPS. Sans commune, le pitch tombe sur son
              repli (« dans votre secteur » au lieu de « a Vitre ») et le
              site perd son referencement local.
              Source : API Adresse du gouvernement, gratuite, sans cle,
              en un seul envoi groupe.

Usage :
    python3 _scripts/nettoyer.py              les deux passes
    python3 _scripts/nettoyer.py --reseaux
    python3 _scripts/nettoyer.py --communes
    python3 _scripts/nettoyer.py --apercu     ce qui serait change, sans ecrire
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "prospection.db"
API_REVERSE = "https://api-adresse.data.gouv.fr/reverse/csv/"
LOT = 1000          # l'API accepte bien plus, mais on reste raisonnable

# Enseignes manquantes dans la liste d'origine, relevees dans les donnees
# reelles. Le reflexe a garder : un nom qui revient plusieurs fois chez des
# « independants » est presque toujours un reseau.
RESEAUX_SUP = {
    # pare-brise — categorie entierement oubliee au depart
    "glassauto", "glass auto", "carglass", "mondial pare-brise", "mondial pare brise",
    "france pare-brise", "france pare brise", "rapid pare-brise", "rapid pare brise",
    "a+glass", "a+ glass", "ouiglass", "oui glass", "glass expert", "cabinet glass",
    "pare-brise", "pare brise",
    # reseaux d'entretien
    "motrio", "bestdrive", "best drive", "siligom", "auto primo", "autoprimo",
    "repareco", "eurorepar", "euro repar", "garage ad", "ad carrosserie",
    "precisium", "axial", "five star", "identicar", "mecanic system",
    "carrosserie ad",
    # controle technique
    "dekra", "securitest", "autovision", "autosur", "controle technique",
    "vivauto", "auto securite",
}


def _sans_accents(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c))


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", _sans_accents(t).lower()).strip()


# Le nom ne dit pas tout : « Garage Martin » affilie a Top Garage porte un
# nom d'independant mais un site de reseau. Le domaine, lui, ne ment pas.
# 889 fiches du vivier refonte -- 27 % -- sont dans ce cas.
HOTES_RESEAU = (
    "top-garage.fr", "concessions.peugeot", "delko.", "avatacar.", "aplusglass",
    "renault.fr", "dacia.fr", "citroen.fr", "peugeot.fr", "opel.fr", "ford.fr",
    "toyota.fr", "nissan.fr", "volkswagen.fr", "audi.fr", "norauto.fr",
    "midas.fr", "feuvert.fr", "speedy.fr", "euromaster.fr", "point-s.fr",
    "carglass.fr", "monsieur-pare-brise", "france-pare-brise",
    "mondial-parebrise", "rapid-pare-brise", "bosch-car-service", "adexpert.fr",
    "garage-ad.fr", "vulco.", "profilplus.", "siligom.", "motrio.",
    "bestdrive.", "eurorepar.", "precisium", "autobacs", "carter-cash",
    "securitest", "autovision", "autosur", "dekra", "controle-technique",
    "auto-securite", "vivauto", "identicar", "five-star",
)


def est_reseau(nom: str, site: str = "") -> str | None:
    """Retourne l'enseigne reconnue, ou None. Le nom, puis le domaine."""
    n = _norm(nom)
    for r in RESEAUX_SUP:
        if r in n:
            return r
    s = (site or "").lower()
    for h in HOTES_RESEAU:
        if h in s:
            return h
    return None


# --------------------------------------------------------------------------

def passe_reseaux(conn, apercu: bool) -> int:
    # Les deux viviers, pas seulement celui des sans-site. La premiere version
    # ne traitait que « aucun », si bien que 889 succursales de reseau sont
    # restees dans le vivier refonte -- Delko, A+ Glass, Top Garage, des
    # concessions Peugeot -- pretes a etre demarchees comme des independants.
    lignes = conn.execute(
        "SELECT cle, nom, COALESCE(site_web,'') FROM prospects "
        "WHERE site_statut IN ('aucun','propre')").fetchall()
    touches = [(c, n, est_reseau(n, s)) for c, n, s in lignes]
    touches = [(c, n, e) for c, n, e in touches if e]
    par_enseigne: dict[str, int] = {}
    for _, _, e in touches:
        par_enseigne[e] = par_enseigne.get(e, 0) + 1

    print(f"\n{len(touches)} lignes a reclasser en « reseau » :")
    for e, n in sorted(par_enseigne.items(), key=lambda x: -x[1])[:15]:
        print(f"  {n:5}  {e}")
    if len(par_enseigne) > 15:
        print(f"  ... et {len(par_enseigne)-15} autres enseignes")

    if apercu:
        print("  (apercu : rien n'a ete ecrit)")
        return 0
    conn.executemany("UPDATE prospects SET site_statut='reseau' WHERE cle=?",
                     [(c,) for c, _, _ in touches])
    conn.commit()
    return len(touches)


def passe_communes(conn, apercu: bool) -> int:
    try:
        import requests
    except ImportError:
        sys.exit("Le module requests est necessaire : pip install requests")

    lignes = conn.execute("""
        SELECT cle, latitude, longitude FROM prospects
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
          AND (COALESCE(commune,'')='' OR COALESCE(code_postal,'')='')
    """).fetchall()
    print(f"\n{len(lignes)} lignes sans commune ou sans code postal, "
          f"toutes avec des coordonnees GPS.")
    if apercu:
        print("  (apercu : rien n'a ete envoye ni ecrit)")
        return 0
    if not lignes:
        return 0

    total = 0
    for debut in range(0, len(lignes), LOT):
        lot = lignes[debut:debut + LOT]
        tampon = io.StringIO()
        w = csv.writer(tampon)
        w.writerow(["cle", "latitude", "longitude"])
        for cle, lat, lon in lot:
            w.writerow([cle, f"{lat:.6f}", f"{lon:.6f}"])

        print(f"  envoi {debut+1}-{debut+len(lot)} sur {len(lignes)}...", end=" ", flush=True)
        try:
            r = requests.post(
                API_REVERSE,
                files={"data": ("points.csv", tampon.getvalue(), "text/csv")},
                timeout=180)
            r.raise_for_status()
        except Exception as e:
            print(f"echec ({type(e).__name__}) — on continue")
            continue

        maj = []
        for row in csv.DictReader(io.StringIO(r.text)):
            ville = (row.get("result_city") or "").strip()
            cp = (row.get("result_postcode") or "").strip()
            if ville or cp:
                maj.append((ville or None, cp or None, row["cle"]))
        # COALESCE(NULLIF(...)) : on ne remplace que ce qui est vide, jamais
        # une valeur que la source d'origine avait fournie.
        conn.executemany("""UPDATE prospects
            SET commune     = COALESCE(NULLIF(commune,''), ?),
                code_postal = COALESCE(NULLIF(code_postal,''), ?)
            WHERE cle = ?""", maj)
        conn.commit()
        total += len(maj)
        print(f"{len(maj)} completees")
    return total


def etat(conn) -> None:
    P = ("FROM prospects WHERE site_statut='aucun' "
         "AND COALESCE(telephone,'')<>'' AND traite_at IS NULL")
    q = lambda s: conn.execute(s).fetchone()[0]
    t = q(f"SELECT COUNT(*) {P}")
    print(f"\n=== {t} prospects exploitables ===")
    for lib, col in (("commune", "commune"), ("code postal", "code_postal")):
        n = q(f"SELECT COUNT(*) {P} AND COALESCE({col},'')=''")
        print(f"  sans {lib:12} : {n:5}  ({100*n/t:.0f}%)" if t else "")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reseaux", action="store_true")
    p.add_argument("--communes", action="store_true")
    p.add_argument("--apercu", action="store_true",
                   help="montre ce qui serait change, sans rien ecrire")
    a = p.parse_args()
    tout = not (a.reseaux or a.communes)

    if not DB_PATH.exists():
        sys.exit(f"{DB_PATH} introuvable. Lance collecte_osm.py d'abord.")
    conn = sqlite3.connect(str(DB_PATH))
    etat(conn)
    if a.reseaux or tout:
        n = passe_reseaux(conn, a.apercu)
        if n:
            print(f"  -> {n} lignes reclassees")
    if a.communes or tout:
        n = passe_communes(conn, a.apercu)
        if n:
            print(f"  -> {n} communes completees")
    if not a.apercu:
        etat(conn)
    conn.close()


if __name__ == "__main__":
    main()
