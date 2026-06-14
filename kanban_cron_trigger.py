#!/usr/bin/env python3
"""Cron trigger: crée une tâche Kanban pour le pipeline de prospection du jour.

Ce script est conçu pour être exécuté en mode no_agent=True dans un job cron Hermes.
Il crée une tâche Kanban que le dispatcher prend en charge.
"""
import sqlite3
import sys
import os
from pathlib import Path

# Ajouter hermes-agent au path
HERMES_AGENT = Path.home() / ".hermes" / "hermes-agent"
sys.path.insert(0, str(HERMES_AGENT))

try:
    from hermes_cli.kanban_db import kanban_db_path, create_task
except ImportError:
    print("ERREUR: Impossible d'importer hermes_cli. Vérifie PYTHONPATH.")
    sys.exit(1)

def main():
    db_path = kanban_db_path()
    if not db_path.exists():
        print(f"ERREUR: Base Kanban introuvable: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Créer la tâche de prospection
    task_id = create_task(
        conn=conn,
        title=f"🐾 Prospection du jour — {__import__('datetime').datetime.now().strftime('%d/%m/%Y')}",
        body="""Pipeline complet de prospection:

1. Scraper chien.com (max 20 pages, 3 nouveaux profils)
2. Générer les sites vitrines (template universel)
3. Uploader les photos Cloudinary
4. Ajouter les prospects dans le CRM GitHub
5. Commit + push sur GitHub Pages
6. Envoyer les notifications Telegram

Script: cd /workspace/templates && python3 cron_pipeline.py

Le worker doit:
- Charger la skill pipeline-prospection
- Exécuter chaque étape dans l'ordre
- Signaler les erreurs via kanban_block si nécessaire""",
        assignee="pipeline",
        created_by="cron-trigger",
        max_runtime_seconds=1800,  # 30 minutes max
        skills=["pipeline-prospection", "scraping-chien-com", "site-generator-universel",
                "photos-eleveurs-cloudinary", "crm-github-prospection",
                "telegram-pitch-eleveurs", "git-deploiement-sites"],
    )

    print(f"✅ Tâche créée: {task_id}")
    print(f"   Board: crm-prospection")

    conn.close()

if __name__ == "__main__":
    main()
