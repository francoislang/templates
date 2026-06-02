import os
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent
load_dotenv(REPO_ROOT / ".env")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
NOTION_SECRET = os.environ["NOTION_SECRET"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
CLOUDINARY_CLOUD_NAME = os.environ["CLOUDINARY_CLOUD_NAME"]
CLOUDINARY_API_KEY = os.environ["CLOUDINARY_API_KEY"]
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "francoislang/template-elevage")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SITES_PER_DAY = int(os.environ.get("SITES_PER_DAY", "3"))
PAGES_TO_SCRAPE = int(os.environ.get("PAGES_TO_SCRAPE", "5"))
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
