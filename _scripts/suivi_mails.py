#!/usr/bin/env python3
"""Suivi quotidien de la prospection par courriel : envois -> CRM, reponses
-> brouillon de reponse + alerte Telegram.

A chaque passage :

  1. ENVOIS. Pour chaque prospect dont le courriel est note « brouillon »
     ou « envoye » dans _data/prospection.db, on verifie dans « Messages
     envoyes » qu'il est vraiment parti (cas du brouillon envoye a la main).
     S'il est parti : mail_statut = envoye, et la fiche CRM passe de
     « Nouveau » a « A relancer » (+ commentaire date). Une relance J+7
     partie fait passer la fiche en « Recontacte » (perdus_check.py la
     passera en « Perdu » au bout de 30 jours sans reponse).

  2. REPONSES. On lit les messages recus depuis SCAN_JOURS jours (defaut 30)
     et on garde ceux qui viennent d'un prospect contacte (meme adresse, ou
     reponse dans le fil : In-Reply-To / References = notre Message-ID).
     Chaque reponse n'est traitee qu'une fois (table « reponses »).
       - reponse automatique (absence...) : signalee, rien d'autre ;
       - rebond (adresse invalide)        : fiche en « Perdu » ;
       - sinon le modele (llm.py, DeepSeek) classe la reponse et redige une
         reponse, deposee en BROUILLON dans le meme fil Gmail. Rien ne part
         seul : tu relis, tu modifies si besoin, tu cliques « Envoyer ».
     CRM : interesse / question / plus tard -> « En discussion » ;
           refus / stop / rebond           -> « Perdu » (+ desinscrits.txt).
     La relance J+7 est annulee pour tout prospect qui a repondu.

  3. TELEGRAM : un message par reponse (resume, categorie, lien Gmail,
     fiche CRM), puis un bilan si quelque chose a bouge.

Usage :
    .venv/bin/python _scripts/suivi_mails.py --apercu    # lit tout, n'ecrit rien
    .venv/bin/python _scripts/suivi_mails.py             # passage normal
    .venv/bin/python _scripts/suivi_mails.py --sans-ia   # alerte sans brouillon
Lance par run_suivi.sh (launchd, tous les jours a 11h30 et 18h).
"""
from __future__ import annotations

import argparse
import email
import imaplib
import json
import os
import re
import sqlite3
import sys
import time
import traceback
import unicodedata
from datetime import datetime, timedelta, timezone
from email import policy
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html import unescape
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import config      # noqa: E402  (charge le .env)
import envoi_mail  # noqa: E402
import llm         # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "prospection.db"
MODELE = os.environ.get("MODELE_REPONSES") or "deepseek/deepseek-v4-pro"
try:
    SCAN_JOURS = int(os.environ.get("SUIVI_SCAN_JOURS") or 30)
except ValueError:
    SCAN_JOURS = 30

# categorie -> statut CRM (None = on ne touche pas au statut)
STATUT_CRM = {
    "interesse": "En discussion",
    "question": "En discussion",
    "plus_tard": "En discussion",
    "refus": "Perdu",
    "stop": "Perdu",
    "rebond": "Perdu",
    "auto": None,
    "autre": None,
}
LIBELLE = {
    "interesse": "✅ intéressé", "question": "❓ question", "plus_tard": "⏳ plus tard",
    "refus": "🚫 refus", "stop": "🛑 ne plus écrire", "rebond": "⚠️ adresse invalide",
    "auto": "🤖 réponse automatique", "autre": "📝 à lire",
}
SANS_BROUILLON = {"auto", "rebond", "stop"}

