#!/usr/bin/env python3
"""Remplace les brouillons Gmail des prospects encore « Nouveau » dans le CRM
par le courriel actuel (pipeline_pro.objet_mail + pipeline_pro.pitch).

Seuls les courriels restes en BROUILLON sont touches : un courriel deja
envoye n'est jamais refait. L'ancien brouillon est retrouve par son
Message-ID et supprime, le nouveau est depose a sa place, la base est mise
a jour (mail_message_id, mail_objet). L'URL de la demo ne change pas.

    python3 _scripts/refaire_brouillons.py              liste, ne touche a rien
    python3 _scripts/refaire_brouillons.py --montrer    affiche aussi le texte
    python3 _scripts/refaire_brouillons.py --appliquer  remplace dans Gmail
"""
from __future__ import annotations

import argparse
import imaplib
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import envoi_mail                       # noqa: E402
import pipeline_pro as pp               # noqa: E402
from regenerer_nouveau import numeros_nouveau  # noqa: E402

DB = Path(__file__).parent.parent / "_data" / "prospection.db"


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--appliquer", action="store_true")
    a.add_argument("--montrer", action="store_true")
    x = a.parse_args()

    nums = numeros_nouveau()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cibles = []
    for r in conn.execute("SELECT * FROM prospects WHERE COALESCE(crm_issue,'') <> ''"):
        num = int(str(r["crm_issue"]).rstrip("/").rsplit("/", 1)[-1] or 0)
        if num not in nums:
            continue
        p = dict(r)
        if not (p.get("email") or "").strip():
            print(f"  - #{num:<4} {p['nom'][:38]:38} pas de courriel")
            continue
        if p.get("mail_statut") != "brouillon":
            print(f"  - #{num:<4} {p['nom'][:38]:38} statut « {p.get('mail_statut')} » : pas touche")
            continue
        cibles.append((num, p))

    print(f"\n{len(nums)} annonce(s) « Nouveau », {len(cibles)} brouillon(s) a refaire\n")
    imap = dossier = None
    if x.appliquer and cibles:
        imap = envoi_mail.connexion_imap()
        dossier = envoi_mail._dossier_brouillons(imap)
        imap.select(dossier)

    faits = 0
    for num, p in cibles:
        url = (p.get("site_genere") or "").strip() or None
        objet = pp.objet_mail(p)
        corps = pp.pitch(p, p.get("metier") or "", url)
        print(f"  ✓ #{num:<4} {p['nom'][:38]:38} {p['email']:34} « {objet} »")
        if x.montrer:
            print("      " + corps.replace("\n", "\n      ") + "\n")
        if not x.appliquer:
            continue
        ancien = (p.get("mail_message_id") or "").strip()
        supprime = False
        if ancien:
            typ, d = imap.search(None, "HEADER", "Message-ID", ancien)
            ids = (d[0] or b"").split() if typ == "OK" else []
            for i in ids:
                imap.store(i, "+FLAGS", "\\Deleted")
            if ids:
                imap.expunge()
                supprime = True
        m = envoi_mail.construire(p["email"], objet, corps)
        typ, rep = imap.append(dossier, "(\\Draft)",
                               imaplib.Time2Internaldate(time.time()), m.as_bytes())
        if typ != "OK":
            print(f"      /!\\ depot refuse : {rep}")
            continue
        conn.execute("UPDATE prospects SET mail_message_id=?, mail_objet=? WHERE cle=?",
                     (m["Message-ID"], objet, p["cle"]))
        conn.commit()
        faits += 1
        print("      ancien brouillon supprime" if supprime else
              "      /!\\ ancien brouillon introuvable (deja envoye ou supprime ?) : verifie Gmail")
    if imap:
        imap.logout()
    if x.appliquer:
        print(f"\n{faits} brouillon(s) remplace(s).")
    else:
        print("\nRien n'a ete modifie. --montrer pour voir les textes, --appliquer pour remplacer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
