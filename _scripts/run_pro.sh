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

# Le pipeline eleveurs part a 9h00 et ce circuit a 9h30 : s'il tourne
# encore, on patiente. Les deux verrous sont distincts, mais le depot git
# est partage et deux push simultanes se marchent dessus. Vingt minutes au
# plus, puis on part quand meme -- mieux vaut un push en conflit qu'une
# journee sans prospection.
VERROU="$REPO/_data/.pipeline.lock"
attente=0
while [ -f "$VERROU" ] && "$PY" -c "
import fcntl, sys
try:
    f = open('$VERROU')
    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    sys.exit(1)          # verrou libre
except BlockingIOError:
    sys.exit(0)          # verrou tenu
except OSError:
    sys.exit(1)
" 2>/dev/null; do
    if [ "$attente" -ge 1200 ]; then
        echo "AVERTISSEMENT: le pipeline eleveurs tourne encore apres 20 min, on demarre quand meme"
        break
    fi
    [ "$attente" -eq 0 ] && echo "le pipeline eleveurs tourne, on patiente..."
    sleep 30
    attente=$((attente + 30))
done
[ "$attente" -gt 0 ] && echo "attente du pipeline eleveurs : ${attente}s"

git pull --rebase --autostash origin main || echo "AVERTISSEMENT: git pull a echoue, on continue"

# --attendre 600 : si le pipeline eleveurs pousse au meme moment, on patiente
# au lieu d'echouer. Les deux verrous sont distincts, seul git est partage.
# Les garages qui ont deja un site font partie du vivier : on leur propose
# une comparaison, pas une refonte imposee. Mettre AVEC_SITE_PRO=0 dans .env
# pour revenir aux seuls sans-site.
AVEC="$(grep -E '^AVEC_SITE_PRO=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ' || true)"
OPT=""
[ "${AVEC:-1}" != "0" ] && OPT="--avec-site"
echo "avec-site=${AVEC:-1}"

"$PY" _scripts/pipeline_pro.py --metier "$METIER" --nombre "$NOMBRE" $OPT --attendre 600
code=$?

echo "----- fin, code de sortie $code -----"

if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 5242880 ]; then
    tail -c 2000000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

exit $code
