#!/usr/bin/env python3
"""
Sellsy API v2 — Export complet : Opportunités + Achats fournisseurs + Clients
Pour alimenter les analyses 360° Urbanize

Token endpoint : https://login.sellsy.com/oauth2/access-tokens
API base       : https://api.sellsy.com/v2
"""

import requests, json, csv, sys, os, time
from datetime import datetime

CLIENT_ID     = "bc4b27e6-0559-4b7d-b644-41d72a0652f4"
CLIENT_SECRET = "c21b498addcefc106185d46208d5237c9078e9c641b76064a5309d6dcf4f01a2"
TOKEN_URL     = "https://login.sellsy.com/oauth2/access-tokens"
API_BASE      = "https://api.sellsy.com/v2"
OUTPUT_DIR    = "sellsy_full_export"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── AUTH ─────────────────────────────────────────────────────────────────────
def get_token():
    r = requests.post(TOKEN_URL,
        data={"grant_type":"client_credentials","client_id":CLIENT_ID,"client_secret":CLIENT_SECRET},
        headers={"Content-Type":"application/x-www-form-urlencoded"}, timeout=15)
    if r.status_code == 200:
        print(f"✅ Token obtenu")
        return r.json()["access_token"]
    print(f"❌ Auth : {r.status_code} — {r.text[:200]}")
    sys.exit(1)

# ─── REQUÊTE ──────────────────────────────────────────────────────────────────
def api_get(token, path, params=None):
    r = requests.get(f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept":"application/json"},
        params=params, timeout=30)
    if r.status_code == 200:
        return r.json()
    try:
        err = r.json().get("error",{})
        print(f"  ⚠️  {path} → {r.status_code} : {err.get('message','')}")
    except:
        print(f"  ⚠️  {path} → {r.status_code}")
    return None

def fetch_all(token, path, params=None, page_size=100, label=""):
    items, offset = [], 0
    while True:
        p = {**(params or {}), "limit": page_size, "offset": offset}
        data = api_get(token, path, p)
        if not data: break
        batch = data.get("data", [])
        total = data.get("pagination", {}).get("total", len(batch))
        if not batch: break
        items.extend(batch)
        if label: print(f"  {len(items)}/{total} {label}")
        if len(items) >= total: break
        offset += page_size
        time.sleep(0.1)  # éviter le rate limiting
    return items

# ─── EXPORTS ──────────────────────────────────────────────────────────────────
def save_json(data, name):
    path = f"{OUTPUT_DIR}/{name}"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 {path} ({len(data)} enregistrements)")

def save_csv(rows, name):
    if not rows: return
    path = f"{OUTPUT_DIR}/{name}"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter=";")
        w.writeheader(); w.writerows(rows)
    print(f"  💾 {path} ({len(rows)} lignes)")

def v(val, *keys):
    """Extraire une valeur imbriquée en tolérant None."""
    cur = val
    for k in keys:
        if cur is None: return ""
        if isinstance(cur, dict): cur = cur.get(k)
        else: return ""
    return cur if cur is not None else ""

def amt(val):
    if isinstance(val, dict): return val.get("value", "")
    return val or ""

def d(val):
    return str(val)[:10] if val else ""

# ─── OPPORTUNITÉS ─────────────────────────────────────────────────────────────
def export_opportunities(token):
    print("\n🎯 OPPORTUNITÉS...")
    items = fetch_all(token, "/opportunities", label="opportunités")
    if not items:
        print("  ⚠️  Aucune opportunité (vérifiez le scope 'Opportunités' de votre clé API)")
        return []
    save_json(items, "opportunities_raw.json")
    rows = []
    for o in items:
        rows.append({
            "ID":               v(o,"id"),
            "Nom":              v(o,"name"),
            "Statut":           v(o,"status"),
            "Etape":            v(o,"step","name"),
            "Pipeline":         v(o,"pipeline","name"),
            "Montant HT":       amt(v(o,"amount")),
            "Probabilite %":    v(o,"probability"),
            "Date cloture":     d(v(o,"closeDate")),
            "Client":           v(o,"thirdParty","name"),
            "Email client":     v(o,"thirdParty","email"),
            "Responsable":      v(o,"owner","name"),
            "Tags":             ", ".join([t.get("name","") for t in (o.get("tags") or [])]),
            "Source":           v(o,"source","name"),
            "Date creation":    d(v(o,"created")),
            "Description":      (v(o,"description") or "")[:200],
        })
    save_csv(rows, "opportunities.csv")
    print(f"  ✅ {len(rows)} opportunités exportées")

    # Statistiques
    won  = [o for o in rows if str(o.get("Statut","")).lower() in ("won","gagne","won")]
    lost = [o for o in rows if str(o.get("Statut","")).lower() in ("lost","perdu","lost")]
    open_opps = [o for o in rows if o not in won and o not in lost]
    print(f"     Gagnées: {len(won)} | Perdues: {len(lost)} | En cours: {len(open_opps)}")

    return items

