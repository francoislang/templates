"""Rend _scripts importable et neutralise le .env pour les tests."""
import os, sys
from pathlib import Path
SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
os.environ.setdefault("MAIL_ADRESSE", "francois-lang@kerr-studio.com")
