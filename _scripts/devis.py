#!/usr/bin/env python3
"""
Generateur de devis et factures PDF pour sites vitrines d'eleveurs canins.

Usage:
    python _scripts/devis.py --issue 14            # Genere un devis pour l'Issue #14
    python _scripts/devis.py --issue 14 --facture  # Genere une facture
    python _scripts/devis.py --client "Eleveur X" --race "Berger" --formule complet
    python _scripts/devis.py --list                # Liste les formules disponibles
"""
import sys, os, json, re
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import config
import yaml

REPO_ROOT = config.REPO_ROOT
BUSINESS_FILE = REPO_ROOT / "_data" / "business.yaml"


def _get_business():
    with open(BUSINESS_FILE) as f:
        data = yaml.safe_load(f)
    return data["business"], data["defaults"], data["prestations"]


def _get_issue_data(issue_number: str):
    """Recupere les infos du client depuis une Issue GitHub."""
    import requests
    with open(REPO_ROOT / ".env") as f:
        for line in f.read().split('\n'):
            if 'GITHUB_TOKEN_PUSH_HERMES' in line and '=' in line:
                gh = line.split('=', 1)[1].strip()
                break
    
    r = requests.get(
        f"https://api.github.com/repos/francoislang/templates/issues/{issue_number}",
        headers={"Authorization": f"token {gh}", "Accept": "application/vnd.github+json"},
        timeout=15
    )
    if r.status_code != 200:
        return None, None, None
    
    issue = r.json()
    title = issue.get("title", "")
    body = issue.get("body", "") or ""
    
    # Extraire nom, race, tel du titre "[Race] Nom - Tel"
    m = re.match(r'\[([^\]]+)\]\s+(.+?)\s*[-–]\s*(.+)$', title)
    race = m.group(1) if m else "Inconnue"
    client = m.group(2) if m else title
    tel = m.group(3) if m else ""
    
    # Extraire email et adresse du body si presents
    email = ""
    for line in body.split('\n'):
        if "Email" in line and ":" in line:
            email = line.split(':', 1)[1].strip()
            break
    
    return client, race, tel, email


def _num_to_words(n: float) -> str:
    """Convertit un nombre en toutes lettres (approx)."""
    euros = int(n)
    cents = int(round((n - euros) * 100))
    if cents == 0:
        return f"{euros} euros"
    return f"{euros} euros et {cents} centimes"


