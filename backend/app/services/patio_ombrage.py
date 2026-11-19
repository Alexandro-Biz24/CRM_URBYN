"""Chiffrage des solutions d'ombrage pour patio.

Portage du classeur « Urbanize_Modele_LLD » (version 39, 09/11/2026) : feuilles
Hypothèses, Dispositif, Patios, Offres par patio et Emprunt.

Deux solutions, trois offres par patio :
- couverture rétractable, en acquisition ou en mise à disposition (location
  longue durée) ;
- couverture fixe, en acquisition uniquement.

Le classeur raisonne sur un rectangle (largeur de référence × plus grande
longueur). Ici le patio est un quadrilatère : les vélums repliables sont
implantés sur sa forme réelle (voir patio_geometrie) et chacun est chiffré à sa
propre longueur. Sur un patio rectangulaire, le résultat est identique à celui
du classeur.

Ce module contient les coûts d'achat, les coefficients et les taux de marge
d'Urbanize : il ne doit jamais être exposé tel quel. `public_quote()` est la
seule sortie destinée au site, elle ne renvoie que des prix de vente.

Toutes les longueurs sont en millimètres, tous les montants en euros HT.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.services.patio_geometrie import (
    Point,
    Velum,
    aire,
    construire_quadrilatere,
    implanter_velums_fixes,
    implanter_velums_repliables,
    repere_du_patio,
)

MAX_PATIOS = 10


# ── Hypothèses (feuille « Hypothèses ») ─────────────────────────────────────


@dataclass(frozen=True)
class Hypotheses:
    # Bloc 2 — les deux dispositifs
    velum_retractable_mm: int = 3000          # Dispositif B12, donnée fixe
    espacement_velums_mm: int = 100           # B23
    tolerance_min_mm: int = 750               # B24
    tolerance_pct: float = 0.05               # B25
    velum_fixe_max_mm: int = 5000             # C22
    fixe_materiel_eur_ml: float = 38.5        # C27
    poseurs: int = 4                          # B29
    cout_jour_poseur: float = 450.0           # B30
    operateurs_urbanize: int = 1              # B31
    pose_deplacement_pct: float = 0.4         # B32
    cout_livraison: float = 1200.0            # Dispositif F68
    patios_par_livraison_retractable: int = 2  # B34
    patios_par_livraison_fixe: int = 4        # C34
    saison_equipe: int = 4                    # C35
    saison_jours_par_patio: float = 0.5       # C36
    saison_deplacement_pct: float = 0.25      # C38
    saison_interventions_an1: int = 1         # C39
    saison_interventions_par_an: int = 2      # C40
    saison_gestion_projet_jh: float = 0.5     # C42

    # Bloc 4 — coefficients de vente
    coef_materiel_retractable: float = 1.8    # B53
    coef_materiel_fixe: float = 2.0           # C53
    coef_pose: float = 1.35                   # B54 / C54
    coef_livraison: float = 1.1               # B55 / C55
    coef_saisonnier: float = 1.35             # C56
    verification_annuelle_facturee: float = 1500.0  # B61
    demontage_a_charge_client: int = 0        # B62

    # Bloc 5 — mise en place commune
    etude_thermique: float = 500.0            # B65
    etude_thermique_incluse: int = 0          # C65
    etude_bureau_etudes: float = 1825.0       # B66
    cout_jh_interne: float = 525.0            # B67
    suivi_projet_jh: float = 2.0              # E68
    travail_preparatoire_jh: float = 1.5      # E69
    deplacements_projet: float = 2000.0       # B70
    prix_jh_interne: float = 1050.0           # B72

    # Bloc 6 — services et risques
    verification_poseurs: int = 2             # B76
    verification_deplacement: float = 500.0   # B78
    petit_materiel_par_velum: float = 30.0    # B79
    petit_materiel_part_parc: float = 0.1     # B80
    assurance_pct: float = 0.012              # B81
    remplacement_pieces_pct: float = 0.2      # B82
    demontage_pct_pose: float = 2 / 3         # B84
    reemploi_tubes_fin: float = 0.3           # B86

    # Bloc 7 — location longue durée
    duree_mois: int = 60                      # B91
    marge_location: float = 0.2               # B93
    arrondi_loyer: float = 5.0                # B94
    taux_emprunt: float = 0.05                # B98
    duree_pret_mois: int = 60                 # B99

    @property
    def mise_en_place_ht(self) -> float:
        """Forfait « Mise en place » (Hypothèses B73)."""
        temps_interne = self.suivi_projet_jh + self.travail_preparatoire_jh
        return (
            self.etude_thermique * self.etude_thermique_incluse
            + self.etude_bureau_etudes
            + self.deplacements_projet
            + temps_interne * self.prix_jh_interne
        )

    @property
    def cout_jour_equipe_pose(self) -> float:
        return (
            self.poseurs * self.cout_jour_poseur
            + self.operateurs_urbanize * self.cout_jh_interne
        )

    @property
    def cout_intervention_saisonniere(self) -> float:
        """Coût d'une dépose ou d'une repose, par patio (C41)."""
        return (
            self.saison_equipe
            * self.cout_jour_poseur
            * self.saison_jours_par_patio
            * (1 + self.saison_deplacement_pct)
        )

    @property
    def nb_campagnes_saisonnieres(self) -> float:
        return self.saison_interventions_an1 + self.saison_interventions_par_an * (
            self.duree_mois / 12 - 1
        )


# ── Prix unitaires du dispositif rétractable (feuille « Dispositif ») ──────


@dataclass(frozen=True)
class PrixRetractable:
    distance_max_tubes_mm: int = 800          # B11
    longueur_max_bache_mm: int = 3200         # B13 = B11 × 4
    marge_rangement_bache_mm: int = 60

    vis_m12: float = 7.85
    boulon_m10: float = 0.15
    ecrou_m8: float = 0.37
    boulon_m6: float = 0.11
    boulon_m5: float = 0.47
    etrier_d42: float = 4.5
    rondelle_m10: float = 0.04
    rondelle_m8: float = 0.1
    rondelle_m6: float = 0.04
    rondelle_m5: float = 0.024
    bouchon_d40: float = 0.46

    taquet: float = 10.75
    poulie_mobile: float = 9.08
    poulie_fixe: float = 6.67
    maillon: float = 1.32
    ridoir: float = 4.75
    cosse_coeur: float = 1.21
    manchon: float = 7.31
    platine_oeillet: float = 3.65
    cable_inox_m: float = 7.06
    corde_m: float = 0.58

    platine_support_court: float = 20.17
    barre_u_support_court: float = 67.0
    platine_support_long: float = 52.54
    barre_u_support_long: float = 62.14
    support_horizontal: float = 40.76
    accroche: float = 3.1
    capot: float = 300.0
    tube_alu_eur_m: float = 3.99

    bache_section: float = 126.36             # 9,72 × 13
    bache_extremite: float = 51.48


# ── Entrées ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PatioInput:
    nom: str
    largeur_1_mm: float
    largeur_2_mm: float
    longueur_1_mm: float
    longueur_2_mm: float


class DimensionsImpossibles(ValueError):
    """Les quatre côtés saisis ne peuvent pas former un patio."""


# ── Résultats internes (avec coûts : ne pas exposer) ───────────────────────


@dataclass
class PatioChiffrage:
    patio: PatioInput
    forme: list[Point]
    # Profondeur du patio perpendiculairement à son grand côté, et longueur de
    # celui-ci : ce sont la « largeur » et la « longueur » du classeur.
    profondeur_mm: float
    grand_cote_mm: float
    surface_m2: float
    velums: list[Velum] = field(default_factory=list)
    velums_fixes: list[list[Point]] = field(default_factory=list)

    # Rétractable
    nb_velums: int = 0
    largeur_couverte_mm: float = 0.0
    ecart_par_cote_mm: float = 0.0
    tolerance_mm: float = 0.0
    hors_tolerance: bool = False
    materiel: float = 0.0
    toile: float = 0.0
    livraison: float = 0.0
    pose: float = 0.0
    cout_pose: float = 0.0
    pieces_remplacables: float = 0.0
    valeur_tubes: float = 0.0
    prix_retractable: float = 0.0

    # Fixe
    nb_velums_fixes: int = 0
    largeur_velum_fixe_mm: float = 0.0
    fixe_toile: float = 0.0
    fixe_cout_pose: float = 0.0
    prix_fixe: float = 0.0

    # Offres (remplies par chiffrer())
    offres: dict = field(default_factory=dict)


def _arrondi_excel(value: float) -> int:
    """ROUND() d'Excel : arrondi au plus proche, la demie vers le haut."""
    return int(math.floor(value + 0.5))