CONSIGNES = """Tu es l'assistant de François Lang, développeur web freelance près de
Nancy (entreprise individuelle « Kerr », site kerr-studio.com). Il prospecte des
petites entreprises françaises par courriel : il leur a préparé une démo de site
vitrine en ligne et leur a écrit. Un prospect vient de répondre. Tu dois classer
la réponse et rédiger la réponse que François enverra (il la relira avant).

Offre et tarifs (à donner UNIQUEMENT si le prospect demande le prix ou les
conditions) :
- site vitrine finalisé (photos, textes, mise en ligne) : 800 €
- option espace d'administration pour modifier le site soi-même : +200 €
- maintenance et hébergement : 20 €/mois
- remise de 10 % si validation sous deux semaines, uniquement sur les prestations
  ponctuelles (jamais sur l'abonnement mensuel)
- paiement : 33 % à la signature, le solde à la mise en ligne
- seule la démo est gratuite, pas le site lui-même

Règles de rédaction :
- vouvoiement, ton professionnel, simple, chaleureux ; phrases courtes ;
  3 à 8 lignes maximum, pas de liste à puces sauf pour un tarif demandé ;
- commence par « Bonjour, » (ou « Bonjour Madame/Monsieur X, » si le nom est
  connu) et termine par « Bien cordialement, » ; n'écris PAS de signature
  (nom, téléphone, site : elle est ajoutée automatiquement) ;
- réponds précisément à ce qui est demandé, n'invente aucun fait, aucune date,
  aucune disponibilité ; si une information manque, propose un court appel ;
- si le prospect est intéressé : remercie, propose un appel de 10 minutes et
  demande le meilleur créneau (ou confirme celui qu'il a proposé, sans en
  inventer) ; tu peux dire que François le rappelle au numéro qu'il indique ;
- si le prospect veut être recontacté plus tard : accepte et demande quand ;
- si le prospect refuse : une réponse de deux lignes, polie, qui le remercie et
  confirme qu'il ne sera plus sollicité ;
- jamais le mot « STOP », jamais de pression commerciale, pas d'emoji.

Catégories possibles :
- interesse : veut en savoir plus, accepte un appel, dit oui ;
- question : pose une question (prix, délais, fonctionnement...) sans dire oui ;
- plus_tard : pas maintenant mais pas fermé ;
- refus : non merci, déjà un prestataire, pas intéressé ;
- stop : demande explicitement de ne plus lui écrire, ou est mécontent ;
- autre : rien de tout cela (hors sujet, message illisible...).

Réponds UNIQUEMENT par un objet JSON, sans texte autour :
{"categorie": "...", "resume": "une phrase qui résume sa réponse",
 "reponse": "le texte complet de la réponse à envoyer"}
"""


# --------------------------------------------------------------------------
# base
# --------------------------------------------------------------------------

def ouvrir() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cols = {r[1] for r in conn.execute("PRAGMA table_info(prospects)")}
    for col in ("crm_synchro", "reponse_at", "reponse_categorie"):
        if col not in cols:
            conn.execute(f"ALTER TABLE prospects ADD COLUMN {col} TEXT")
    conn.execute("""CREATE TABLE IF NOT EXISTS reponses (
        message_id TEXT PRIMARY KEY,
        cle TEXT, recu_at TEXT, expediteur TEXT, objet TEXT,
        categorie TEXT, resume TEXT, brouillon_mid TEXT, thread_id TEXT,
        traite_at TEXT)""")
    conn.commit()
    return conn


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# CRM (GitHub Project V2) — tolerant : une panne GitHub n'arrete pas le suivi
# --------------------------------------------------------------------------

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def _numero(crm_issue: str | None) -> str:
    m = re.search(r"(\d+)\s*$", str(crm_issue or ""))
    return m.group(1) if m else ""


def crm_maj(p: dict, statut: str | None, commentaire: str, apercu: bool) -> str:
    """Change le statut de la fiche et ajoute un commentaire. Renvoie un
    libelle court pour Telegram, ou '' si rien n'a pu etre fait."""
    n = _numero(p.get("crm_issue"))
    if not n:
        return ""
    if apercu:
        return f"#{n}" + (f" → {statut}" if statut else "")
    import crm
    fait = f"#{n}"
    try:
        if statut:
            reel = crm.changer_statut(n, statut)
            fait += f" → {reel}"
        if commentaire:
            crm.commenter(n, commentaire)
    except Exception as e:  # noqa: BLE001
        print(f"   /!\\ CRM #{n} : {e}")
        fait += " (CRM en erreur)"
    return fait


# --------------------------------------------------------------------------
# IMAP
# --------------------------------------------------------------------------

