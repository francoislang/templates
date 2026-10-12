#!/usr/bin/env python3
"""Passe en « Perdu » les fiches restees plus d'un mois en « Recontacte ».

Cron quotidien (lance par run_relances.sh, en semaine a 14h, apres
relance_check.py).

La date de depart est celle ou la fiche est entree dans « Recontacte »,
lue dans l'historique de l'Issue (evenement « statut change » du board).
A defaut — fiche deplacee avant que GitHub ne garde cet historique — on
prend le champ « Relance J+7 », puis la derniere modification de l'Issue.

Usage :
    python3 _scripts/perdus_check.py --apercu   # liste, ne deplace rien
    python3 _scripts/perdus_check.py            # deplace et previent sur Telegram
    python3 _scripts/perdus_check.py --jours 45 # autre delai (defaut : 30)
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import date, datetime, timezone

import crm
import telegram

DELAI_JOURS = 30


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def _est_recontacte(statut: str) -> bool:
    return _norm(statut).startswith("recontact")


def _champ_statut() -> tuple[str, dict[str, str]]:
    """(id du champ Status, {nom d'option: id})."""
    d = crm._graphql({"query": f"""{{
      node(id: "{crm.PROJECT_ID}") {{ ... on ProjectV2 {{
        fields(first: 30) {{ nodes {{
          ... on ProjectV2SingleSelectField {{ id name options {{ id name }} }}
        }} }} }} }} }}"""})
    for f in d["data"]["node"]["fields"]["nodes"]:
        if f and f.get("name") == "Status":
            return f["id"], {o["name"]: o["id"] for o in f["options"]}
    raise SystemExit("champ « Status » introuvable sur le board")


_HISTORIQUE = """
          timelineItems(last: 30, itemTypes: [PROJECT_V2_ITEM_STATUS_CHANGED_EVENT]) {
            nodes { ... on ProjectV2ItemStatusChangedEvent { createdAt status } }
          }"""


def _items(avec_historique: bool) -> list[dict]:
    items, curseur = [], None
    while True:
        apres = f', after: "{curseur}"' if curseur else ""
        q = {"query": f"""{{
          node(id: "{crm.PROJECT_ID}") {{ ... on ProjectV2 {{
            items(first: {20 if avec_historique else 50}{apres}) {{
              pageInfo {{ hasNextPage endCursor }}
              nodes {{
                id
                fieldValues(first: 20) {{ nodes {{
                  __typename
                  ... on ProjectV2ItemFieldSingleSelectValue {{
                    name field {{ ... on ProjectV2SingleSelectField {{ name }} }} }}
                  ... on ProjectV2ItemFieldDateValue {{
                    date field {{ ... on ProjectV2Field {{ name }} }} }}
                }} }}
                content {{ ... on Issue {{
                  number title url updatedAt {_HISTORIQUE if avec_historique else ""}
                }} }}
              }}
            }} }} }} }}"""}
        d = crm._graphql(q)
        bloc = d["data"]["node"]["items"]
        items.extend(bloc["nodes"])
        if not bloc["pageInfo"]["hasNextPage"]:
            return items
        curseur = bloc["pageInfo"]["endCursor"]


def _date(s: str | None) -> date | None:
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _entree_recontacte(item: dict) -> tuple[date | None, str]:
    """Date d'entree dans « Recontacte » et d'ou elle vient."""
    contenu = item.get("content") or {}
    evts = ((contenu.get("timelineItems") or {}).get("nodes") or [])
    dates = [_date(e.get("createdAt")) for e in evts
             if e and _est_recontacte(e.get("status") or "")]
    dates = [d for d in dates if d]
    if dates:
        return max(dates), "historique"
    for fv in (item.get("fieldValues") or {}).get("nodes", []):
        if (fv.get("field") or {}).get("name") == "Relance J+7" and fv.get("date"):
            return _date(fv["date"]), "Relance J+7"
    return _date(contenu.get("updatedAt")), "derniere modif"


def _deplacer(item_id: str, champ_id: str, option_id: str) -> None:
    crm._graphql({"query": f"""mutation {{
      updateProjectV2ItemFieldValue(input: {{
        projectId: "{crm.PROJECT_ID}", itemId: "{item_id}", fieldId: "{champ_id}",
        value: {{ singleSelectOptionId: "{option_id}" }} }}) {{ projectV2Item {{ id }} }} }}"""})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apercu", action="store_true", help="liste sans rien deplacer")
    ap.add_argument("--jours", type=int, default=DELAI_JOURS)
    args = ap.parse_args()
    aujourdhui = datetime.now(timezone.utc).date()
    print(f"Perdus check — {aujourdhui} (delai {args.jours} j)"
          f"{' — APERCU, rien ne sera deplace' if args.apercu else ''}")

    champ_id, options = _champ_statut()
    print("Statuts du board :", ", ".join(options))
    recontacte = [n for n in options if _est_recontacte(n)]
    perdu = [n for n in options if _norm(n) == "perdu"]
    if not recontacte or not perdu:
        print(f"ERREUR : statut « Recontacte » ({recontacte}) ou « Perdu » ({perdu}) absent")
        return 1
    id_perdu = options[perdu[0]]

    try:
        items = _items(avec_historique=True)
    except crm.GraphQLError as e:
        print(f"historique des statuts indisponible ({e}) — repli sur les dates de champ")
        items = _items(avec_historique=False)

    a_perdre, en_cours = [], 0
    for it in items:
        statut = next((fv.get("name") for fv in (it.get("fieldValues") or {}).get("nodes", [])
                       if (fv.get("field") or {}).get("name") == "Status"), None)
        if not _est_recontacte(statut or ""):
            continue
        entree, source = _entree_recontacte(it)
        age = (aujourdhui - entree).days if entree else None
        c = it.get("content") or {}
        ligne = f"  #{c.get('number')} {c.get('title', '?')[:60]} — {age} j ({source})"
        if age is not None and age > args.jours:
            a_perdre.append((it, c, age))
            print(ligne + "  -> PERDU")
        else:
            en_cours += 1
            print(ligne)

    print(f"\n{len(a_perdre)} fiche(s) a passer en « {perdu[0]} », {en_cours} encore en cours")
    if args.apercu or not a_perdre:
        return 0

    faits = []
    for it, c, age in a_perdre:
        try:
            _deplacer(it["id"], champ_id, id_perdu)
            titre = re.sub(r"^\[[^]]*\]\s*", "", c.get("title", ""))[:50]
            faits.append(f"#{c.get('number')} {titre} ({age} j)")
        except crm.GraphQLError as e:
            print(f"  /!\\ #{c.get('number')} non deplacee : {e}")
    if faits:
        telegram.send(f"🗂️ {len(faits)} prospect(s) passe(s) en « {perdu[0]} » "
                      f"(plus de {args.jours} j en « {recontacte[0]} » sans suite) :\n"
                      + "\n".join(faits))
    print(f"{len(faits)} fiche(s) deplacee(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
