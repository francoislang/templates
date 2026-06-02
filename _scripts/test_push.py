import subprocess, sys; sys.path.insert(0, '_scripts')
import telegram

# Commit et push
subprocess.run(['git','-C','/workspace/templates','add','-A'], check=True)
subprocess.run(['git','-C','/workspace/templates','commit','-m','Sites test'], check=False)
push = subprocess.run(['git','-C','/workspace/templates','push','origin','main'], capture_output=True, timeout=60)
if push.returncode == 0:
    print('✅ Push GitHub reussi')
else:
    print('⚠️ Push:', push.stderr.decode()[:200])

# Telegram
msg = '🐾 PROSPECTION DU JOUR — 3 nouveau(x) eleveur(s)\n'
msg += '━' * 30 + '\n'
for name, race, phone in [
    ('Le Domaine du Bouledogue Francais','Bouledogue Francais','0898023525'),
    ('Les Poms Bully d Amour','Loulou de Pomeranie','0493504898'),
    ('Boulyruby','Bouledogue Francais','0496225446'),
]:
    slug = name.lower().replace("'",'').replace(' ','-').strip('-')
    msg += f'\n🐕 {name}\n📌 {race}\n📞 {phone}\n'
    msg += f'🌐 https://francoislang.github.io/templates/{slug}\n'
    msg += '\n' + '─' * 30
    msg += '\n\n--- PITCH A ENVOYER ---\n'
    msg += 'Bonjour,\n\n'
    msg += 'Je suis developpeur web specialise dans la creation de sites pour les eleveurs canins.\n\n'
    msg += f"J'ai une offre speciale : un site vitrine cle en main pour votre elevage de {race}, heberge, personnalise avec vos photos, visible sur Google.\n\n"
    msg += f"J'ai prepare une demo gratuite pour vous montrer le rendu possible pour votre elevage : https://francoislang.github.io/templates/{slug}\n\n"
    msg += "Est-ce que vous avez 2 minutes pour qu'on en parle ?\n\n"
    msg += 'Francois-Frederic Lang\nlangfrancoisfrederic@gmail.com\n'
    msg += '--- FIN DU PITCH ---'

telegram.send(msg)
print('✅ Telegram envoye')