def _imap_date(d: datetime) -> str:
    mois = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()[d.month - 1]
    return f"{d.day:02d}-{mois}-{d.year}"


_COUPURES = (OSError, imaplib.IMAP4.abort)   # OSError couvre TimeoutError et SSLError


class ImapSolide:
    """Connexion Gmail qui se reconnecte seule quand Google coupe ou ne repond
    plus, puis rejoue la commande (le dossier selectionne est re-selectionne)."""

    def __init__(self, essais: int = 3):
        self.essais = essais
        self.dossier: str | None = None
        self.imap = envoi_mail.connexion_imap()

    def _rouvrir(self) -> None:
        try:
            self.imap.shutdown()
        except Exception:  # noqa: BLE001
            pass
        self.imap = envoi_mail.connexion_imap()
        if self.dossier:
            self.imap.select(self.dossier, readonly=True)

    def _appel(self, nom: str, *args):
        for i in range(self.essais):
            try:
                return getattr(self.imap, nom)(*args)
            except _COUPURES as e:
                if i == self.essais - 1:
                    raise
                print(f"   /!\\ Gmail ne répond plus ({type(e).__name__}), "
                      f"reconnexion {i + 1}/{self.essais - 1}")
                time.sleep(5 * (i + 1))
                try:
                    self._rouvrir()
                except _COUPURES:
                    pass   # l'essai suivant echouera et retentera

    def select(self, dossier: str, readonly: bool = True):
        self.dossier = dossier
        return self._appel("select", dossier, readonly)

    def search(self, *args):
        return self._appel("search", *args)

    def fetch(self, *args):
        return self._appel("fetch", *args)

    def list(self, *args):
        return self._appel("list", *args)

    def logout(self) -> None:
        try:
            self.imap.logout()
        except Exception:  # noqa: BLE001
            pass


def _search(imap, critere: str) -> list[bytes]:
    typ, data = imap.search(None, critere)
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def _entetes(imap, num: bytes) -> tuple[email.message.Message | None, str]:
    typ, data = imap.fetch(num, "(X-GM-THRID BODY.PEEK[HEADER])")
    if typ != "OK" or not data:
        return None, ""
    thrid, brut = "", b""
    for part in data:
        if isinstance(part, tuple):
            m = re.search(rb"X-GM-THRID (\d+)", part[0])
            if m:
                thrid = m.group(1).decode()
            brut = part[1]
    if not brut:
        return None, thrid
    return email.message_from_bytes(brut, policy=policy.default), thrid


def _complet(imap, num: bytes) -> email.message.EmailMessage | None:
    typ, data = imap.fetch(num, "(BODY.PEEK[])")
    if typ != "OK":
        return None
    for part in data:
        if isinstance(part, tuple):
            return email.message_from_bytes(part[1], policy=policy.default)
    return None


def _ids(valeur: str | None) -> set[str]:
    return {m.strip().lower() for m in re.findall(r"<[^<>]+>", str(valeur or ""))}


def texte_de(m: email.message.EmailMessage) -> str:
    corps = m.get_body(preferencelist=("plain", "html"))
    if corps is None:
        return ""
    try:
        t = corps.get_content()
    except Exception:  # noqa: BLE001
        t = (corps.get_payload(decode=True) or b"").decode("utf-8", "replace")
    if corps.get_content_type() == "text/html":
        t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
        t = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", t)
        t = unescape(re.sub(r"<[^>]+>", " ", t))
    return t


def sans_citation(t: str) -> str:
    """Ne garde que ce que le prospect a ecrit (coupe l'historique cite)."""
    lignes = []
    for l in t.splitlines():
        s = l.strip()
        if re.match(r"^(le|on)\s.+(a écrit|a ecrit|wrote)\s*:?\s*$", s, re.I) \
                or re.match(r"^-{2,}\s*(message d'origine|original message)", s, re.I) \
                or re.match(r"^(de|from)\s*:\s.+@", s, re.I):
            break
        if s.startswith(">"):
            continue
        lignes.append(l.rstrip())
    out = "\n".join(lignes).strip()
    return re.sub(r"\n{3,}", "\n\n", out)[:4000]


