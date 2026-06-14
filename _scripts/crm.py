"""
Module CRM — remplace Notion par GitHub Issues + GitHub Projects.

Fonctions:
    get_existing_phones() -> set[str]  : evite les doublons
    add_entry(...) -> str              : cree une Issue + l'ajoute au board
    update_entry(...)                  : met a jour le statut de l'Issue
"""
import os, re, requests, json

import config


def _token() -> str:
    for line in open(config.REPO_ROOT / ".env").read().split('\n'):
        if 'GITHUB_TOKEN_PUSH_HERMES' in line and '=' in line:
            return line.split('=', 1)[1].strip()
    return ""


def _headers():
    return {
        "Authorization": f"token {_token()}",
        "Accept": "application/vnd.github+json",
    }


def _graphql(query: dict) -> dict:
    r = requests.post("https://api.github.com/graphql", json=query, headers=_headers(), timeout=15)
    return r.json()


def _normalize(phone: str) -> str:
    return phone.replace(" ", "").replace("-", "").replace(".", "").replace("+", "00")


def _extract_number(phone: str) -> str:
    """Extrait juste les chiffres du telephone pour comparaison."""
    return re.sub(r'[^0-9]', '', phone)


# ID du projet GitHub
PROJECT_ID = "PVT_kwHOBcibjc4BZSav"

# Mapping statut -> option ID (a completer apres configuration des colonnes)
STATUS_OPTIONS = {
    "Nouveau": "220a6b9a",
    "A contacter": "229bbc62",
    "En discussion": "3639095f",
    "A relancer": "a3615a82",
    "Devis envoye": "e76394b2",
    "Devis signe": "a91bbf4d",
    "Facture envoyee": "4e8e6936",
    "Facture payee": "ed8ee671",
    "Site livre": "7d33bbed",
    "Perdu": "fe76c142",
}


def _load_status_options():
    """Charge les mappings statut -> option ID depuis le board GitHub."""
    q = {'query': f'''
    {{
      node(id: "{PROJECT_ID}") {{
        ... on ProjectV2 {{
          fields(first: 20) {{
            nodes {{
              ... on ProjectV2SingleSelectField {{
                id
                name
                options {{ id name }}
              }}
            }}
          }}
        }}
      }}
    }}
    '''}
    d = _graphql(q)
    nodes = d.get('data', {}).get('node', {}).get('fields', {}).get('nodes', [])
    for node in nodes:
        if node and 'options' in node:
            for opt in node['options']:
                STATUS_OPTIONS[opt['name']] = opt['id']


def _get_project_items() -> list[dict]:
    """
    Recupere tous les items du projet GitHub avec leur statut.
    Pagine jusqu'a avoir tout le projet.
    """
    items = []
    cursor = None

    while True:
        after = f', after: "{cursor}"' if cursor else ""
        q = {"query": f"""
        {{
          node(id: "{PROJECT_ID}") {{
            ... on ProjectV2 {{
              items(first: 100{after}) {{
                pageInfo {{ hasNextPage endCursor }}
                nodes {{
                  fieldValues(first: 10) {{
                    nodes {{
                      ... on ProjectV2ItemFieldSingleSelectValue {{
                        name
                        field {{ ... on ProjectV2SingleSelectField {{ name }} }}
                      }}
                    }}
                  }}
                  content {{
                    ... on Issue {{
                      title
                      labels(first: 10) {{
                        nodes {{ name }}
                      }}
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
        """}
        data = _graphql(q)
        items_data = (
            data.get("data", {})
                .get("node", {})
                .get("items", {})
        )
        items.extend(items_data.get("nodes", []))
        page_info = items_data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    return items


def get_existing_phones() -> set[str]:
    """
    Recupere les telephones des prospects deja traites (statut != Nouveau).
    Les prospects 'Nouveau' sont exclus pour permettre leur re-decouverte
    si jamais ils ont ete ajoutes par erreur ou nettoyes.
    """
    phones = set()

    for item in _get_project_items():
        # Lire le statut du prospect
        status = None
        for fv in item.get("fieldValues", {}).get("nodes", []):
            if fv and fv.get("field", {}).get("name") == "Status":
                status = fv.get("name")

        # Ignorer les Nouveau : ils peuvent etre re-decouverts par le cron
        if not status:
            continue

        content = item.get("content") or {}
        # Telephone depuis le label tel-{digits}
        for label in content.get("labels", {}).get("nodes", []):
            name = label.get("name", "")
            if name.startswith("tel-"):
                phones.add(name.replace("tel-", ""))

        # Telephone depuis le titre "[Race] Nom — tel"
        title = content.get("title", "")
        m = re.search(r"[—\-]\s*(.+)$", title)
        if m:
            tel = re.sub(r"[^0-9]", "", m.group(1))
            if len(tel) >= 7:
                phones.add(tel)

    return phones


def get_existing_names() -> set[str]:
    """
    Recupere les noms d'elevages deja traites (statut != Nouveau).
    Meme logique que get_existing_phones : les Nouveau sont exclus.
    """
    names = set()

    for item in _get_project_items():
        status = None
        for fv in item.get("fieldValues", {}).get("nodes", []):
            if fv and fv.get("field", {}).get("name") == "Status":
                status = fv.get("name")

        if not status:
            continue

        title = (item.get("content") or {}).get("title", "")
        m = re.match(r"\[([^\]]+)\]\s+(.+?)\s*[—\-]\s*(.+)$", title)
        if m:
            names.add(m.group(2).strip().lower())

    return names


