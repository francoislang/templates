#!/usr/bin/env python3
"""Backfill des colonnes processed_at / crm_issue_url / site_slug / site_url
dans la table `annonces`, en se basant sur les Issues du CRM GitHub.

Pour chaque Issue du repo francoislang/templates :
  - Extrait téléphone (depuis label `tel-XXXX` ou depuis le titre "[Race] Nom — tel")
  - Match par téléphone normalisé à une row `annonces`
  - UPDATE processed_at, crm_issue_url, site_slug (+ site_url si le dossier existe)

Usage:
    python3 _scripts/backfill_processed.py                 # dry-run par défaut
    python3 _scripts/backfill_processed.py --apply         # écrit en DB
    python3 _scripts/backfill_processed.py --apply -v      # verbose
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "_data" / "annonces.db"
REPO_SLUG = "francoislang/templates"
PAGES_URL = "https://francoislang.github.io/templates/{slug}"


def _github_token() -> str:
    """Récupère le token depuis .env (comme le fait crm.py)."""
    env = REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GITHUB_TOKEN_PUSH_HERMES=") or line.startswith("GITHUB_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("GITHUB_TOKEN_PUSH_HERMES") or os.environ.get("GITHUB_TOKEN") or ""


def normalize_phone(p: str) -> str:
    return re.sub(r"[^\d]", "", (p or ""))


def slugify(text: str) -> str:
    """Même règle que pipeline.py — pas d'unicode normalization."""
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def slugify_strip_accents(text: str) -> str:
    """Variante qui dégueule les accents avant slugify — utile pour matcher les dossiers existants."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def fetch_all_issues(token: str) -> list[dict]:
    """Récupère toutes les Issues (open + closed) via REST API."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    issues = []
    page = 1
    while True:
        r = requests.get(
            f"https://api.github.com/repos/{REPO_SLUG}/issues",
            headers=headers,
            params={"state": "all", "per_page": 100, "page": page},
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        # Skip PRs
        issues.extend(i for i in batch if "pull_request" not in i)
        page += 1
    return issues


def extract_phone_from_issue(issue: dict) -> str:
    """Retourne le phone normalisé (digits) ou ''."""
    # Depuis label tel-XXXX (le plus fiable)
    for lbl in issue.get("labels", []):
        name = lbl.get("name", "")
        if name.startswith("tel-"):
            return name[4:]
    # Fallback : titre "[Race] Nom — tel"
    title = issue.get("title", "")
    m = re.search(r"[—\-]\s*([\d\s.\-+]{8,})$", title)
    if m:
        digits = normalize_phone(m.group(1))
        if len(digits) >= 7:
            return digits
    return ""


def extract_name_from_title(title: str) -> str:
    """Extrait le nom d'élevage depuis '[Race] Nom — tel'."""
    # Retire le [Race] au début
    t = re.sub(r"^\[[^\]]+\]\s*", "", title)
    # Retire le suffixe " — tel" ou " - tel"
    t = re.sub(r"\s*[—\-]\s*[\d\s.\-+]+$", "", t)
    return t.strip()


def find_site_slug(name: str, sites_in_repo: set[str]) -> str:
    """Retourne le slug du dossier existant ou '' si aucun."""
    candidates = [slugify(name), slugify_strip_accents(name)]
    for c in candidates:
        if c in sites_in_repo:
            return c
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Applique les UPDATE (sinon dry-run)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    token = _github_token()
    if not token:
        print("ERREUR: pas de GITHUB_TOKEN_PUSH_HERMES / GITHUB_TOKEN dans .env ou env")
        sys.exit(1)

    print(f"DB   : {DB_PATH}")
    print(f"Mode : {'APPLY' if args.apply else 'DRY-RUN'}")

    # 1. Charger les dossiers de sites existants dans le repo
    excluded = {"_scripts", "_templates", "_data", "node_modules", ".git", ".claude"}
    sites_in_repo = {d.name for d in REPO_ROOT.iterdir()
                     if d.is_dir() and d.name not in excluded
                     and not d.name.startswith(".")
                     and (d / "index.html").exists()}
    print(f"Sites dans le repo : {len(sites_in_repo)}")

    # 2. Charger les Issues du CRM
    print("Fetch Issues GitHub...", end=" ", flush=True)
    issues = fetch_all_issues(token)
    print(f"{len(issues)} Issues")

    # 3. Index DB par phone normalisé
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    db_by_phone = {}
    for r in conn.execute("SELECT source_url, name, phone, processed_at FROM annonces WHERE phone != ''"):
        p = normalize_phone(r["phone"])
        if p:
            db_by_phone.setdefault(p, []).append(dict(r))
    print(f"Rows DB avec phone : {sum(len(v) for v in db_by_phone.values())}  "
          f"| phones distincts : {len(db_by_phone)}")

    # 4. Parcours Issues → match DB → UPDATE
    now = datetime.now(timezone.utc).isoformat()
    counts = {"issues_total": len(issues), "issues_with_phone": 0,
              "matched": 0, "no_match": 0, "already_processed": 0,
              "site_found": 0}
    no_match = []
    updates = []  # (source_url, crm_issue_url, site_slug, site_url)

    for issue in issues:
        phone = extract_phone_from_issue(issue)
        if not phone:
            continue
        counts["issues_with_phone"] += 1

        rows = db_by_phone.get(phone, [])
        if not rows:
            no_match.append({
                "title": issue.get("title", "")[:80],
                "phone": phone,
                "url": issue.get("html_url", ""),
            })
            counts["no_match"] += 1
            continue

        # Match ! Sélectionne la row (ou la première si plusieurs)
        target = rows[0]
        counts["matched"] += 1

        # Site slug (si dossier existe)
        name = extract_name_from_title(issue.get("title", ""))
        slug = find_site_slug(name, sites_in_repo)
        site_url = PAGES_URL.format(slug=slug) if slug else ""
        if slug:
            counts["site_found"] += 1

        if target["processed_at"]:
            counts["already_processed"] += 1

        updates.append((
            target["source_url"],
            issue.get("html_url", ""),
            slug,
            site_url,
        ))

        if args.verbose:
            print(f"  MATCH  {name!r:35} phone={phone:12} "
                  f"→ {target['name']!r:30} slug={slug!r}")

    # 5. Résumé & apply
    print("\n=== Bilan ===")
    for k, v in counts.items():
        print(f"  {k:22s} {v}")

    if no_match:
        print(f"\n=== {len(no_match)} Issues sans match DB (phone absent en `annonces`) ===")
        for x in no_match[:10]:
            print(f"  {x['title']!r:40} phone={x['phone']} {x['url']}")
        if len(no_match) > 10:
            print(f"  ... et {len(no_match) - 10} autres")

    if args.apply and updates:
        print(f"\nÉcriture DB : {len(updates)} UPDATE...", end=" ", flush=True)
        for src, issue_url, slug, site_url in updates:
            conn.execute(
                """UPDATE annonces SET
                     processed_at   = COALESCE(processed_at, ?),
                     crm_issue_url  = ?,
                     site_slug      = NULLIF(?, ''),
                     site_url       = NULLIF(?, '')
                   WHERE source_url = ?""",
                (now, issue_url, slug, site_url, src),
            )
        conn.commit()

        # Recheck état DB
        total_processed = conn.execute(
            "SELECT COUNT(*) FROM annonces WHERE processed_at IS NOT NULL"
        ).fetchone()[0]
        remaining = conn.execute(
            "SELECT COUNT(*) FROM annonces "
            "WHERE processed_at IS NULL AND phone != '' AND phone NOT LIKE '08%'"
        ).fetchone()[0]
        print("OK")
        print(f"  DB : processed_at renseigné pour {total_processed} rows")
        print(f"  Pool restant (non-traités, avec phone, hors 08): {remaining}")
    elif not args.apply:
        print("\n(dry-run — relance avec --apply pour écrire)")

    conn.close()


if __name__ == "__main__":
    main()
