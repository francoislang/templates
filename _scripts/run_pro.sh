#!/bin/bash
# Circuit de prospection parallele (marches hors elevage canin).
# Appele par launchd. Independant de run_daily.sh : autre verrou, autre horaire.
#
# Le marche se choisit par la variable METIER_PRO du .env (defaut : garage).

set -u
REPO="$HOME/Local/Perso/templates"
PY="$REPO/.venv/bin/python"
LOG_DIR="$REPO/_data/logs"
LOG="$LOG_DIR/pipeline_pro.log"

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

METIER="$(grep -E '^METIER_PRO=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ' || true)"
METIER="${METIER:-garage}"
NOMBRE="$(grep -E '^SITES_PRO_PAR_JOUR=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ' || true)"
NOMBRE="${NOMBRE:-5}"

echo "marche=$METIER nombre=$NOMBRE"

git pull --rebase --autostash origin main || echo "AVERTISSEMENT: git pull a echoue, on continue"

# --attendre 600 : si le pipeline eleveurs pousse au meme moment, on patiente
# au lieu d'echouer. Les deux verrous sont distincts, seul git est partage.
"$PY" _scripts/pipeline_pro.py --metier "$METIER" --nombre "$NOMBRE" --attendre 600
code=$?

echo "----- fin, code de sortie $code -----"

if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 5242880 ]; then
    tail -c 2000000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

exit $code
