#!/usr/bin/env python3
"""Deplace les fiches prospects du depot public vers le depot prive.

Le depot `templates` est public (GitHub Pages) et ses Issues etaient donc
lisibles sans authentification — or leurs titres portent le nom ET le
telephone de chaque eleveur. Ce script recopie chaque Issue dans
`crm-prospection` (prive), la rattache au meme board Projects, puis
supprime l'originale.

Reprenable : l'etat est garde dans _data/migration_crm.json, donc on peut
relancer autant de fois que necessaire apres une coupure ou une limite de
debit atteinte.

Usage :
    python3 _scripts/migrer_crm_prive.py --copier          # etape 1
    python3 _scripts/migrer_crm_prive.py --verifier        # etape 2
    python3 _scripts/migrer_crm_prive.py --supprimer       # etape 3 (definitif)
"""
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import requests
import crm

SOURCE = "francoislang/templates"
CIBLE = crm.CRM_REPO
ETAT = Path(__file__).parent.parent / "_data" / "migration_crm.json"


def charger():
    if ETAT.exists():
        return json.loads(ETAT.read_text(encoding="utf-8"))
    return {"copiees": {}, "supprimees": []}


def sauver(e):
    ETAT.parent.mkdir(parents=True, exist_ok=True)
    ETAT.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


def issues_source():
    """Toutes les Issues du depot public, les plus anciennes d'abord."""
    out, page = [], 1
    while True:
        r = requests.get(f"https://api.github.com/repos/{SOURCE}/issues",
                         params={"state": "all", "per_page": 100, "page": page,
                                 "direction": "asc"},
                         headers=crm._headers(), timeout=30)
        d = r.json()
        if not isinstance(d, list) or not d:
            break
        out += [i for i in d if "pull_request" not in i]
        page += 1
    return out


def copier(limite):
    etat = charger()
    src = issues_source()
    restantes = [i for i in src if str(i["number"]) not in etat["copiees"]]
    print(f"{len(src)} Issues a la source, {len(etat['copiees'])} deja copiees, "
          f"{len(restantes)} restantes")

    faites = 0
    for iss in restantes:
        if faites >= limite:
            print(f"\nLimite de {limite} atteinte — relancer pour continuer.")
            break
        corps = iss.get("body") or ""
        corps += (f"\n\n---\n*Migre depuis {SOURCE}#{iss['number']} "
                  f"(cree le {iss['created_at'][:10]}).*")
        payload = {
            "title": iss["title"],
            "body": corps,
            "labels": [l["name"] for l in iss.get("labels", [])],
        }
        r = requests.post(f"https://api.github.com/repos/{CIBLE}/issues",
                          json=payload, headers=crm._headers(), timeout=30)
        if r.status_code == 201:
            neuve = r.json()
            etat["copiees"][str(iss["number"])] = {
                "nouveau": neuve["number"], "node": neuve["node_id"],
                "titre": iss["title"], "etat": iss["state"],
            }
            faites += 1
            print(f"  #{iss['number']} -> #{neuve['number']}")
            sauver(etat)
            time.sleep(2.5)          # limite secondaire de GitHub
        elif r.status_code in (403, 429):
            attente = int(r.headers.get("Retry-After", 60))
            print(f"  limite de debit atteinte, pause de {attente}s")
            time.sleep(attente)
        else:
            print(f"  ECHEC #{iss['number']} : HTTP {r.status_code} "
                  f"{str(r.json())[:120]}")
            break
    sauver(etat)
    print(f"\nTotal copie : {len(etat['copiees'])}")


def verifier():
    etat = charger()
    src = issues_source()
    manquantes = [i["number"] for i in src if str(i["number"]) not in etat["copiees"]]
    print(f"source     : {len(src)} Issues")
    print(f"copiees    : {len(etat['copiees'])}")
    print(f"manquantes : {len(manquantes)} {manquantes[:20]}")
    return not manquantes


