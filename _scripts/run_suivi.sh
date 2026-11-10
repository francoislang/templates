#!/bin/bash
# Suivi des courriels de prospection (appele par launchd, 11h30 et 18h00) :
# envois -> CRM, reponses -> brouillon Gmail + alerte Telegram.
# Meme logique que run_relances.sh : environnement explicite pour launchd.

set -u
REPO="$HOME/Local/Perso/templates"
PY="$REPO/.venv/bin/python"
LOG_DIR="$REPO/_data/logs"
LOG="$LOG_DIR/suivi_mails.log"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LANG="fr_FR.UTF-8"
export PYTHONIOENCODING="utf-8"

mkdir -p "$LOG_DIR"
exec >> "$LOG" 2>&1

echo ""
echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="

if [ ! -x "$PY" ]; then
    echo "ERREUR: environnement virtuel introuvable ($PY)"
    exit 1
fi
cd "$REPO" || { echo "ERREUR: depot introuvable ($REPO)"; exit 1; }

"$PY" _scripts/suivi_mails.py
code=$?
echo "----- fin (code $code) -----"
exit $code
