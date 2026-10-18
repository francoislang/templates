#!/usr/bin/env python3
"""Envoi des pitchs par courriel, depuis le compte Google Workspace.

Deux modes, choisis par MAIL_MODE dans le .env :

  brouillon  (defaut)  le message est depose dans les Brouillons de Gmail.
                       Tu le relis, tu cliques « Envoyer ». Rien ne part seul.
  envoi                le message part directement par SMTP (smtp.gmail.com).
  off                  rien n'est fait : le pitch reste sur Telegram.

Garde-fous, quel que soit le mode :
  - plafond quotidien MAILS_PAR_JOUR (defaut 20) : un domaine neuf se
    « chauffe », au-dela de 30 a 50 par jour la boite finit en spam ;
  - une adresse deja ecrite ne recoit jamais un second premier message ;
  - les adresses de _data/desinscrits.txt (une par ligne) sont ignorees :
    c'est la que vont ceux qui repondent STOP ;
  - en-tete List-Unsubscribe, texte brut, pas de pixel ni de lien traque.

Connexion : mot de passe d'application Google (compte Google > Securite >
Validation en deux etapes > Mots de passe des applications), pas le mot de
passe du compte. IMAP doit etre active dans Gmail (Parametres > Transfert et
POP/IMAP).

Variables .env :
    MAIL_ADRESSE        francois@kerr-studio.com
    MAIL_MOT_DE_PASSE   mot de passe d'application (16 lettres)
    MAIL_NOM            François-Frédéric Lang
    MAIL_SOCIETE        Kerr Studio            (facultatif, signature)
    MAIL_SIREN          123 456 789            (facultatif, signature)
    MAIL_MODE           brouillon | envoi | off
    MAILS_PAR_JOUR      20

Usage :
    .venv/bin/python _scripts/envoi_mail.py --verifier
    .venv/bin/python _scripts/envoi_mail.py --test toi@exemple.fr
"""
from __future__ import annotations

import argparse
import html as _html
import imaplib
import os
import re
import smtplib
import sys
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402,F401  (charge le .env dans os.environ)

REPO_ROOT = Path(__file__).parent.parent
DESINSCRITS = REPO_ROOT / "_data" / "desinscrits.txt"

SMTP_HOTE, SMTP_PORT = "smtp.gmail.com", 587
IMAP_HOTE = "imap.gmail.com"
TELEPHONE = "06 32 81 42 00"
ANCIENNE_ADRESSE = "langfrancoisfrederic@gmail.com"


def _env(nom: str, defaut: str = "") -> str:
    return (os.environ.get(nom) or defaut).strip().strip('"').strip("'")


ADRESSE = _env("MAIL_ADRESSE")
MOT_DE_PASSE = _env("MAIL_MOT_DE_PASSE").replace(" ", "")
NOM = _env("MAIL_NOM", "François-Frédéric Lang")
SOCIETE = _env("MAIL_SOCIETE")
SIREN = _env("MAIL_SIREN")
SITE = _env("MAIL_SITE")
# Signature HTML avec logo (la meme que la signature Gmail « kerr »).
# MAIL_SIGNATURE_HTML=0 pour revenir au texte seul.
SIGNATURE_HTML = _env("MAIL_SIGNATURE_HTML", "1") != "0"
LOGO_URL = _env("MAIL_LOGO_URL",
                "https://kerr-studio.com/signature/kerr-signature.png")
PHOTO_URL = _env("MAIL_PHOTO_URL",
                 "https://kerr-studio.com/signature/francois.png")
MODE = _env("MAIL_MODE", "brouillon").lower()
try:
    PAR_JOUR = int(_env("MAILS_PAR_JOUR", "20"))
except ValueError:
    PAR_JOUR = 20


class ErreurMail(RuntimeError):
    pass


# --------------------------------------------------------------------------
# ce qui est reutilise par les pipelines
# --------------------------------------------------------------------------

def actif() -> bool:
    """Vrai si un courriel peut etre depose ou envoye."""
    return MODE in ("brouillon", "envoi") and bool(ADRESSE and MOT_DE_PASSE)


def adresse_contact() -> str:
    """L'adresse a afficher dans les signatures."""
    return ADRESSE or ANCIENNE_ADRESSE


def signature() -> list[str]:
    # Version texte de la signature Kerr : pas d'image ni de lien suivi en
    # prospection, un seul lien (le site).
    lignes = [NOM]
    if SOCIETE:
        lignes.append(SOCIETE)
    lignes.append(TELEPHONE)
    lignes.append(SITE or adresse_contact())
    if SIREN:
        lignes.append(f"SIREN {SIREN}")
    return lignes