def est_auto(h: email.message.Message) -> bool:
    if (h.get("Auto-Submitted") or "no").lower() != "no":
        return True
    if h.get("X-Autoreply") or h.get("X-Autorespond"):
        return True
    obj = (h.get("Subject") or "").lower()
    return bool(re.search(r"r[ée]ponse automatique|absence|absent|out of office|"
                          r"automatic reply|auto-?reply|congés|conges", obj))


def est_rebond(h: email.message.Message) -> bool:
    exp = (h.get("From") or "").lower()
    return "mailer-daemon" in exp or "postmaster" in exp


# --------------------------------------------------------------------------
# 1. envois -> CRM
# --------------------------------------------------------------------------

def synchro_envois(conn, imap, envoyes: str, apercu: bool) -> list[str]:
    faits = []
    imap.select(envoyes, readonly=True)
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM prospects WHERE mail_statut IN ('brouillon','envoye') "
        "AND mail_envoye_at IS NOT NULL "
        "AND COALESCE(crm_synchro,'') NOT IN ('recontacte','repondu')")]
    for p in rows:
        dest = (p.get("email") or "").strip()
        if not dest:
            continue
        etat = p.get("crm_synchro") or ""
        if etat == "contacte" and not p.get("mail_relance_at"):
            continue  # deja au CRM, aucune relance partie : rien a constater
        depuis = datetime.fromisoformat(p["mail_envoye_at"]) - timedelta(days=1)
        partis = _search(imap, f'(TO "{dest}" SINCE {_imap_date(depuis)})')
        nom = p.get("nom") or dest

        if not etat:
            if p["mail_statut"] != "envoye" and not partis:
                continue  # toujours en brouillon
            date_envoi = p["mail_envoye_at"][:10]
            if partis:
                h, _ = _entetes(imap, partis[0])
                if h is not None and h.get("Date"):
                    try:
                        date_envoi = parsedate_to_datetime(h["Date"]).date().isoformat()
                    except (TypeError, ValueError):
                        pass
                mid = (h.get("Message-ID") or "").strip() if h is not None else ""
            else:
                mid = ""
            crm = crm_maj(p, "A relancer",
                          f"✉️ Courriel de prospection envoyé le {date_envoi} "
                          f"(« {p.get('mail_objet') or ''} »).", apercu)
            print(f"   envoi constaté : {nom} {crm}")
            faits.append(f"{nom} {crm}".strip())
            if not apercu:
                conn.execute("UPDATE prospects SET mail_statut='envoye', "
                             "mail_message_id=COALESCE(NULLIF(?,''), mail_message_id), "
                             "crm_synchro='contacte' WHERE cle=?", (mid, p["cle"]))
                conn.commit()
            etat = "contacte"

        if etat == "contacte" and p.get("mail_relance_at") and len(partis) >= 2:
            crm = crm_maj(p, "Recontacté",
                          f"🔁 Relance par courriel envoyée le {p['mail_relance_at'][:10]}.",
                          apercu)
            print(f"   relance constatée : {nom} {crm}")
            faits.append(f"{nom} (relance) {crm}".strip())
            if not apercu:
                conn.execute("UPDATE prospects SET crm_synchro='recontacte' WHERE cle=?",
                             (p["cle"],))
                conn.commit()
    return faits


# --------------------------------------------------------------------------
# 2. reponses
# --------------------------------------------------------------------------

def contactes(conn) -> tuple[dict[str, dict], dict[str, dict]]:
    par_mail, par_mid = {}, {}
    for r in conn.execute("SELECT * FROM prospects WHERE mail_statut='envoye' "
                          "OR (mail_statut='brouillon' AND mail_envoye_at IS NOT NULL)"):
        p = dict(r)
        if p.get("email"):
            par_mail[p["email"].strip().lower()] = p
        for mid in _ids(p.get("mail_message_id")):
            par_mid[mid] = p
    return par_mail, par_mid


