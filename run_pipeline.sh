#!/bin/bash
# Pipeline prospection — à ajouter dans le crontab système
# 0 8 * * * /workspace/templates/run_pipeline.sh >> /tmp/pipeline.log 2>&1
cd /workspace/templates && python3 _scripts/pipeline.py