def _plafond(value: float, pas: float) -> float:
    """CEILING() d'Excel : multiple de `pas` immédiatement supérieur."""
    return math.ceil(round(value / pas, 9)) * pas


def _interets_emprunt(montant: float, taux_annuel: float, mois: int) -> float:
    """Total des intérêts d'un prêt à mensualités constantes (feuille Emprunt)."""
    if montant <= 0 or mois <= 0:
        return 0.0
    taux = taux_annuel / 12
    if taux == 0:
        return 0.0
    mensualite = montant * taux / (1 - (1 + taux) ** -mois)
    return mensualite * mois - montant


def _bache(longueur_totale_mm: float, p: PrixRetractable) -> float:
    """Bâche d'un vélum : sections standard plus une section d'extrémité."""
    return (
        math.ceil(longueur_totale_mm / p.longueur_max_bache_mm) - 1
    ) * p.bache_section + p.bache_extremite


def _longueur_avec_rangement(longueur_mm: float, p: PrixRetractable) -> float:
    return longueur_mm + (
        math.ceil(longueur_mm / p.distance_max_tubes_mm) + 1
    ) * p.marge_rangement_bache_mm


def _nb_velums(profondeur_mm: float, h: Hypotheses) -> int:
    return max(
        1,
        _arrondi_excel(
            (profondeur_mm + h.espacement_velums_mm)
            / (h.velum_retractable_mm + h.espacement_velums_mm)
        ),
    )