def original_envoye(imap, envoyes: str, p: dict) -> str:
    """Le texte de notre premier courriel, pour donner le contexte au modele."""
    mid = (p.get("mail_message_id") or "").strip()
    if not mid:
        return ""
    try:
        imap.select(envoyes, readonly=True)
        nums = _search(imap, f'(HEADER Message-ID "{mid}")')
        if not nums:
            return ""
        m = _complet(imap, nums[0])
        return texte_de(m)[:2500] if m is not None else ""
    except Exception:  # noqa: BLE001
        return ""


def analyser(p: dict, objet: str, texte: str, original: str) -> dict:
    contexte = {
        "entreprise": p.get("nom"), "metier": p.get("metier"),
        "commune": p.get("commune"), "demo": p.get("site_genere"),
        "objet": objet,
    }
    prompt = (CONSIGNES + "\n\nContexte du prospect :\n"
              + json.dumps(contexte, ensure_ascii=False)
              + "\n\nCourriel envoyé par François :\n«««\n" + (original or "(indisponible)")
              + "\n»»»\n\nRéponse du prospect :\n«««\n" + texte + "\n»»»\n")
    sortie, err = llm.generer(prompt, MODELE, max_tokens=4000, flux=False,
                              timeout=(30, 180))
    if not sortie:
        raise RuntimeError(f"modèle indisponible : {err}")
    m = re.search(r"\{.*\}", sortie, re.S)
    if not m:
        raise RuntimeError("réponse du modèle sans JSON")
    d = json.loads(m.group(0))
    cat = str(d.get("categorie") or "autre").strip().lower()
    if cat not in STATUT_CRM:
        cat = "autre"
    return {"categorie": cat, "resume": str(d.get("resume") or "").strip(),
            "reponse": str(d.get("reponse") or "").strip()}


def deposer_reponse(h: email.message.Message, dest: str, texte: str) -> str:
    objet = h.get("Subject") or ""
    if not re.match(r"^\s*(re|réf|ref)\s*:", objet, re.I):
        objet = f"Re: {objet}"
    leur_mid = (h.get("Message-ID") or "").strip()
    refs = " ".join(x for x in [(h.get("References") or "").strip(), leur_mid] if x)
    corps = texte.rstrip() + "\n\n" + "\n".join(envoi_mail.signature())
    m = envoi_mail.construire(dest, objet, corps,
                              {"In-Reply-To": leur_mid, "References": refs})
    del m["List-Unsubscribe"]   # c'est une conversation, plus de la prospection
    envoi_mail.deposer_brouillon(m)
    return m["Message-ID"]


def ajouter_desinscrit(adresse: str) -> None:
    adresse = adresse.strip().lower()
    if not adresse or adresse in envoi_mail.desinscrits():
        return
    with open(envoi_mail.DESINSCRITS, "a", encoding="utf-8") as f:
        f.write(f"{adresse}\n")


def lien_gmail(thrid: str) -> str:
    if not thrid:
        return "https://mail.google.com/mail/u/0/#drafts"
    return f"https://mail.google.com/mail/u/0/#all/{int(thrid):x}"


def telegram(texte: str) -> None:
    """Texte brut (pas de Markdown : un « _ » dans un nom casserait l'envoi)."""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": texte[:4000],
                  "disable_web_page_preview": True}, timeout=15)
        if r.status_code != 200:
            print(f"   /!\\ Telegram HTTP {r.status_code}")
    except requests.RequestException as e:
        print(f"   /!\\ Telegram : {e}")


