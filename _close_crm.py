import requests, json

token = ''
for line in open('/workspace/templates/.env'):
    if 'GITHUB_TOKEN_PUSH_HERMES' in line and '=' in line:
        token = line.split('=', 1)[1].strip()
        break

h = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github+json'}

query = """
{
  node(id: "PVT_kwHOBcibjc4BZSav") {
    ... on ProjectV2 {
      items(first: 100) {
        nodes {
          id
          content {
            ... on Issue {
              number
              title
              state
            }
          }
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field {
                  ... on ProjectV2FieldCommon {
                    name
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

r = requests.post('https://api.github.com/graphql', json={'query': query}, headers=h, timeout=15)
data = r.json()

if 'errors' in data:
    print('GraphQL error:', json.dumps(data['errors'], indent=2)[:500])
    exit(1)

items = data['data']['node']['items']['nodes']
print(f'Total items: {len(items)}')

nouveau = []
for item in items:
    status = None
    for fv in item.get('fieldValues', {}).get('nodes', []):
        if fv and fv.get('field', {}).get('name') == 'Status':
            status = fv.get('name')
    content = item.get('content', {})
    if status == 'Nouveau' and content and content.get('state') == 'OPEN':
        nouveau.append(content['number'])
        print(f'  [Nouveau] #{content["number"]} - {content["title"][:60]}')

if not nouveau:
    print('Aucun item en statut Nouveau')
else:
    print(f'\nFermeture de {len(nouveau)} issues...')
    for num in nouveau:
        r2 = requests.patch(
            f'https://api.github.com/repos/francoislang/templates/issues/{num}',
            headers=h, json={'state': 'closed'}, timeout=15
        )
    print(f'✅ {len(nouveau)} issues fermées')