def _chiffrer_dispositifs(
    patio: PatioInput, nb_patios: int, h: Hypotheses, p: PrixRetractable
) -> PatioChiffrage:
    forme = construire_quadrilatere(
        patio.largeur_1_mm / 1000,
        patio.largeur_2_mm / 1000,
        patio.longueur_1_mm / 1000,
        patio.longueur_2_mm / 1000,
    )
    if forme is None:
        raise DimensionsImpossibles(
            f"Les quatre côtés de « {patio.nom} » ne peuvent pas former un patio."
        )
    repere = repere_du_patio(forme)
    # Arrondi au millimètre : évite qu'un écart d'arrondi flottant ne fasse
    # basculer un nombre de tubes ou de sections de bâche.
    profondeur = round(repere.profondeur * 1000)
    grand_cote = round(repere.longueur_grand_cote * 1000)
    c = PatioChiffrage(
        patio=patio,
        forme=forme,
        profondeur_mm=profondeur,
        grand_cote_mm=grand_cote,
        surface_m2=aire(forme),
    )

    # ── Repliable : un vélum par bande de 3 m, chacun à sa propre longueur ──
    c.velums = implanter_velums_repliables(
        forme,
        _nb_velums(profondeur, h),
        h.velum_retractable_mm / 1000,
        h.espacement_velums_mm / 1000,
    )
    n = len(c.velums)
    longueurs_totales = [
        _longueur_avec_rangement(round(v.longueur * 1000), p) for v in c.velums
    ]
    tubes = [math.ceil(lt / p.distance_max_tubes_mm) + 1 for lt in longueurs_totales]
    total_tubes = sum(tubes)
    jours = math.ceil(0.5 + n / 2)

    quincaillerie = (
        36 * n * p.vis_m12
        + 28 * n * p.boulon_m10
        + 4 * n * p.ecrou_m8
        + sum(2 * t + 15 for t in tubes) * p.boulon_m6
        + 10 * n * p.boulon_m5
        + 2 * n * p.etrier_d42
        + 28 * n * p.rondelle_m10
        + 4 * n * p.rondelle_m8
        + sum(2 * t + 15 for t in tubes) * p.rondelle_m6
        + math.ceil(10 * n / 50) * 50 * p.rondelle_m5
        + math.ceil(2 * total_tubes / 50) * 50 * p.bouchon_d40
    )
    accastillage = (
        2 * n * p.taquet
        + sum(2 * t - 1 for t in tubes) * p.poulie_mobile
        + 3 * n * p.poulie_fixe
        + sum(2 * t - 1 for t in tubes) * p.maillon
        + 2 * n * p.ridoir
        + 4 * n * p.cosse_coeur
        + 4 * n * p.manchon
        + 4 * n * p.platine_oeillet
        + sum(2 * lt / 1000 + 0.5 for lt in longueurs_totales) * p.cable_inox_m
        + sum(2 * lt / 1000 + 2 for lt in longueurs_totales) * p.corde_m
    )
    prix_tube = p.tube_alu_eur_m * h.velum_retractable_mm / 1000
    valeur_tubes = total_tubes * prix_tube
    metallerie = (
        3 * n * p.platine_support_court
        + 3 * n * p.barre_u_support_court
        + 3 * n * p.platine_support_long
        + 3 * n * p.barre_u_support_long
        + 4 * n * p.support_horizontal
        + 2 * total_tubes * p.accroche
        + p.capot
        + valeur_tubes
    )
    bache = sum(_bache(lt, p) for lt in longueurs_totales)

    c.nb_velums = n
    c.materiel = quincaillerie + accastillage + metallerie
    c.toile = bache
    c.livraison = (
        math.ceil(nb_patios / h.patios_par_livraison_retractable)
        * h.cout_livraison
        / nb_patios
    )
    main_oeuvre = h.cout_jour_equipe_pose * jours
    c.pose = main_oeuvre * (1 + h.pose_deplacement_pct)
    c.cout_pose = c.materiel + c.toile + c.livraison + c.pose
    c.pieces_remplacables = quincaillerie + accastillage + bache
    c.valeur_tubes = valeur_tubes
    c.prix_retractable = (
        (c.materiel + c.toile) * h.coef_materiel_retractable
        + c.pose * h.coef_pose
        + c.livraison * h.coef_livraison
    )

    # ── Repliable : profondeur couverte et tolérance ──
    c.largeur_couverte_mm = n * h.velum_retractable_mm + max(n - 1, 0) * h.espacement_velums_mm
    c.ecart_par_cote_mm = (profondeur - c.largeur_couverte_mm) / 2
    c.tolerance_mm = max(h.tolerance_min_mm, h.tolerance_pct * profondeur)
    c.hors_tolerance = abs(c.ecart_par_cote_mm) > c.tolerance_mm

    # ── Fixe : chiffrée comme dans le classeur, sur le rectangle enveloppe
    #    (profondeur × grand côté). La toile reprend le prix au m² d'une bâche
    #    repliable de référence couvrant ce rectangle. ──
    nf = math.ceil(profondeur / h.velum_fixe_max_mm)
    largeur_velum_m = profondeur / nf / 1000
    perimetre = 2 * (largeur_velum_m + grand_cote / 1000)
    metres_lineaires = nf * perimetre - max(nf - 1, 0) * grand_cote / 1000
    fixe_materiel = metres_lineaires * h.fixe_materiel_eur_ml
    n_ref = _nb_velums(profondeur, h)
    couverte_ref = n_ref * h.velum_retractable_mm + max(n_ref - 1, 0) * h.espacement_velums_mm
    bache_ref = n_ref * _bache(_longueur_avec_rangement(grand_cote, p), p)
    fixe_toile = bache_ref * profondeur / couverte_ref
    fixe_livraison = (
        math.ceil(nb_patios / h.patios_par_livraison_fixe) * h.cout_livraison / nb_patios
    )
    jours_fixe = math.ceil(0.5 + nf / 2)
    fixe_pose = h.cout_jour_equipe_pose * jours_fixe * (1 + h.pose_deplacement_pct)

    c.nb_velums_fixes = nf
    c.largeur_velum_fixe_mm = profondeur / nf
    c.velums_fixes = implanter_velums_fixes(forme, nf)
    c.fixe_toile = fixe_toile
    c.fixe_cout_pose = fixe_materiel + fixe_toile + fixe_livraison + fixe_pose
    c.prix_fixe = (
        (fixe_materiel + fixe_toile) * h.coef_materiel_fixe
        + fixe_pose * h.coef_pose
        + fixe_livraison * h.coef_livraison
    )
    return c