def traiter_reponses(conn, imap, tous: str, envoyes: str, apercu: bool,
                     sans_ia: bool) -> list[dict]:
    par_mail, par_mid = contactes(conn)
    if not par_mail and not par_mid:
        print("   aucun prospect contacté par courriel")
        return []
    deja = {r[0] for r in conn.execute("SELECT message_id FROM reponses")}
    moi = envoi_mail.ADRESSE.lower()

    imap.select(tous, readonly=True)
    depuis = datetime.now(timezone.utc) - timedelta(days=SCAN_JOURS)
    nums = _search(imap, f"(SINCE {_imap_date(depuis)} NOT FROM \"{moi}\")")
    print(f"   {len(nums)} message(s) reçu(s) depuis {SCAN_JOURS} j")

    trouves = []
    for num in nums:
        h, thrid = _entetes(imap, num)
        if h is None:
            continue
        mid = (h.get("Message-ID") or "").strip()
        cle_msg = mid.lower() or f"thr-{thrid}-{num.decode()}"
        if cle_msg in deja:
            continue
        exp = parseaddr(h.get("From") or "")[1].lower()
        lies = _ids(h.get("In-Reply-To")) | _ids(h.get("References"))
        p = next((par_mid[i] for i in lies if i in par_mid), None) or par_mail.get(exp)
        if p is None and est_rebond(h):
            # le rebond cite l'adresse en echec dans ses en-tetes ou son corps
            m = _complet(imap, num)
            corps = texte_de(m).lower() if m is not None else ""
            p = next((v for k, v in par_mail.items() if k in corps), None)
        if p is None:
            continue
        trouves.append((num, h, thrid, cle_msg, exp, p))

    resultats = []
    for num, h, thrid, cle_msg, exp, p in trouves:
        nom = p.get("nom") or exp
        objet = h.get("Subject") or ""
        try:
            recu = parsedate_to_datetime(h["Date"]).astimezone(timezone.utc) \
                .isoformat(timespec="seconds")
        except (TypeError, ValueError, KeyError):
            recu = maintenant()
        print(f"   ↩ réponse de {nom} <{exp}> : « {objet[:60]} »")

        r = {"nom": nom, "p": p, "exp": exp, "objet": objet, "thrid": thrid,
             "resume": "", "brouillon": False, "crm": "", "erreur": ""}
        texte = ""
        if est_rebond(h):
            r["categorie"] = "rebond"
            r["resume"] = "Le courriel n'a pas pu être distribué (adresse invalide)."
        elif est_auto(h):
            r["categorie"] = "auto"
            r["resume"] = "Réponse automatique (absence ou accusé de réception)."
        else:
            m = _complet(imap, num)
            texte = sans_citation(texte_de(m)) if m is not None else ""
            if sans_ia:
                r["categorie"], r["resume"] = "autre", texte[:300]
            else:
                try:
                    a = analyser(p, objet, texte,
                                 original_envoye(imap, envoyes, p))
                    r.update(categorie=a["categorie"], resume=a["resume"])
                    r["proposition"] = a["reponse"]
                except Exception as e:  # noqa: BLE001
                    print(f"   /!\\ analyse {nom} : {e}")
                    r["categorie"], r["resume"] = "autre", texte[:300]
                    r["erreur"] = str(e)[:150]
            imap.select(tous, readonly=True)

        cat = r["categorie"]
        brouillon_mid = ""
        if r.get("proposition") and cat not in SANS_BROUILLON and not apercu:
            try:
                brouillon_mid = deposer_reponse(h, exp, r["proposition"])
                r["brouillon"] = True
            except Exception as e:  # noqa: BLE001
                print(f"   /!\\ brouillon {nom} : {e}")
                r["erreur"] = f"brouillon non déposé : {e}"[:150]
        elif r.get("proposition") and cat not in SANS_BROUILLON:
            r["brouillon"] = True  # en apercu : on montre ce qui serait fait
            print("     --- brouillon proposé ---\n     "
                  + r["proposition"].replace("\n", "\n     "))

        extrait = (texte[:600] + "…") if len(texte) > 600 else texte
        commentaire = (f"↩️ Réponse reçue le {recu[:10]} de {exp} — {LIBELLE[cat]}\n\n"
                       f"{r['resume']}"
                       + (f"\n\n> " + extrait.replace("\n", "\n> ") if extrait else "")
                       + ("\n\nBrouillon de réponse déposé dans Gmail." if r["brouillon"] else ""))
        r["crm"] = crm_maj(p, STATUT_CRM[cat], commentaire, apercu)

        if not apercu:
            if cat in ("refus", "stop", "rebond"):
                ajouter_desinscrit(p.get("email") or exp)
            if cat != "auto":
                conn.execute(
                    "UPDATE prospects SET crm_synchro='repondu', reponse_at=?, "
                    "reponse_categorie=?, mail_statut=CASE WHEN ?='rebond' "
                    "THEN 'rejete' ELSE mail_statut END, "
                    "mail_relance_statut=CASE WHEN mail_relance_at IS NULL "
                    "THEN 'a_repondu' ELSE mail_relance_statut END WHERE cle=?",
                    (recu, cat, cat, p["cle"]))
            conn.execute("INSERT OR REPLACE INTO reponses VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (cle_msg, p["cle"], recu, exp, objet, cat, r["resume"],
                          brouillon_mid, thrid, maintenant()))
            conn.commit()
            alerter(r)
        resultats.append(r)
    return resultats


