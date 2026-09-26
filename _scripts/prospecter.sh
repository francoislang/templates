#!/bin/bash
# Prospection garages, en une commande.
#
#   ./_scripts/prospecter.sh              5 garages
#   ./_scripts/prospecter.sh 10           10 garages
#   ./_scripts/prospecter.sh 5 normandie  en collectant d'abord la Normandie

set -eu
cd "$(dirname "$0")/.."
PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"

[ $# -ge 2 ] && "$PY" _scripts/collecte_osm.py --region "$2"

"$PY" _scripts/pipeline_pro.py --nombre "${1:-5}" --attendre 600
"$PY" _scripts/pipeline_pro.py --reste
