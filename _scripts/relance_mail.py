#!/usr/bin/env python3
"""Relance par courriel des prospects contactes par courriel, a J+7.

Pour chaque prospect de _data/prospection.db dont le premier courriel date
d'au moins RELANCE_MAIL_JOURS jours (defaut 7) et qui n'a pas encore ete
relance :

  1. il a repondu (un message de lui dans la boite depuis le premier
     envoi)                 -> pas de relance, statut « a_repondu » ;
  2. il est dans _data/desinscrits.txt
                            -> pas de relance, statut « stop » ;
  3. le premier courriel n'a jamais quitte les Brouillons (introuvable dans
     « Messages envoyes ») -> on attend ; au-dela de 14 jours, statut
     « jamais_envoye » et on n'y revient plus ;
  4. sinon                  -> une seule relance, dans le meme fil
     (Re: + In-Reply-To), en brouillon ou envoyee selon MAIL_MODE.

Une seule relance par prospect, jamais deux. Plafond : MAILS_PAR_JOUR.
Lance chaque jour par run_relances.sh, apres relance_check.py.

Usage :
    .venv/bin/python _scripts/relance_mail.py --apercu
    .venv/bin/python _scripts/relance_mail.py
"""
from __future__ import annotations

import argparse
import imaplib
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import envoi_mail  # noqa: E402
import telegram    # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "prospection.db"
try:
    JOURS = int(os.environ.get("RELANCE_MAIL_JOURS") or 7)
except ValueError:
    JOURS = 7
ABANDON = 14   # jours apres lesquels un brouillon jamais parti est oublie

SUJETS = {"garage": "votre garage", "menuisier": "votre menuiserie",
          "nautique": "votre chantier naval"}


def corps_relance(p: dict) -> str:
    sujet = SUJETS.get(p.get("metier") or "", "votre activité")
    lignes = [
        "Bonjour,",
        "",
        "Je me permets de revenir vers vous au sujet du site de démonstration "
        f"que j'ai préparé pour {sujet} la semaine dernière.",
    ]
    if p.get("site_genere"):
        lignes += ["", "Il est toujours en ligne ici :", p["site_genere"]]
    lignes += [
        "",
        "Si le projet vous intéresse, je peux l'adapter à vos photos et à vos "
        "prestations ; sinon, un simple « non merci » me suffit et je ne vous "
        "relancerai plus.",
        "",
        "Bonne journée,",
        "",
        *envoi_mail.signature(),
    ]
    return "\n".join(lignes)


def _imap_date(iso: str) -> str:
    # pas de strftime("%b") : run_relances.sh tourne en fr_FR, ce qui
    # donnerait « oct. » au lieu de « Oct », refuse par IMAP
    d = datetime.fromisoformat(iso).date()
    mois = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()[d.month - 1]
    return f"{d.day:02d}-{mois}-{d.year}"


