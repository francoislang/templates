#!/bin/bash
# Lancement quotidien du pipeline de prospection (appele par launchd).
#
# launchd demarre avec un environnement minimal : ni PATH complet, ni
# repertoire courant. Tout est donc explicite ici.

set -u
REPO="$HOME/Local/Perso/templates"
PY="$REPO/.venv/bin/python"
LOG_DIR="$REPO/_data/logs"
LOG="$LOG_DIR/pipeline.log"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LANG="fr_FR.UTF-8"
export PYTHONIOENCODING="utf-8"

mkdir -p "$LOG_DIR"
exec >> "$LOG" 2>&1

echo ""
echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="

if [ ! -x "$PY" ]; then
    echo "ERREUR: environnement virtuel introuvable ($PY)"
    echo "  -> cd $REPO && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

cd "$REPO" || { echo "ERREUR: depot introuvable ($REPO)"; exit 1; }

# Repartir du dernier etat distant, sans casser si le working tree est sale
git pull --rebase --autostash origin main || echo "AVERTISSEMENT: git pull a echoue, on continue"

"$PY" _scripts/pipeline.py
code=$?

echo "----- fin, code de sortie $code -----"

# Garder le journal sous 5 Mo
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 5242880 ]; then
    tail -c 2000000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

exit $code
