#!/usr/bin/env python3
"""Alerte Telegram quand un eleveur ouvre sa demo.

Un prospect qui regarde son site est le signal d'achat le plus fort de la
prospection : il vaut un appel dans la foulee, tant qu'on est frais dans sa
tete. Ce script interroge Umami, compare aux vues deja connues, et ne
signale que les NOUVELLES.

Le premier passage n'alerte pas : il enregistre le point de depart.

Usage :
    python3 _scripts/vues_check.py            # verification normale
    python3 _scripts/vues_check.py --test     # affiche la reponse brute d'Umami
    python3 _scripts/vues_check.py --bilan    # etat actuel, sans alerter
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import requests
import telegram

ETAT = Path(__file__).parent.parent / "_data" / "vues.json"
DB_PATH = Path(__file__).parent.parent / "_data" / "annonces.db"

# On ne derange pas la nuit : launchd reveille le script toutes les heures,
# mais une alerte a 3h du matin n'a aucune valeur.
HEURE_MIN, HEURE_MAX = 8, 21


def _cle() -> tuple[str, str]:
    """(url du Worker, jeton de lecture) depuis le .env."""
    valeurs = {}
    env = Path(__file__).parent.parent / ".env"
    if env.exists():
        for ligne in env.read_text(encoding="utf-8").splitlines():
            for nom in ("COMPTEUR_URL", "COMPTEUR_TOKEN"):
                if ligne.startswith(nom) and "=" in ligne:
                    valeurs[nom] = ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return valeurs.get("COMPTEUR_URL", ""), valeurs.get("COMPTEUR_TOKEN", "")


def _noms() -> dict[str, str]:
    """slug du site -> nom de l'elevage."""
    out = {}
    if not DB_PATH.exists():
        return out
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    for r in c.execute("SELECT site_slug, name FROM annonces "
                       "WHERE site_slug IS NOT NULL AND site_slug != ''"):
        out.setdefault(r["site_slug"], r["name"] or r["site_slug"])
    c.close()
    return out


def vues_par_site(url: str, jeton: str) -> dict[str, int]:
    """Vues cumulees par slug, lues sur le Worker Cloudflare."""
    r = requests.get(f"{url.rstrip('/')}/stats",
                     headers={"Authorization": f"Bearer {jeton}"},
                     timeout=30)
    if r.status_code == 401:
        raise RuntimeError("jeton refuse par le compteur (COMPTEUR_TOKEN)")
    if r.status_code != 200:
        raise RuntimeError(f"compteur HTTP {r.status_code}: {r.text[:200]}")
    return {slug: int(d.get("n") or 0) for slug, d in (r.json() or {}).items()}


def detail_par_site(url: str, jeton: str) -> dict:
    """Comme vues_par_site, mais en gardant les horodatages."""
    r = requests.get(f"{url.rstrip('/')}/stats",
                     headers={"Authorization": f"Bearer {jeton}"}, timeout=30)
    r.raise_for_status()
    return r.json() or {}


def charger() -> dict:
    if ETAT.exists():
        return json.loads(ETAT.read_text(encoding="utf-8"))
    return {"initialise": False, "vues": {}}


def sauver(e: dict) -> None:
    ETAT.parent.mkdir(parents=True, exist_ok=True)
    ETAT.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


def main(mode: str) -> int:
    url, jeton = _cle()
    if not url or not url.startswith("http"):
        print("COMPTEUR_URL absent du .env — rien a faire.")
        return 0
    if not jeton:
        print("COMPTEUR_TOKEN absent du .env — rien a faire.")
        return 0

    if mode == "test":
        print(json.dumps(detail_par_site(url, jeton), indent=1, ensure_ascii=False))
        return 0

    actuelles = vues_par_site(url, jeton)
    etat = charger()
    noms = _noms()

    if not etat["initialise"]:
        etat = {"initialise": True, "vues": actuelles}
        sauver(etat)
        print(f"Point de depart enregistre : {len(actuelles)} site(s) deja vus. "
              f"Les alertes commencent au prochain passage.")
        return 0

    nouveaux = []
    for slug, n in actuelles.items():
        avant = etat["vues"].get(slug, 0)
        if n > avant:
            nouveaux.append((slug, n - avant, n))

    if mode == "bilan":
        print(f"{len(actuelles)} site(s) avec des vues, "
              f"{len(nouveaux)} avec du nouveau depuis le dernier passage")
        for slug, delta, total in sorted(nouveaux, key=lambda x: -x[1]):
            print(f"  {noms.get(slug, slug):<34} +{delta} (total {total})")
        return 0

    heure = datetime.now().hour
    if nouveaux and not (HEURE_MIN <= heure < HEURE_MAX):
        print(f"{len(nouveaux)} nouveaute(s), mais il est {heure}h — "
              f"alerte reportee au prochain passage.")
        return 0

    for slug, delta, total in sorted(nouveaux, key=lambda x: -x[1]):
        nom = noms.get(slug, slug)
        msg = (f"👀 *{nom}* vient de regarder sa démo\n\n"
               f"+{delta} vue(s) — {total} au total\n"
               f"https://francoislang.github.io/templates/{slug}\n\n"
               f"_Bon moment pour appeler._")
        try:
            telegram.send(msg)
        except Exception as e:
            print(f"  alerte Telegram impossible pour {slug}: {e}")
        print(f"  ALERTE {nom} +{delta}")

    etat["vues"] = actuelles
    sauver(etat)
    print(f"Bilan : {len(nouveaux)} alerte(s) envoyee(s), "
          f"{len(actuelles)} site(s) suivis.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--bilan", action="store_true")
    a = ap.parse_args()
    try:
        sys.exit(main("test" if a.test else "bilan" if a.bilan else "normal"))
    except Exception as e:
        print(f"ERREUR : {e}")
        sys.exit(1)