def chiffrer(
    patios: list[PatioInput],
    hypotheses: Hypotheses | None = None,
    prix: PrixRetractable | None = None,
) -> list[PatioChiffrage]:
    """Chiffre chaque patio. Les postes mutualisés dépendent du lot entier."""
    h = hypotheses or Hypotheses()
    p = prix or PrixRetractable()
    if not patios:
        return []
    if len(patios) > MAX_PATIOS:
        raise ValueError(f"Au plus {MAX_PATIOS} patios par demande.")

    chiffrages = [_chiffrer_dispositifs(patio, len(patios), h, p) for patio in patios]

    surface_totale = sum(c.surface_m2 for c in chiffrages)
    cout_retractable_total = sum(c.cout_pose for c in chiffrages)
    interets_totaux = _interets_emprunt(
        cout_retractable_total, h.taux_emprunt, h.duree_pret_mois
    )
    annees = h.duree_mois / 12
    verification_cout_annuel = (
        h.verification_poseurs * h.cout_jour_poseur + h.verification_deplacement
    )
    gestion_projet_saison = (
        h.saison_gestion_projet_jh * h.cout_jh_interne * h.nb_campagnes_saisonnieres
    )

    for c in chiffrages:
        part_surface = c.surface_m2 / surface_totale if surface_totale else 0.0
        part_cout = c.cout_pose / cout_retractable_total if cout_retractable_total else 0.0
        demontage = h.demontage_pct_pose * c.pose

        # Rétractable — acquisition (Offres par patio, lignes 15 à 21)
        verification_annuelle = h.verification_annuelle_facturee * part_surface
        cout_complet_acquisition = (
            c.prix_retractable
            + verification_annuelle * annees
            + h.assurance_pct * c.cout_pose * annees
            + c.pieces_remplacables * h.remplacement_pieces_pct
            + demontage * h.demontage_a_charge_client
        )

        # Rétractable — location longue durée (lignes 49 à 58)
        cout_location = (
            c.cout_pose
            + interets_totaux * part_cout
            + (
                verification_cout_annuel * part_surface
                + h.petit_materiel_par_velum * c.nb_velums * h.petit_materiel_part_parc
            )
            * annees
            + h.assurance_pct * c.cout_pose * annees
            + c.pieces_remplacables * h.remplacement_pieces_pct
            + demontage
            - c.valeur_tubes * h.reemploi_tubes_fin
        )
        loyer = _plafond(
            cout_location / ((1 - h.marge_location) * h.duree_mois), h.arrondi_loyer
        )

        # Fixe — acquisition (lignes 32 à 40)
        saisonnier_annuel_base = (
            h.cout_intervention_saisonniere
            + h.saison_gestion_projet_jh * h.cout_jh_interne * part_surface
        ) * h.coef_saisonnier
        saisonnier_duree = (
            h.cout_intervention_saisonniere * h.nb_campagnes_saisonnieres
            + gestion_projet_saison * part_surface
        ) * h.coef_saisonnier
        cout_complet_fixe = (
            c.prix_fixe
            + saisonnier_duree
            + h.assurance_pct * c.fixe_cout_pose * annees
            + c.fixe_toile * h.remplacement_pieces_pct
            + demontage * h.demontage_a_charge_client
        )

        c.offres = {
            "retractable_acquisition": {
                "prix_net": c.prix_retractable,
                "verification_annuelle": verification_annuelle,
                "cout_complet_duree": cout_complet_acquisition,
            },
            "retractable_mise_a_disposition": {
                "loyer_mensuel": loyer,
                "duree_mois": h.duree_mois,
                "total_loyers": loyer * h.duree_mois,
            },
            "fixe_acquisition": {
                "prix_net": c.prix_fixe,
                "saisonnier_premiere_annee": saisonnier_annuel_base
                * h.saison_interventions_an1,
                "saisonnier_annees_suivantes": saisonnier_annuel_base
                * h.saison_interventions_par_an,
                "saisonnier_duree": saisonnier_duree,
                "cout_complet_duree": cout_complet_fixe,
            },
        }
    return chiffrages