def rattacher(limite):
    """Rattache les Issues copiees au board, en reprenant leur statut.

    Indispensable AVANT toute suppression : les items du board pointent sur
    les Issues du depot public. Les supprimer les retirerait du board et
    ferait perdre tous les statuts (A relancer, Perdu, etc.).
    """
    etat = charger()
    etat.setdefault("rattachees", {})

    # statut actuel, par titre d'Issue
    statuts = {}
    for it in crm._get_project_items():
        c = it.get("content") or {}
        titre = c.get("title")
        if not titre:
            continue
        for fv in (it.get("fieldValues") or {}).get("nodes", []):
            if (fv.get("field") or {}).get("name") == "Status":
                statuts[titre] = fv.get("name") or ""
    print(f"{len(statuts)} statut(s) releve(s) sur le board")

    crm._load_status_options()
    champ = "PVTSSF_lAHOBcibjc4BZSavzhUSIRo"
    a_faire = [(k, v) for k, v in etat["copiees"].items()
               if k not in etat["rattachees"]]
    print(f"{len(a_faire)} fiche(s) a rattacher")

    faites = 0
    for ancien, info in a_faire:
        if faites >= limite:
            print(f"\nLimite de {limite} atteinte — relancer pour continuer.")
            break
        try:
            d = crm._graphql({"query":
                'mutation { addProjectV2ItemById(input:{projectId:"%s", contentId:"%s"})'
                ' { item { id } } }' % (crm.PROJECT_ID, info["node"])})
            item = d["data"]["addProjectV2ItemById"]["item"]["id"]

            voulu = statuts.get(info["titre"], "")
            opt = crm.STATUS_OPTIONS.get(voulu) or crm.STATUS_OPTIONS.get("Nouveau")
            if opt:
                crm._graphql({"query":
                    'mutation { updateProjectV2ItemFieldValue(input:{projectId:"%s",'
                    ' itemId:"%s", fieldId:"%s", value:{singleSelectOptionId:"%s"}})'
                    ' { projectV2Item { id } } }' % (crm.PROJECT_ID, item, champ, opt)})

            etat["rattachees"][ancien] = {"item": item, "statut": voulu or "Nouveau"}
            faites += 1
            print(f"  #{ancien} -> #{info['nouveau']}  [{voulu or 'Nouveau'}]")
            sauver(etat)
            time.sleep(1.2)
        except Exception as e:
            print(f"  ECHEC #{ancien} : {e}")
            break
    sauver(etat)
    print(f"\nTotal rattache : {len(etat['rattachees'])}")


def supprimer(limite):
    """Supprime les Issues du depot public. Definitif."""
    etat = charger()
    if not verifier():
        print("\nREFUS : toutes les Issues ne sont pas encore copiees.")
        return
    rat = etat.get("rattachees", {})
    if len(rat) < len(etat["copiees"]):
        print(f"\nREFUS : {len(etat['copiees']) - len(rat)} fiche(s) pas encore "
              f"rattachee(s) au board. Lancer --rattacher d'abord, sinon les "
              f"statuts seront perdus.")
        return
    a_faire = [n for n in etat["copiees"] if n not in etat["supprimees"]]
    print(f"{len(a_faire)} Issue(s) a supprimer du depot public")
    faites = 0
    for numero in a_faire:
        if faites >= limite:
            print(f"\nLimite de {limite} atteinte — relancer pour continuer.")
            break
        d = crm._graphql({"query": """
          { repository(owner:"francoislang", name:"templates") {
              issue(number: %s) { id } } }""" % numero}, strict=False)
        node = (((d.get("data") or {}).get("repository") or {}).get("issue") or {}).get("id")
        if not node:
            etat["supprimees"].append(numero)   # deja disparue
            continue
        try:
            crm._graphql({"query": 'mutation { deleteIssue(input:{issueId:"%s"}) '
                                   '{ clientMutationId } }' % node})
            etat["supprimees"].append(numero)
            faites += 1
            print(f"  #{numero} supprimee")
            sauver(etat)
            time.sleep(1.5)
        except Exception as e:
            print(f"  ECHEC #{numero} : {e}")
            break
    sauver(etat)
    print(f"\nTotal supprime : {len(etat['supprimees'])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--copier", action="store_true")
    ap.add_argument("--verifier", action="store_true")
    ap.add_argument("--rattacher", action="store_true")
    ap.add_argument("--supprimer", action="store_true")
    ap.add_argument("--limite", type=int, default=40,
                    help="nombre d'Issues traitees par execution")
    a = ap.parse_args()
    if a.copier: copier(a.limite)
    elif a.verifier: verifier()
    elif a.rattacher: rattacher(a.limite)
    elif a.supprimer: supprimer(a.limite)
    else: ap.print_help()