def _generate_html(doc_type: str, client: str, race: str, tel: str, email: str,
                   formule: str, prix_ht: float, num: str, business: dict,
                   defaults: dict) -> str:
    """Genere le HTML du devis/facture."""
    b = business
    d = defaults
    tva_pct = b["taux_tva"]
    tva = prix_ht * tva_pct / 100 if tva_pct > 0 else 0
    total_ttc = prix_ht + tva
    today = datetime.now()
    
    if doc_type == "devis":
        titre = "DEVIS"
        validite = f"Valable {d['validite_devis']} jours"
        numero = f"DEV-{today.year}-{num}"
    else:
        titre = "FACTURE"
        validite = f"A payer sous {d['delai_paiement']} jours"
        numero = f"FAC-{today.year}-{num}"
    
    echeance = today + timedelta(days=d['delai_paiement'])
    
    tva_line = ""
    if tva_pct > 0:
        tva_line = f"""
        <tr>
            <td colspan="3" style="text-align:right; padding:8px; border-bottom:1px solid #ddd;">
                <strong>TVA ({tva_pct}%)</strong>
            </td>
            <td style="text-align:right; padding:8px; border-bottom:1px solid #ddd;">
                {tva:.2f} €
            </td>
        </tr>"""
    
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>{titre} {numero}</title>
<style>
    @page {{ margin: 20mm; }}
    body {{ font-family: 'Helvetica', 'Arial', sans-serif; font-size: 12px; color: #222; line-height: 1.5; }}
    .header {{ display: flex; justify-content: space-between; margin-bottom: 40px; }}
    .header-left h1 {{ font-size: 28px; color: #2D5A3D; margin: 0 0 5px 0; }}
    .header-left p {{ margin: 2px 0; color: #555; font-size: 11px; }}
    .header-right {{ text-align: right; }}
    .header-right h2 {{ font-size: 24px; color: #333; margin: 0; }}
    .header-right .numero {{ font-size: 14px; color: #2D5A3D; font-weight: bold; }}
    .infos {{ display: flex; justify-content: space-between; margin-bottom: 30px; }}
    .infos-box {{ width: 45%; }}
    .infos-box h3 {{ font-size: 13px; color: #2D5A3D; margin: 0 0 5px 0; border-bottom: 2px solid #2D5A3D; padding-bottom: 3px; }}
    .infos-box p {{ margin: 3px 0; font-size: 11px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
    th {{ background: #2D5A3D; color: white; padding: 10px 8px; text-align: left; font-size: 11px; }}
    td {{ padding: 8px; border-bottom: 1px solid #eee; font-size: 11px; }}
    .total-row td {{ font-weight: bold; font-size: 14px; color: #2D5A3D; border-top: 2px solid #2D5A3D; }}
    .footer {{ margin-top: 50px; font-size: 10px; color: #999; text-align: center; border-top: 1px solid #ddd; padding-top: 10px; }}
    .conditions {{ font-size: 10px; color: #666; margin-top: 20px; }}
    .signature {{ margin-top: 60px; }}
    .signature-line {{ display: inline-block; border-top: 1px solid #333; width: 250px; padding-top: 5px; font-size: 11px; }}
    .badge-tva {{ display: inline-block; background: #f0f0f0; padding: 2px 8px; border-radius: 3px; font-size: 10px; color: #666; }}
</style>
</head>
<body>

<div class="header">
    <div class="header-left">
        <h1>{b['nom']} {b['prenom']}</h1>
        <p>{b['adresse']}</p>
        <p>{b['code_postal']} {b['ville']}</p>
        <p>{b['email']} | {b['telephone']}</p>
        <p><strong>{b['statut']}</strong> - SIRET {b['siren']}</p>
        <p><span class="badge-tva">{("TVA non applicable, art. 293 B du CGI" if b["regime_tva"] == "non-redevable" else f"TVA intracommunautaire: {b.get('tva_intra', 'N/A')}")}</span></p>
    </div>
    <div class="header-right">
        <h2>{titre}</h2>
        <p class="numero">{numero}</p>
        <p>Date: {today.strftime('%d/%m/%Y')}</p>
        <p>{validite}</p>
    </div>
</div>

<div class="infos">
    <div class="infos-box">
        <h3>CLIENT</h3>
        <p><strong>{client}</strong></p>
        <p>Race: {race}</p>
        <p>Tel: {tel}</p>
        {f'<p>Email: {email}</p>' if email else ''}
    </div>
    <div class="infos-box">
        <h3>PRESTATION</h3>
        <p>{formule}</p>
    </div>
</div>

<table>
    <tr>
        <th style="width:50%">Designation</th>
        <th style="width:10%;text-align:center">Qté</th>
        <th style="width:20%;text-align:right">Prix unitaire HT</th>
        <th style="width:20%;text-align:right">Total HT</th>
    </tr>
    <tr>
        <td>{formule} - {race}</td>
        <td style="text-align:center">1</td>
        <td style="text-align:right">{prix_ht:.2f} €</td>
        <td style="text-align:right">{prix_ht:.2f} €</td>
    </tr>
    {tva_line}
    <tr class="total-row">
        <td colspan="3" style="text-align:right;">Total TTC</td>
        <td style="text-align:right;">{total_ttc:.2f} €</td>
    </tr>
</table>

<p style="text-align:right; font-size:11px; color:#666;">
    Soit {_num_to_words(total_ttc)}
</p>

<div class="conditions">
    <p><strong>Conditions de paiement :</strong> {d['conditions_paiement']}</p>
    <p><strong>Echeance :</strong> {echeance.strftime('%d/%m/%Y')}</p>
    <p><strong>IBAN :</strong> {d['iban']} | <strong>BIC :</strong> {d['bic']}</p>
    <p><strong>Retard de paiement :</strong> Application d'une penalite de 3 fois le taux d'interet legal et d'une indemnite forfaitaire de 40€ pour frais de recouvrement (art. L441-6 C.com.)</p>
</div>

<div class="signature">
    <p>Fait a {b['ville']}, le {today.strftime('%d/%m/%Y')}</p>
    <div class="signature-line">Signature et cachet (precede de la mention "Bon pour accord")</div>
</div>

<div class="footer">
    <p>{b['nom']} {b['prenom']} - SIRET {b['siren']} - {b['statut']}</p>
</div>

</body>
</html>"""
    return html


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generateur de devis/facture")
    parser.add_argument("--issue", "-i", help="Numero d'Issue GitHub")
    parser.add_argument("--client", "-c", help="Nom du client")
    parser.add_argument("--race", "-r", help="Race du chien")
    parser.add_argument("--tel", "-t", help="Telephone")
    parser.add_argument("--email", "-e", help="Email")
    parser.add_argument("--formule", "-f", default="site_vitrine_base",
                        choices=["site_vitrine_base", "site_vitrine_complet", "site_vitrine_premium"],
                        help="Formule choisie")
    parser.add_argument("--facture", action="store_true", help="Generer une facture au lieu d'un devis")
    parser.add_argument("--prix", type=float, help="Prix HT personnalise")
    parser.add_argument("--list", action="store_true", help="Lister les formules")
    parser.add_argument("--output", "-o", help="Fichier de sortie (sinon = docs/DEV-xxx.html)")
    
    args = parser.parse_args()
    
    # Load business info
    try:
        business, defaults, prestations = _get_business()
    except FileNotFoundError:
        print("❌ Fichier _data/business.yaml introuvable. Configure d'abord tes infos.")
        sys.exit(1)
    
    if args.list:
        print("Formules disponibles :")
        for key, p in sorted(prestations.items()):
            print(f"  {key:25s} {p['prix_ht']:>6.0f}€ HT - {p['nom']}")
        return
    
    # Recuperer les donnees du client
    client = args.client or ""
    race = args.race or ""
    tel = args.tel or ""
    email = args.email or ""
    
    if args.issue:
        client, race, tel, email = _get_issue_data(args.issue)
        if not client:
            print(f"❌ Issue #{args.issue} introuvable")
            sys.exit(1)
        print(f"  Client: {client}")
        print(f"  Race: {race}")
        print(f"  Tel: {tel}")
    
    if not client:
        print("❌ Specifie un client (--client ou --issue)")
        sys.exit(1)
    
    # Formule
    formule_key = args.formule
    formule = prestations[formule_key]
    prix_ht = args.prix or formule["prix_ht"]
    
    # Generer
    docs_dir = REPO_ROOT / "docs"
    docs_dir.mkdir(exist_ok=True)
    existing = list(docs_dir.glob(f"{'FAC' if args.facture else 'DEV'}-*"))
    num = str(len(existing) + 1).zfill(4)
    
    # Generer
    doc_type_label = "devis" if not args.facture else "facture"
    prefix = "DEV" if not args.facture else "FAC"
    
    html = _generate_html(
        doc_type_label, client, race, tel, email,
        formule["nom"], prix_ht, num, business, defaults
    )
    
    # Sauvegarder
    year = datetime.now().year
    filename = args.output or f"{prefix}-{year}-{num}-{re.sub(r'[^a-z0-9]', '-', client.lower()[:20])}.html"
    filepath = docs_dir / filename
    filepath.write_text(html, encoding="utf-8")
    
    titre_doc = "DEVIS" if not args.facture else "FACTURE"
    total = prix_ht * (1 + business['taux_tva'] / 100)
    print(f"\n✅ {titre_doc} genere : {filepath}")
    print(f"   Total TTC : {total:.2f} €")
    print(f"   Ouvrir dans le navigateur puis imprimer en PDF")


if __name__ == "__main__":
    main()