# ─── ACHATS FOURNISSEURS ───────────────────────────────────────────────────────
def export_purchases(token):
    print("\n📦 ACHATS FOURNISSEURS...")

    # Test des endpoints connus
    for path in ["/purchases/incoming", "/purchase-invoices"]:
        test = api_get(token, path, {"limit":1})
        if test is not None:
            print(f"  ✅ Endpoint : {path}")
            items = fetch_all(token, path, label="achats")
            save_json(items, "purchases_raw.json")

            rows = []
            for p in items:
                amount = p.get("amount") or {}
                rows.append({
                    "ID":               v(p,"id"),
                    "Numero":           v(p,"number"),
                    "Objet":            v(p,"subject"),
                    "Date":             d(v(p,"displayedDate")),
                    "Type":             v(p,"type"),
                    "Statut":           v(p,"status"),
                    "Fournisseur":      v(p,"thirdParty","name"),
                    "Email fournisseur":v(p,"thirdParty","email"),
                    "Total HT":         amt(amount.get("totalExcludingTaxes")),
                    "TVA":              amt(amount.get("taxes")),
                    "Total TTC":        amt(amount.get("total")),
                    "Devise":           v(p,"currency") or "EUR",
                    "Proprietaire":     v(p,"owner","name"),
                    "Date creation":    d(v(p,"created")),
                })
            save_csv(rows, "purchases.csv")

            # Lignes de détail
            print(f"  📋 Récupération des lignes de détail...")
            all_rows = []
            for i, p in enumerate(items):
                if i % 20 == 0: print(f"    {i}/{len(items)}...")
                detail = api_get(token, f"/purchases/{v(p,'id')}/rows")
                if detail:
                    for row in detail.get("data", []):
                        all_rows.append({
                            "Document":     v(p,"number"),
                            "Date":         d(v(p,"displayedDate")),
                            "Fournisseur":  v(p,"thirdParty","name"),
                            "Produit":      v(row,"name"),
                            "Reference":    v(row,"reference"),
                            "Quantite":     v(row,"quantity"),
                            "PU HT":        amt(v(row,"unitAmount")),
                            "Total HT":     amt(v(row,"totalAmount")),
                            "TVA":          amt(v(row,"taxAmount")),
                        })
                time.sleep(0.05)

            if all_rows:
                save_csv(all_rows, "purchases_rows.csv")
                print(f"  ✅ {len(all_rows)} lignes de détail")
            return items

    print("  ❌ Aucun endpoint achat accessible")
    print("  → Vérifiez que le scope 'Achats' est activé dans Sellsy > Préférences > API V2")
    return []

# ─── CLIENTS & CONTACTS ───────────────────────────────────────────────────────
def export_clients(token):
    print("\n🏢 CLIENTS & PROSPECTS...")
    items = fetch_all(token, "/companies", label="entreprises")
    save_json(items, "companies_raw.json")

    rows = []
    for c in items:
        addr = c.get("mainAddress") or {}
        rows.append({
            "ID":           v(c,"id"),
            "Type":         v(c,"type"),
            "Nom":          v(c,"name"),
            "Email":        v(c,"email"),
            "Tel":          v(c,"phone"),
            "Siret":        v(c,"siret"),
            "Code NAF":     v(c,"apeCode"),
            "Statut":       v(c,"status"),
            "Adresse":      v(addr,"address"),
            "Ville":        v(addr,"city"),
            "CP":           v(addr,"zipCode"),
            "Pays":         v(addr,"country"),
            "Tags":         ", ".join([t.get("name","") for t in (c.get("tags") or [])]),
            "Date creation": d(v(c,"created")),
        })
    save_csv(rows, "companies.csv")

    clients   = [r for r in rows if r["Type"] == "client"]
    prospects = [r for r in rows if r["Type"] == "prospect"]
    suppliers = [r for r in rows if r["Type"] == "supplier"]
    save_csv(clients,   "clients.csv")
    save_csv(prospects, "prospects.csv")
    save_csv(suppliers, "suppliers_companies.csv")
    print(f"  ✅ {len(clients)} clients | {len(prospects)} prospects | {len(suppliers)} fournisseurs")
    return items

# ─── FACTURES VENTES ──────────────────────────────────────────────────────────
def export_invoices(token):
    print("\n🧾 FACTURES DE VENTE...")
    items = fetch_all(token, "/invoices", label="factures")
    if not items: return []
    save_json(items, "invoices_raw.json")

    rows = []
    for inv in items:
        amount = inv.get("amount") or {}
        rows.append({
            "ID":           v(inv,"id"),
            "Numero":       v(inv,"number"),
            "Objet":        v(inv,"subject"),
            "Date":         d(v(inv,"displayedDate")),
            "Echeance":     d(v(inv,"dueDate")),
            "Statut":       v(inv,"status"),
            "Client":       v(inv,"thirdParty","name"),
            "Email":        v(inv,"thirdParty","email"),
            "Total HT":     amt(amount.get("totalExcludingTaxes")),
            "TVA":          amt(amount.get("taxes")),
            "Total TTC":    amt(amount.get("total")),
            "Devise":       v(inv,"currency") or "EUR",
            "Proprietaire": v(inv,"owner","name"),
        })
    save_csv(rows, "invoices.csv")
    print(f"  ✅ {len(rows)} factures")
    return items

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  SELLSY v2 — Export Complet pour Analyses 360°")
    print("=" * 60)

    token = get_token()

    companies    = export_clients(token)
    invoices     = export_invoices(token)
    opportunities = export_opportunities(token)
    purchases    = export_purchases(token)

    print("\n" + "=" * 60)
    print("  RÉSUMÉ")
    print("=" * 60)
    print(f"  Entreprises     : {len(companies)}")
    print(f"  Factures vente  : {len(invoices)}")
    print(f"  Opportunités    : {len(opportunities)}")
    print(f"  Achats          : {len(purchases)}")
    print(f"\n  📁 Fichiers dans : ./{OUTPUT_DIR}/")
    print("=" * 60)
    print("""
  Fichiers générés :
  - companies.csv          → toutes les entreprises
  - clients.csv            → clients uniquement
  - prospects.csv          → prospects uniquement
  - suppliers_companies.csv→ fournisseurs (annuaire)
  - invoices.csv           → factures de vente
  - opportunities.csv      → opportunités commerciales
  - purchases.csv          → achats fournisseurs (si scope OK)
  - purchases_rows.csv     → lignes de détail achats
  - *_raw.json             → données brutes complètes
""")
