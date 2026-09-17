#!/bin/bash
# Verification quotidienne des relances J+7 (appelee par launchd).
#
# Meme logique que run_daily.sh : launchd demarre avec un environnement
# minimal, donc tout est explicite ici.

set -u
REPO="$HOME/Local/Perso/templates"
PY="$REPO/.venv/bin/python"
LOG_DIR="$REPO/_data/logs"
LOG="$LOG_DIR/relances.log"

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

"$PY" _scripts/relance_check.py
code=$?
echo "----- fin (code $code) -----"
exit $code