# ── Sortie publique : prix de vente uniquement ─────────────────────────────


def _eur(value: float) -> float:
    return round(value + 1e-9, 2)


def public_quote(
    patios: list[PatioInput],
    *,
    mise_en_place: bool = True,
    verification_annuelle: bool = False,
    intervention_saisonniere: bool = False,
    hypotheses: Hypotheses | None = None,
) -> dict:
    """Devis destiné au site : aucun coût, coefficient ni taux de marge."""
    h = hypotheses or Hypotheses()
    chiffrages = chiffrer(patios, h)
    forfait = _eur(h.mise_en_place_ht) if mise_en_place else 0.0

    def _points(polygone: list[Point]) -> list[list[float]]:
        return [[round(x, 4), round(y, 4)] for x, y in polygone]

    lignes = []
    for c in chiffrages:
        o = c.offres
        lignes.append(
            {
                "nom": c.patio.nom,
                "surface_m2": round(c.surface_m2, 2),
                "profondeur_mm": round(c.profondeur_mm),
                "grand_cote_mm": round(c.grand_cote_mm),
                # Forme du patio, en mètres, dans l'ordre A∩C, A∩D, B∩D, B∩C.
                "forme": _points(c.forme),
                "retractable": {
                    "nb_velums": c.nb_velums,
                    "largeur_velum_mm": h.velum_retractable_mm,
                    "espacement_mm": h.espacement_velums_mm,
                    "velums": [
                        {
                            "longueur_mm": round(v.longueur * 1000),
                            "polygone": _points(v.polygone),
                        }
                        for v in c.velums
                    ],
                    "hors_tolerance": c.hors_tolerance,
                    "acquisition": {
                        k: _eur(v) for k, v in o["retractable_acquisition"].items()
                    },
                    "mise_a_disposition": {
                        "loyer_mensuel": _eur(
                            o["retractable_mise_a_disposition"]["loyer_mensuel"]
                        ),
                        "duree_mois": o["retractable_mise_a_disposition"]["duree_mois"],
                        "total_loyers": _eur(
                            o["retractable_mise_a_disposition"]["total_loyers"]
                        ),
                    },
                },
                "fixe": {
                    "nb_velums": c.nb_velums_fixes,
                    "largeur_velum_mm": round(c.largeur_velum_fixe_mm),
                    "velums": [_points(polygone) for polygone in c.velums_fixes],
                    "acquisition": {k: _eur(v) for k, v in o["fixe_acquisition"].items()},
                },
            }
        )

    def _total(solution: str, offre: str, cle: str) -> float:
        return _eur(sum(ligne[solution][offre][cle] for ligne in lignes))

    return {
        "devise": "EUR",
        "montants": "HT",
        "duree_mois": h.duree_mois,
        "mise_en_place": {
            "incluse": mise_en_place,
            "forfait": forfait,
            "prestations": [
                "Étude thermique",
                "Étude de bureau d'études",
                "Repérage et prise de mesure",
            ],
        },
        # Options choisies par le client : les montants correspondants figurent
        # dans chaque patio, le site ne les affiche que si l'option est retenue.
        "options": {
            "verification_annuelle": verification_annuelle,
            "intervention_saisonniere": intervention_saisonniere,
        },
        "patios": lignes,
        "totaux": {
            "surface_m2": round(sum(ligne["surface_m2"] for ligne in lignes), 2),
            "retractable_acquisition": _total("retractable", "acquisition", "prix_net"),
            "retractable_loyer_mensuel": _total(
                "retractable", "mise_a_disposition", "loyer_mensuel"
            ),
            "fixe_acquisition": _total("fixe", "acquisition", "prix_net"),
            "retractable_verification_annuelle": _total(
                "retractable", "acquisition", "verification_annuelle"
            ),
            "fixe_saisonnier_annees_suivantes": _total(
                "fixe", "acquisition", "saisonnier_annees_suivantes"
            ),
            "fixe_saisonnier_premiere_annee": _total(
                "fixe", "acquisition", "saisonnier_premiere_annee"
            ),
        },
    }