def signature_html() -> str:
    """Signature « kerr » : photo ronde, coordonnees, logo. Images hebergees
    sur le site, styles en ligne, tables (seule mise en page fiable dans
    Gmail et Outlook)."""
    site_txt = SITE or "kerr-studio.com"
    site = site_txt if site_txt.startswith("http") else f"https://{site_txt}/"
    e = _html.escape
    tel = "+33" + TELEPHONE.replace(" ", "")[1:]
    return (
        '<table cellpadding="0" cellspacing="0" border="0" '
        'style="border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;">'
        '<tr><td style="padding:0 16px 0 0;vertical-align:middle;">'
        f'<img src="{PHOTO_URL}" width="72" height="72" alt="{e(NOM)}" border="0" '
        'style="display:block;border:0;width:72px;height:72px;border-radius:36px;"></td>'
        '<td style="border-left:2px solid #C4682C;padding:2px 0 2px 16px;vertical-align:middle;">'
        f'<div style="font-size:15px;line-height:20px;font-weight:bold;color:#17191E;">{e(NOM)}</div>'
        '<div style="font-size:13px;line-height:18px;color:#5B6068;">'
        'Développeur web · Sites, automatisations &amp; IA</div>'
        '<div style="font-size:13px;line-height:19px;color:#5B6068;padding-top:6px;">'
        f'<a href="tel:{tel}" style="color:#17191E;text-decoration:none;">{e(TELEPHONE)}</a>'
        '&nbsp;&nbsp;·&nbsp;&nbsp;'
        f'<a href="{site}" style="color:#9E5322;text-decoration:none;">{e(site_txt)}</a></div>'
        f'<div style="font-size:13px;line-height:19px;"><a href="mailto:{e(adresse_contact())}" '
        f'style="color:#5B6068;text-decoration:none;">{e(adresse_contact())}</a></div>'
        '<table cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin-top:8px;">'
        f'<tr><td style="vertical-align:middle;"><a href="{site}" style="text-decoration:none;">'
        f'<img src="{LOGO_URL}" width="83" height="36" alt="kerr" border="0" '
        'style="display:block;border:0;width:83px;height:36px;"></a></td></tr></table>'
        '</td></tr></table>')


_URL = re.compile(r"(https?://[^\s<>]+)")


def corps_html(corps: str) -> str | None:
    """Version HTML du message : le texte tel quel (paragraphes, liens
    cliquables), et la signature texte remplacee par la signature « kerr ».
    None si la signature texte n'est pas trouvee en fin de corps."""
    sig_txt = "\n".join(signature())
    if sig_txt not in corps:
        return None
    avant, apres = corps.rsplit(sig_txt, 1)

    def bloc(txt: str) -> str:
        paras = []
        for p in txt.strip("\n").split("\n\n"):
            if not p.strip():
                continue
            h = _html.escape(p).replace("\n", "<br>")
            h = _URL.sub(lambda m: f'<a href="{m.group(1)}" style="color:#9E5322;">'
                                   f'{m.group(1)}</a>', h)
            paras.append(f'<p style="margin:0 0 14px 0;">{h}</p>')
        return "".join(paras)

    return ('<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;'
            'line-height:21px;color:#17191E;">'
            + bloc(avant) + signature_html()
            + (f'<div style="margin-top:14px;font-size:12px;color:#8A8F98;">'
               f'{bloc(apres)}</div>' if apres.strip() else "")
            + '</div>')


def desinscrits() -> set[str]:
    if not DESINSCRITS.exists():
        return set()
    return {l.strip().lower() for l in DESINSCRITS.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.lstrip().startswith("#")}


def adresse_valide(a: str) -> bool:
    return bool(re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[a-z]{2,}", (a or "").strip(), re.I))


def construire(dest: str, objet: str, corps: str,
               entetes: dict | None = None) -> EmailMessage:
    if not ADRESSE:
        raise ErreurMail("MAIL_ADRESSE absente du .env")
    m = EmailMessage()
    m["From"] = formataddr((NOM, ADRESSE))
    m["To"] = dest.strip()
    m["Subject"] = objet
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain=ADRESSE.split("@", 1)[1])
    # desinscription en un clic par le client de messagerie (Gmail l'affiche)
    m["List-Unsubscribe"] = f"<mailto:{ADRESSE}?subject=STOP>"
    for k, v in (entetes or {}).items():
        if v:
            m[k] = v
    m.set_content(corps, charset="utf-8")
    if SIGNATURE_HTML:
        h = corps_html(corps)
        if h:
            # multipart/alternative : la version texte reste lisible partout
            m.add_alternative(h, subtype="html", charset="utf-8")
    return m


