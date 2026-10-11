"""Appel des modeles de generation, avec repli d'un fournisseur sur l'autre.

DeepSeek en direct d'abord (DEEPSEEK_API_KEY), OpenRouter en secours
(OPENROUTER_API_KEY, ou l'ancienne ANTHROPIC_API_KEY qui contient en realite
une cle OpenRouter « sk-or- »). Un credit epuise chez l'un ne bloque plus la
chaine tant que l'autre repond — c'est ce qui a fait tourner les eleveurs en
template de repli du 2 au 9 octobre 2026 (HTTP 402 OpenRouter).

Les noms de modeles restent ceux d'OpenRouter (« deepseek/deepseek-v4-pro ») :
le prefixe est retire pour l'API DeepSeek. Un modele qui n'est pas chez
DeepSeek (autre editeur, variante « :free ») part directement sur OpenRouter.

Les erreurs gardent la forme « HTTP 402 », « reponse vide »… : pipeline_pro.py
les trie par sous-chaine (PASSAGERES / FATALES).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
_FICHIERS_ENV = (REPO_ROOT / ".env", Path.home() / ".hermes" / ".env")

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Ces refus ne s'arrangent pas en reessayant : on passe au fournisseur suivant.
_REFUS_DEFINITIFS = (401, 402, 403)


def lire_cle(nom: str) -> str:
    """Variable d'environnement, sinon .env du depot, sinon ~/.hermes/.env."""
    v = os.environ.get(nom, "").strip()
    if v:
        return v
    for fp in _FICHIERS_ENV:
        if not fp.exists():
            continue
        for ligne in fp.read_text(encoding="utf-8").splitlines():
            if ligne.startswith(nom + "="):
                v = ligne.split("=", 1)[1].strip().strip('"').strip("'")
                if v:
                    return v
    return ""


def fournisseurs(modele: str) -> list[tuple[str, str, str, str]]:
    """[(nom, url, cle, modele_tel_que_le_fournisseur_l_attend)] par priorite."""
    liste = []
    cle_ds = lire_cle("DEEPSEEK_API_KEY")
    if cle_ds and modele.startswith("deepseek/") and ":" not in modele:
        liste.append(("DeepSeek", DEEPSEEK_URL, cle_ds, modele.split("/", 1)[1]))
    cle_or = lire_cle("OPENROUTER_API_KEY")
    if not cle_or:
        ancienne = lire_cle("ANTHROPIC_API_KEY")
        if ancienne.startswith("sk-or-"):
            cle_or = ancienne
    if cle_or:
        liste.append(("OpenRouter", OPENROUTER_URL, cle_or, modele))
    return liste


def disponible(modele: str) -> bool:
    return bool(fournisseurs(modele))


def _lire_flux(r) -> str:
    # decode_unicode=True ferait confiance a l'en-tete HTTP : sans charset
    # explicite, requests retombe sur ISO-8859-1 et les accents ressortent
    # en double encodage. On decode nous-memes en UTF-8.
    morceaux = []
    for brute in r.iter_lines(decode_unicode=False):
        if not brute:
            continue
        ligne = brute.decode("utf-8", "replace")
        if not ligne.startswith("data: "):
            continue
        corps = ligne[6:]
        if corps.strip() == "[DONE]":
            break
        try:
            delta = json.loads(corps)["choices"][0].get("delta", {})
        except (ValueError, KeyError, IndexError):
            continue
        if delta.get("content"):
            morceaux.append(delta["content"])
    return "".join(morceaux)


def generer(prompt: str, modele: str, max_tokens: int, flux: bool = True,
            timeout=(30, 900), tentatives: int = 2) -> tuple[str, str]:
    """Renvoie (texte, "") ou ("", raison_du_dernier_echec)."""
    fours = fournisseurs(modele)
    if not fours:
        return "", "OPENROUTER_API_KEY absente (et DEEPSEEK_API_KEY absente)"
    derniere = ""
    for nom, url, cle, nom_modele in fours:
        print(f"   modele : {nom} {nom_modele}")
        payload = {"model": nom_modele,
                   "messages": [{"role": "user", "content": prompt}],
                   "max_tokens": max_tokens, "stream": flux}
        for tentative in range(1, tentatives + 1):
            try:
                r = requests.post(url, headers={"Authorization": f"Bearer {cle}",
                                                "Content-Type": "application/json"},
                                  json=payload, timeout=timeout, stream=flux)
                if r.status_code != 200:
                    derniere = f"{nom} HTTP {r.status_code}"
                    print(f"   /!\\ {derniere} ({tentative}/{tentatives})")
                    if r.status_code in _REFUS_DEFINITIFS:
                        break
                    continue
                if flux:
                    texte = _lire_flux(r)
                else:
                    r.encoding = "utf-8"
                    texte = r.json()["choices"][0]["message"].get("content") or ""
                if texte.strip():
                    return texte, ""
                derniere = f"{nom} reponse vide"
                print(f"   /!\\ {derniere} ({tentative}/{tentatives})")
            except requests.exceptions.RequestException as e:
                derniere = f"{nom} {type(e).__name__}"
                print(f"   /!\\ {derniere} ({tentative}/{tentatives})")
                time.sleep(5)
            except (ValueError, KeyError, IndexError) as e:
                derniere = f"{nom} reponse vide (illisible : {type(e).__name__})"
                print(f"   /!\\ {derniere} ({tentative}/{tentatives})")
        if len(fours) > 1 and nom != fours[-1][0]:
            print(f"   -> repli sur {fours[fours.index((nom, url, cle, nom_modele)) + 1][0]}")
    return "", derniere or "echec inconnu"
