"""Contrôle du chiffrage patio contre le classeur de référence.

Valeurs lues dans « Urbanize_Modele_LLD » version 39 (09/11/2026), pour un
patio de 10 × 10 m commandé seul. À relancer après toute modification des
hypothèses ou des prix unitaires de app/services/patio_ombrage.py :

    .venv/bin/python scripts/check_patio_ombrage.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.patio_ombrage import Hypotheses, PatioInput, chiffrer, public_quote  # noqa: E402

patio = PatioInput("Patio 1", 10_000, 10_000, 10_000, 10_000)
c = chiffrer([patio])[0]
o = c.offres

REFERENCES = [
    ("Matériel (Patios B54)", c.materiel, 6116.2156),
    ("Toile (Patios B55)", c.toile, 1291.68),
    ("Coût du dispositif rétractable posé (Patios B59)", c.cout_pose, 15117.8956),
    ("Prix rétractable en acquisition (Patios B63)", c.prix_retractable, 23442.71208),
    ("Coût complet rétractable (Offres par patio B19)", o["retractable_acquisition"]["cout_complet_duree"], 32646.680936),
    ("Loyer mensuel (Offres par patio B58)", o["retractable_mise_a_disposition"]["loyer_mensuel"], 630),
    ("Coût du dispositif fixe posé (Patios B81)", c.fixe_cout_pose, 11039),
    ("Prix fixe en acquisition (Patios B86)", c.prix_fixe, 16766.5),
    ("Saisonnier sur la durée (Offres par patio B36)", o["fixe_acquisition"]["saisonnier_duree"], 16858.125),
    ("Coût complet fixe (Offres par patio B37)", o["fixe_acquisition"]["cout_complet_duree"], 34567.765),
    ("Forfait mise en place (Hypothèses B73)", Hypotheses().mise_en_place_ht, 7500),
]

ecarts = 0
for libelle, calcule, attendu in REFERENCES:
    ok = abs(calcule - attendu) < 0.005
    ecarts += not ok
    print(f"{'OK   ' if ok else 'ÉCART'} {libelle:52s} {calcule:>12.2f}  (classeur {attendu:>12.2f})")

# Le devis public ne doit porter aucun coût, coefficient ni marge.
brut = str(public_quote([patio])).lower()
fuites = [mot for mot in ("cout_pose", "materiel", "marge", "coef", "15117", "6116") if mot in brut]
print(f"{'OK   ' if not fuites else 'ÉCART'} Aucune donnée interne dans le devis public {fuites or ''}")

sys.exit(1 if ecarts or fuites else 0)