def add_entry(elevage: str, races: list[str], phone: str,
              demo_url: str = None, notes: str = None) -> str:
    """
    Cree une Issue GitHub pour le prospect et l ajoute au board.
    Retourne le numero de l Issue.
    """
    race = races[0] if races else "Inconnue"

    # Construire le corps de l issue
    body_parts = [
        f"## Prospect : {elevage}",
        f"- **Race** : {race}",
        f"- **Telephone** : {phone}",
    ]

    # Extraire les infos depuis notes
    email = ""
    siren = ""
    site_actuel = ""
    description = ""
    pitch = ""

    if notes:
        for line in notes.split(" | "):
            line = line.strip()
            if line.startswith("Email:"):
                body_parts.append(f"- **Email** : {line.replace('Email:', '').strip()}")
            elif line.startswith("SIREN:"):
                body_parts.append(f"- **SIREN** : {line.replace('SIREN:', '').strip()}")
            elif line.startswith("Site actuel:"):
                body_parts.append(f"- **Site actuel** : {line.replace('Site actuel:', '').strip()}")
            elif line.startswith("Description:"):
                desc = line.replace('Description:', '').strip()
                body_parts.append(f"- **Description** : {desc[:200]}")
            elif line.startswith("Pitch:"):
                pitch = line.replace('Pitch:', '').strip()
            elif line.startswith("pas de template"):
                body_parts.append(f"- ⚠️ {line}")

    if demo_url:
        body_parts.append(f"- **Demo** : {demo_url}")

    body_parts.append("")
    body_parts.append("---")
    body_parts.append("### Pitch a envoyer")
    body_parts.append("")
    if pitch:
        body_parts.append(pitch)
    else:
        body_parts.append("*(Pitch a generer)*")

    body = "\n".join(body_parts)

    # Labels
    labels = [race.lower().replace(" ", "-")]
    tel_clean = re.sub(r'[^0-9]', '', phone)
    if tel_clean:
        labels.append(f"tel-{tel_clean}")

    # Creer l Issue — tentative avec labels
    issue_data = {
        "title": f"[{race}] {elevage} — {phone}",
        "body": body,
        "labels": labels,
    }

    r = requests.post(
        "https://api.github.com/repos/francoislang/templates/issues",
        headers=_headers(), json=issue_data, timeout=15
    )

    # Si erreur 422 sur les labels, retenter sans labels
    if r.status_code == 422:
        issue_data_no_labels = dict(issue_data)
        issue_data_no_labels.pop("labels", None)
        r = requests.post(
            "https://api.github.com/repos/francoislang/templates/issues",
            headers=_headers(), json=issue_data_no_labels, timeout=15
        )
        if r.status_code in (201, 200):
            # Reussi sans labels — ajouter les labels ensuite
            issue_number = r.json().get("number", "")
            if issue_number:
                for label in labels:
                    requests.post(
                        f"https://api.github.com/repos/francoislang/templates/issues/{issue_number}/labels",
                        headers=_headers(), json={"labels": [label]}, timeout=15
                    )

    if r.status_code not in (201, 200):
        print(f"  ⚠️ GitHub Issues: {r.status_code} — {elevage} non ajouté")
        return ""

    issue = r.json()
    issue_node_id = issue.get("node_id", "")
    issue_number = issue.get("number", "")

    # Ajouter l Issue au project board
    if issue_node_id:
        q = {'query': f'''
        mutation {{
          addProjectV2ItemById(input: {{
            projectId: "{PROJECT_ID}",
            contentId: "{issue_node_id}"
          }}) {{
            item {{
              id
            }}
          }}
        }}
        '''}
        _graphql(q)

    # Mettre a jour le statut si on a les options
    _load_status_options()
    new_option_id = STATUS_OPTIONS.get("Nouveau")
    if issue_node_id and new_option_id:
        # Recuperer l item ID dans le projet
        q2 = {'query': f'''
        {{
          node(id: "{issue_node_id}") {{
            ... on Issue {{
              projectItems(first: 1) {{
                nodes {{
                  id
                }}
              }}
            }}
          }}
        }}
        '''}
        d2 = _graphql(q2)
        items = d2.get('data', {}).get('node', {}).get('projectItems', {}).get('nodes', [])
        if items:
            item_id = items[0]['id']
            q3 = {'query': f'''
            mutation {{
              updateProjectV2ItemFieldValue(input: {{
                projectId: "{PROJECT_ID}",
                itemId: "{item_id}",
                fieldId: "PVTSSF_lAHOBcibjc4BZSavzhUSIRo",
                value: {{
                  singleSelectOptionId: "{new_option_id}"
                }}
              }}) {{
                projectV2Item {{
                  id
                }}
              }}
            }}
            '''}
            _graphql(q3)

    return str(issue_number)


def update_entry(page_id: str, notes: str = None) -> None:
    """Met a jour les notes d une Issue."""
    # page_id est le numero d issue
    if notes:
        r = requests.patch(
            f"https://api.github.com/repos/francoislang/templates/issues/{page_id}",
            headers=_headers(),
            json={"body": notes},
            timeout=15
        )