def alerter(r: dict) -> None:
    p, cat = r["p"], r["categorie"]
    lignes = [f"📩 Réponse de {r['nom']}"
              + (f" ({p.get('metier')}" + (f", {p['commune']}" if p.get("commune") else "") + ")"
                 if p.get("metier") else ""),
              LIBELLE[cat],
              "",
              r["resume"] or "(pas de résumé)"]
    if r["brouillon"]:
        lignes += ["", "✏️ Réponse prête en brouillon dans Gmail : relis-la, "
                       "modifie si besoin et clique « Envoyer »."]
    elif cat not in ("auto", "rebond"):
        lignes += ["", "Pas de brouillon : réponds toi-même."]
    if r["erreur"]:
        lignes.append(f"⚠️ {r['erreur']}")
    lignes += ["", lien_gmail(r["thrid"])]
    if r["crm"]:
        lignes.append(f"CRM {r['crm']}")
    if p.get("site_genere"):
        lignes.append(f"Démo : {p['site_genere']}")
    telegram("\n".join(lignes))


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apercu", action="store_true",
                    help="lit la boite et le CRM, n'ecrit rien nulle part")
    ap.add_argument("--sans-ia", action="store_true",
                    help="pas de modele : alerte Telegram sans brouillon")
    a = ap.parse_args()
    print(f"Suivi des courriels — {maintenant()}"
          + (" — APERCU, rien ne sera écrit" if a.apercu else ""))

    if not (envoi_mail.ADRESSE and envoi_mail.MOT_DE_PASSE):
        print("MAIL_ADRESSE / MAIL_MOT_DE_PASSE absents : rien à faire.")
        return 0
    conn = ouvrir()
    envois: list[str] = []
    reps: list[dict] = []
    pannes: list[str] = []

    # Une connexion neuve par etape : une panne de l'etape 1 n'empeche plus
    # le traitement des reponses (etape 2).
    for etape, libelle in ((1, "Envois"), (2, "Réponses")):
        print(f"{etape}. {libelle}")
        imap = None
        try:
            imap = ImapSolide()
            tous = envoi_mail.dossier_special(imap, "\\All", '"[Gmail]/All Mail"')
            envoyes = envoi_mail.dossier_special(imap, "\\Sent", '"[Gmail]/Sent Mail"')
            if etape == 1:
                envois = synchro_envois(conn, imap, envoyes, a.apercu)
            else:
                reps = traiter_reponses(conn, imap, tous, envoyes, a.apercu, a.sans_ia)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            pannes.append(libelle.lower())
            print(f"   /!\\ étape {etape} interrompue, reprise au prochain passage")
        finally:
            if imap is not None:
                imap.logout()

    print(f"Bilan : {len(envois)} envoi(s) passé(s) au CRM, {len(reps)} réponse(s)"
          + (f" — en échec : {', '.join(pannes)}" if pannes else ""))
    if pannes and not a.apercu:
        telegram(f"⚠️ Suivi des courriels : étape {', '.join(pannes)} en échec "
                 "(Gmail injoignable). Nouvel essai au prochain passage.")
    if a.apercu or not envois:
        return 1 if pannes else 0
    telegram(f"📤 {len(envois)} courriel(s) de prospection envoyé(s), fiches CRM "
             "mises à jour :\n- " + "\n- ".join(envois[:15])
             + ("\n…" if len(envois) > 15 else ""))
    return 1 if pannes else 0


if __name__ == "__main__":
    sys.exit(main())