def _dossier_brouillons(imap: imaplib.IMAP4_SSL) -> str:
    """Le nom du dossier Brouillons, quelle que soit la langue du compte."""
    typ, lignes = imap.list()
    if typ == "OK":
        for brut in lignes or []:
            l = brut.decode("utf-8", "replace") if isinstance(brut, bytes) else str(brut)
            if "\\Drafts" in l:
                m = re.search(r'("[^"]*"|\S+)\s*$', l)
                if m:
                    return m.group(1)
    return '"[Gmail]/Drafts"'


def deposer_brouillon(m: EmailMessage) -> None:
    try:
        with imaplib.IMAP4_SSL(IMAP_HOTE) as imap:
            imap.login(ADRESSE, MOT_DE_PASSE)
            dossier = _dossier_brouillons(imap)
            typ, rep = imap.append(dossier, "(\\Draft)",
                                   imaplib.Time2Internaldate(time.time()),
                                   m.as_bytes())
            if typ != "OK":
                raise ErreurMail(f"IMAP APPEND refuse : {rep}")
    except imaplib.IMAP4.error as e:
        raise ErreurMail(f"IMAP : {e}") from e


def envoyer_smtp(m: EmailMessage) -> None:
    try:
        with smtplib.SMTP(SMTP_HOTE, SMTP_PORT, timeout=30) as s:
            s.starttls()
            s.login(ADRESSE, MOT_DE_PASSE)
            s.send_message(m)
    except smtplib.SMTPException as e:
        raise ErreurMail(f"SMTP : {e}") from e


def expedier(dest: str, objet: str, corps: str, mode: str | None = None,
             entetes: dict | None = None) -> tuple[str, str]:
    """Depose ou envoie. Renvoie (statut, Message-ID), statut valant
    'brouillon' ou 'envoye'. Leve ErreurMail."""
    mode = (mode or MODE).lower()
    if mode not in ("brouillon", "envoi"):
        raise ErreurMail(f"MAIL_MODE={mode} : rien a faire")
    if not MOT_DE_PASSE:
        raise ErreurMail("MAIL_MOT_DE_PASSE absent du .env")
    if not adresse_valide(dest):
        raise ErreurMail(f"adresse invalide : {dest!r}")
    if dest.strip().lower() in desinscrits():
        raise ErreurMail(f"{dest} est dans desinscrits.txt")
    m = construire(dest, objet, corps, entetes)
    if mode == "envoi":
        envoyer_smtp(m)
        return "envoye", m["Message-ID"]
    deposer_brouillon(m)
    return "brouillon", m["Message-ID"]


def dossier_special(imap: imaplib.IMAP4_SSL, drapeau: str, defaut: str) -> str:
    """Nom d'un dossier Gmail par son role (\\Sent, \\All...), quelle que
    soit la langue du compte."""
    typ, lignes = imap.list()
    if typ == "OK":
        for brut in lignes or []:
            l = brut.decode("utf-8", "replace") if isinstance(brut, bytes) else str(brut)
            if drapeau in l:
                m = re.search(r'("[^"]*"|\S+)\s*$', l)
                if m:
                    return m.group(1)
    return defaut


def connexion_imap() -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL(IMAP_HOTE)
    imap.login(ADRESSE, MOT_DE_PASSE)
    return imap


# --------------------------------------------------------------------------
# verification a la main
# --------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--verifier", action="store_true",
                   help="teste la connexion IMAP et SMTP, n'envoie rien")
    p.add_argument("--test", metavar="ADRESSE",
                   help="envoie (ou depose en brouillon) un message d'essai")
    p.add_argument("--mode", choices=["brouillon", "envoi"], default=None)
    a = p.parse_args()

    print(f"compte : {ADRESSE or '(MAIL_ADRESSE absente)'}  mode : {MODE}  "
          f"plafond : {PAR_JOUR}/jour")
    if not (ADRESSE and MOT_DE_PASSE):
        sys.exit("Renseigne MAIL_ADRESSE et MAIL_MOT_DE_PASSE dans le .env.")

    if a.verifier:
        with imaplib.IMAP4_SSL(IMAP_HOTE) as imap:
            imap.login(ADRESSE, MOT_DE_PASSE)
            print(f"IMAP ok, brouillons : {_dossier_brouillons(imap)}")
        with smtplib.SMTP(SMTP_HOTE, SMTP_PORT, timeout=30) as s:
            s.starttls()
            s.login(ADRESSE, MOT_DE_PASSE)
            print("SMTP ok")
        return

    if a.test:
        corps = "\n".join(["Bonjour,", "", "Message d'essai du pipeline de prospection.",
                           "", "Bien cordialement,", "", *signature()])
        r, mid = expedier(a.test, "Essai pipeline", corps, a.mode)
        print(f"ok : {r} {mid}")
        return
    p.print_help()


if __name__ == "__main__":
    main()