def _cherche(imap: imaplib.IMAP4_SSL, dossier: str, critere: str) -> list[bytes]:
    typ, _ = imap.select(dossier, readonly=True)
    if typ != "OK":
        raise envoi_mail.ErreurMail(f"dossier introuvable : {dossier}")
    typ, data = imap.search(None, critere)
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def _message_id(imap: imaplib.IMAP4_SSL, num: bytes) -> str:
    typ, data = imap.fetch(num, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
    if typ != "OK":
        return ""
    for part in data:
        if isinstance(part, tuple):
            t = part[1].decode("utf-8", "replace")
            if ":" in t:
                return t.split(":", 1)[1].strip()
    return ""


def noter(conn, cle: str, statut: str, quand: bool = False) -> None:
    conn.execute("UPDATE prospects SET mail_relance_statut=?, "
                 "mail_relance_at=COALESCE(?, mail_relance_at) WHERE cle=?",
                 (statut, datetime.now(timezone.utc).isoformat(timespec="seconds")
                  if quand else None, cle))
    conn.commit()


def relances_du_jour(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM prospects WHERE mail_relance_at IS NOT NULL AND "
        "date(mail_relance_at,'localtime') = date('now','localtime')").fetchone()[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apercu", action="store_true",
                    help="liste ce qui serait fait, sans rien deposer ni noter")
    a = ap.parse_args()

    if not envoi_mail.actif():
        print("Courriels inactifs (MAIL_MODE=off ou identifiants absents) : rien a faire.")
        return
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cols = {r[1] for r in conn.execute("PRAGMA table_info(prospects)")}
    if "mail_relance_at" not in cols:
        print("Aucun courriel encore envoye par le pipeline : rien a relancer.")
        return

    limite = (datetime.now(timezone.utc) - timedelta(days=JOURS)).isoformat()
    candidats = [dict(r) for r in conn.execute(
        "SELECT * FROM prospects WHERE mail_statut IN ('brouillon','envoye') "
        "AND mail_envoye_at <= ? AND mail_relance_at IS NULL "
        "AND COALESCE(mail_relance_statut,'') NOT IN "
        "('a_repondu','stop','jamais_envoye') ORDER BY mail_envoye_at",
        (limite,))]
    print(f"{len(candidats)} prospect(s) contacte(s) par courriel il y a {JOURS} jours ou plus")
    if not candidats:
        return

    stop = envoi_mail.desinscrits()
    bilan = {"relance": 0, "a_repondu": 0, "stop": 0, "attente": 0,
             "jamais_envoye": 0, "erreur": 0}
    imap = envoi_mail.connexion_imap()
    try:
        tous = envoi_mail.dossier_special(imap, "\\All", '"[Gmail]/All Mail"')
        envoyes = envoi_mail.dossier_special(imap, "\\Sent", '"[Gmail]/Sent Mail"')
        for p in candidats:
            nom, dest = p.get("nom") or "", (p.get("email") or "").strip()
            depuis = _imap_date(p["mail_envoye_at"])
            if dest.lower() in stop:
                print(f"  {nom} : desinscrit"); bilan["stop"] += 1
                if not a.apercu: noter(conn, p["cle"], "stop")
                continue
            if _cherche(imap, tous, f'(FROM "{dest}" SINCE {depuis})'):
                print(f"  {nom} : a repondu — pas de relance"); bilan["a_repondu"] += 1
                if not a.apercu: noter(conn, p["cle"], "a_repondu")
                continue
            partis = _cherche(imap, envoyes, f'(TO "{dest}" SINCE {depuis})')
            if not partis:
                age = (datetime.now(timezone.utc)
                       - datetime.fromisoformat(p["mail_envoye_at"])).days
                if age >= ABANDON:
                    print(f"  {nom} : brouillon jamais envoye depuis {age} j — abandonne")
                    bilan["jamais_envoye"] += 1
                    if not a.apercu: noter(conn, p["cle"], "jamais_envoye")
                else:
                    print(f"  {nom} : premier courriel encore en brouillon — on attend")
                    bilan["attente"] += 1
                continue
            if relances_du_jour(conn) >= envoi_mail.PAR_JOUR:
                print("  plafond quotidien atteint, la suite demain"); break
            mid = _message_id(imap, partis[0]) or p.get("mail_message_id") or ""
            objet = p.get("mail_objet") or "Votre site"
            if a.apercu:
                print(f"  {nom} <{dest}> : relance « Re: {objet} »")
                bilan["relance"] += 1
                continue
            try:
                statut, _ = envoi_mail.expedier(
                    dest, f"Re: {objet}", corps_relance(p),
                    entetes={"In-Reply-To": mid, "References": mid})
            except Exception as e:
                print(f"  /!\\ {nom} : {e}"); bilan["erreur"] += 1
                noter(conn, p["cle"], f"erreur: {e}"[:200])
                continue
            noter(conn, p["cle"], statut, quand=True)
            bilan["relance"] += 1
            print(f"  ✉ {nom} <{dest}> : relance {statut}")
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    print(f"Bilan : {bilan}")
    if a.apercu:
        return
    morceaux = []
    if bilan["relance"]:
        morceaux.append(f"{bilan['relance']} relance(s) "
                        + ("envoyee(s)" if envoi_mail.MODE == "envoi"
                           else "en brouillon dans Gmail, a relire"))
    if bilan["a_repondu"]:
        morceaux.append(f"{bilan['a_repondu']} ont repondu")
    if bilan["attente"]:
        morceaux.append(f"{bilan['attente']} premier(s) courriel(s) encore en "
                        "brouillon, non envoye(s)")
    if bilan["erreur"]:
        morceaux.append(f"{bilan['erreur']} erreur(s)")
    if morceaux:
        telegram.send("\U0001F501 Relances par courriel : " + ", ".join(morceaux))


if __name__ == "__main__":
    main()
