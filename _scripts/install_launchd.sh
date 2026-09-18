#!/bin/bash
# Installe (ou reinstalle) les deux agents launchd du projet.
#
# launchd ne lit que ~/Library/LaunchAgents : un plist qui vit dans le depot
# n'est jamais charge tant qu'il n'a pas ete copie la. C'est la cause du
# message "Could not find service ... in domain for user gui".
#
# Relancer ce script apres toute modification d'un plist : launchd garde
# l'ancienne version en memoire tant qu'on ne l'a pas dechargee.

set -u
REPO="$HOME/Local/Perso/templates"
SRC="$REPO/_scripts/launchd"
DEST="$HOME/Library/LaunchAgents"
UID_GUI="gui/$(id -u)"
AGENTS=(com.francoislang.prospection com.francoislang.relances)

mkdir -p "$DEST"

for label in "${AGENTS[@]}"; do
    plist="$SRC/$label.plist"
    if [ ! -f "$plist" ]; then
        echo "  ignore : $label (plist absent de $SRC)"
        continue
    fi
    if ! plutil -lint "$plist" >/dev/null 2>&1; then
        echo "  ERREUR : $label — plist invalide, non installe"
        continue
    fi

    cp "$plist" "$DEST/$label.plist"
    launchctl bootout "$UID_GUI/$label" 2>/dev/null   # ignore s'il n'etait pas charge
    if launchctl bootstrap "$UID_GUI" "$DEST/$label.plist" 2>/dev/null; then
        echo "  installe : $label"
    else
        echo "  ERREUR : $label — bootstrap refuse"
    fi
done

# S'assurer que les scripts lances restent executables
chmod +x "$REPO"/_scripts/run_daily.sh "$REPO"/_scripts/run_relances.sh 2>/dev/null

echo ""
echo "Agents charges (PID, code de sortie du dernier lancement, label) :"
launchctl list | grep francoislang || echo "  aucun — quelque chose a echoue"
echo ""
echo "Pour declencher un lancement immediat :"
for label in "${AGENTS[@]}"; do
    echo "  launchctl kickstart -k $UID_GUI/$label"
done
