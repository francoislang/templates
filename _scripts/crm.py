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
    "Nouveau": "0653063d",
    "A contacter": "291531de",
    "En discussion": "a105cdf6",
    "Devis envoye": "a2d9cc78",
    "Devis signe": "66334337",
    "Facture envoyee": "9ceca521",
    "Facture payee": "eb490bde",
    "Site livre": "effcf55f",
    "Perdu": "2e252a0e",
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


def get_existing_phones() -> set[str]:
    """Recupere les telephones des Issues deja existantes (evite les doublons)."""
    phones = set()
    url = "https://api.github.com/repos/francoislang/templates/issues"
    params = {"state": "all", "per_page": 100, "page": 1}

    while True:
        r = requests.get(url, headers=_headers(), params=params, timeout=15)
        if r.status_code != 200:
            break
        for issue in r.json():
            # Chercher le telephone dans le corps de l issue
            body = issue.get("body", "") + issue.get("title", "")
            phones_found = re.findall(r'0[1-9](?:[\s.\-]?\d{2}){4}', body)
            for p in phones_found:
                phones.add(_extract_number(p))
            # Chercher aussi dans les labels
            for label in issue.get("labels", []):
                if label.get("name", "").startswith("tel-"):
                    phones.add(label["name"].replace("tel-", ""))

        if len(r.json()) < 100:
            break
        params["page"] += 1

    return phones


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

    # Creer l Issue
    issue_data = {
        "title": f"[{race}] {elevage} — {phone}",
        "body": body,
        "labels": labels,
    }

    r = requests.post(
        "https://api.github.com/repos/francoislang/templates/issues",
        headers=_headers(), json=issue_data, timeout=15
    )

    if r.status_code not in (201, 200):
        print(f"  ⚠️ GitHub Issues: {r.status_code} {r.text[:200]}")

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
