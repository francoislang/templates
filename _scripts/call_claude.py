import requests, json, os, re

with open('.env') as f:
    content = f.read()

key = ""
for line in content.split('\n'):
    if 'ANTHROPIC_API_KEY' in line and '=' in line:
        key = line.split('=', 1)[1].strip()
        break

print(f'Cle trouvee: {len(key)} chars')

prospect = {
    'name': "The Best of Farmdream",
    'race': 'Rhodesian Ridgeback',
    'phone': '06.51.19.52.24',
    'city': 'Alpes-Maritimes',
    'description': "Derriere chaque chiot se cache une histoire... et la mienne est loin d'etre ordinaire ! Mon compagnon de vie a grandi en Rhodesie, et c'est la que notre passion pour cette race a pris racine. A mes debuts, le chemin fut seme d'embuches, mais une motivation constante m'a toujours guidee : approfondir ma connaissance des Rhodesian Ridgebacks.",
    'photo_url': 'https://upload.chien.com/img/23-106786-the-best-of-farmdream.jpg?1754839903',
    'photo_1': 'https://res.cloudinary.com/dhwukxhgc/image/upload/q_auto/f_auto/v1780237577/photo-rhodesian_ridgeback/rhodesian_ridgeback_1.jpg',
    'photo_2': 'https://res.cloudinary.com/dhwukxhgc/image/upload/q_auto/f_auto/v1780237579/photo-rhodesian_ridgeback/rhodesian_ridgeback_2.jpg',
}

prompt = f"""Cree un site vitrine HTML complet pour un eleveur de chiens. Un seul fichier index.html avec CSS inline, responsive, animations au scroll.

Inspire-toi du style riche des sites comme joyaux-d-anubis (plein ecran, hero, about, galerie, contact, schema.org).

Prospect: {json.dumps(prospect, ensure_ascii=False)}

Regles:
- Site UNIQUE, pas un template
- Hero avec photo grand format
- Section histoire avec la description
- Section "La race" avec presentation du Rhodesian Ridgeback
- Galerie photos avec les 2 photos fournies
- Section contact avec telephone et localisation
- Footer
- Google Fonts authorises
- Schema.org JSON-LD
- Design professionnel, tons chauds terracotta/ocher (origine africaine)
- Reponds UNIQUEMENT avec le code HTML complet, sans rien d'autre"""

response = requests.post(
    'https://openrouter.ai/api/v1/chat/completions',
    headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
    json={
        'model': 'anthropic/claude-sonnet-4',
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 32000,
    },
    timeout=120
)

result = response.json()
html = result['choices'][0]['message']['content']

# Enlever les eventuelles balises markdown
html = re.sub(r'^```html?\n?', '', html)
html = re.sub(r'\n?```\s*$', '', html)

os.makedirs('the-best-of-farmdream', exist_ok=True)
with open('the-best-of-farmdream/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

lignes = html.count('\n')
print(f'✅ {lignes} lignes, {len(html)} chars')
print(f'https://francoislang.github.io/templates/the-best-of-farmdream')
