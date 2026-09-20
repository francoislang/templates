#!/bin/bash
# Verification horaire des vues de demos (appelee par launchd).
set -u
REPO="$HOME/Local/Perso/templates"
PY="$REPO/.venv/bin/python"
LOG_DIR="$REPO/_data/logs"
LOG="$LOG_DIR/vues.log"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LANG="fr_FR.UTF-8"
export PYTHONIOENCODING="utf-8"

mkdir -p "$LOG_DIR"
exec >> "$LOG" 2>&1

echo ""
echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
[ -x "$PY" ] || { echo "ERREUR: venv introuvable ($PY)"; exit 1; }
cd "$REPO" || { echo "ERREUR: depot introuvable"; exit 1; }
"$PY" _scripts/vues_check.py
echo "----- fin (code $?) -----"

# journal borne a 2 Mo
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 2097152 ]; then
    tail -c 1000000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
