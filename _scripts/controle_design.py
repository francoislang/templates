#!/usr/bin/env python3
"""Controle deterministe du rendu, avant que le site parte au prospect.

Impeccable (Apache-2.0, https://github.com/pbakaus/impeccable) embarque des
regles qui reperent les tics visuels des pages generees : halo radial derriere
le hero, tuile d'icone empilee au-dessus d'un titre, echelle typographique
plate, texte fonctionnel sous 11 px, contraste insuffisant, surtitre au-dessus
de chaque h2. Aucun modele, aucune cle API : un binaire rend la page dans un
Chrome et mesure.

Deux modes existent, et le choix n'est pas neutre. Le scan de fichier fait une
analyse statique qui ne sait pas lire une regle a selecteurs groupes
(« .a,.b{...} ») : elle a signale huit paddings absents qui etaient bien la.
On sert donc la page sur un port local et on scanne l'URL, ce qui passe par un
vrai navigateur. Mesure sur le gabarit garage : 14 faux defauts en mode
fichier contre 9 vrais en mode URL.

Si aucun Chrome n'est trouve, pointer IMPECCABLE_BROWSER sur un navigateur
base sur Chromium (Brave convient). Sans navigateur, le controle est saute :
il ne bloque jamais une generation.

    python3 _scripts/controle_design.py chemin/vers/dossier
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

DELAI = 240          # le premier appel telecharge le moteur
FICHIER = "index.html"


@functools.lru_cache(maxsize=1)
def disponible() -> bool:
    """npx present ? Sinon le controle est saute, jamais bloquant."""
    try:
        return subprocess.run(["npx", "--version"], capture_output=True,
                              timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class _Muet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):  # pas de bruit dans la sortie du pipeline
        pass


def _servir(dossier: Path):
    gest = functools.partial(_Muet, directory=str(dossier))
    srv = socketserver.TCPServer(("127.0.0.1", 0), gest)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def analyser(dossier: Path, fichier: str = FICHIER) -> tuple[list[dict], str]:
    """Retourne (constats, erreur). Une erreur ne doit jamais tout arreter."""
    if not disponible():
        return [], "npx absent"
    if not (Path(dossier) / fichier).exists():
        return [], f"{fichier} introuvable dans {dossier}"

    srv = None
    try:
        srv, port = _servir(Path(dossier))
        env = dict(os.environ)
        # Chrome refuse son bac a sable quand le processus tourne en root ;
        # CI=1 est le drapeau qu'Impeccable lit pour ajouter --no-sandbox.
        env.setdefault("CI", "1")
        r = subprocess.run(
            ["npx", "--yes", "impeccable", "detect",
             f"http://127.0.0.1:{port}/{fichier}", "--json"],
            capture_output=True, text=True, timeout=DELAI, env=env)
        # 0 = rien a signaler, 2 = des constats, 1 = cible non scannable
        # (typiquement : aucun Chrome installe, voir IMPECCABLE_BROWSER).
        if r.returncode == 1 or not r.stdout.strip():
            derniere = (r.stderr.strip().splitlines() or ["sortie vide"])[-1]
            return [], derniere.removeprefix("Error: ").strip()[:200]
        return json.loads(r.stdout), ""
    except subprocess.TimeoutExpired:
        return [], f"delai depasse ({DELAI}s)"
    except (OSError, ValueError) as e:
        return [], f"{type(e).__name__}: {e}"
    finally:
        if srv:
            srv.shutdown()
            srv.server_close()


def echecs(constats: list[dict]) -> list[dict]:
    """Les avis ne comptent pas : ils ne doivent jamais bloquer une sortie."""
    return [c for c in constats if c.get("severity") != "advisory"]


def resume(constats: list[dict]) -> str:
    """Le texte renvoye au modele pour qu'il corrige lui-meme."""
    lignes = []
    for c in echecs(constats):
        lignes.append(f"- [{c['antipattern']}] {c.get('snippet','')}\n"
                      f"  Correction attendue : {c.get('description','')}")
    return "\n".join(lignes)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cible = Path(sys.argv[1])
    dossier, fichier = (cible.parent, cible.name) if cible.is_file() else (cible, FICHIER)
    constats, err = analyser(dossier, fichier)
    if err:
        sys.exit(f"controle impossible : {err}")
    mauvais = echecs(constats)
    for c in mauvais:
        print(f"  [{c['antipattern']}] {c.get('snippet','')}")
    avis = len(constats) - len(mauvais)
    print(f"\n{len(mauvais)} defaut(s), {avis} avis")
    sys.exit(2 if mauvais else 0)


if __name__ == "__main__":
    main()
