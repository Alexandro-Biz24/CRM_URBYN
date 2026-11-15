"""Géométrie d'un patio et implantation des vélums.

Le patio est décrit par ses quatre côtés : A et B (largeurs), C et D
(longueurs). Sommets dans l'ordre A∩C, A∩D, B∩D, B∩C ; le côté A, où le
dispositif est installé, va du sommet 0 au sommet 1.

Ce module est la référence unique de l'implantation : le chiffrage s'appuie sur
les longueurs de vélums calculées ici, et le site dessine les polygones qu'il
renvoie. Ce qui est dessiné est donc exactement ce qui est chiffré.

Longueurs en mètres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float]

MARGE_COUVERTURE_FIXE_M = 0.15


def _aire_signee(points: list[Point]) -> float:
    somme = 0.0
    for i, (ax, ay) in enumerate(points):
        bx, by = points[(i + 1) % len(points)]
        somme += ax * by - bx * ay
    return somme / 2


def aire(points: list[Point]) -> float:
    return abs(_aire_signee(points))


def _est_convexe(points: list[Point]) -> bool:
    signe = 0
    for i in range(4):
        ax, ay = points[i]
        bx, by = points[(i + 1) % 4]
        cx, cy = points[(i + 2) % 4]
        produit = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if abs(produit) < 1e-9:
            continue
        if signe == 0:
            signe = 1 if produit > 0 else -1
        elif (1 if produit > 0 else -1) != signe:
            return False
    return True


def construire_quadrilatere(
    largeur_a: float, largeur_b: float, longueur_c: float, longueur_d: float
) -> list[Point] | None:
    """Reconstitue la forme du patio à partir de ses quatre côtés.

    Quatre longueurs laissent un angle libre : on retient la forme d'aire
    maximale, la plus régulière (un rectangle si les côtés opposés sont égaux).
    Même algorithme que `construireQuadrilatere` côté site.

    Renvoie None si aucun quadrilatère n'a ces côtés.
    """
    cotes = [largeur_a, largeur_b, longueur_c, longueur_d]
    if any(not c > 0 for c in cotes):
        return None
    plus_grand = max(cotes)
    if plus_grand >= sum(cotes) - plus_grand:
        return None

    a0: Point = (0.0, 0.0)
    a1: Point = (largeur_a, 0.0)
    meilleur: tuple[float, list[Point]] | None = None

    pas = 0
    while True:
        degres = 5 + pas * 0.25
        if degres > 175:
            break
        pas += 1
        angle = math.radians(degres)
        b0: Point = (longueur_c * math.cos(angle), longueur_c * math.sin(angle))
        dx, dy = a1[0] - b0[0], a1[1] - b0[1]
        distance = math.hypot(dx, dy)
        if (
            distance > largeur_b + longueur_d
            or distance < abs(largeur_b - longueur_d)
            or distance == 0
        ):
            continue
        k = (largeur_b**2 - longueur_d**2 + distance**2) / (2 * distance)
        h = math.sqrt(max(0.0, largeur_b**2 - k**2))
        mx, my = b0[0] + k * dx / distance, b0[1] + k * dy / distance
        for b1 in (
            (mx + h * dy / distance, my - h * dx / distance),
            (mx - h * dy / distance, my + h * dx / distance),
        ):
            if b1[1] <= 0 or b1[0] <= b0[0]:
                continue
            points = [a0, a1, b1, b0]
            if not _est_convexe(points):
                continue
            surface = aire(points)
            if meilleur is None or surface > meilleur[0]:
                meilleur = (surface, points)
    return meilleur[1] if meilleur else None


@dataclass(frozen=True)
class Repere:
    """Repère local du patio : s le long du grand côté, t vers l'intérieur."""

    origine: Point
    u: Point
    n: Point
    longueur_grand_cote: float
    profondeur: float

    def local(self, pt: Point) -> tuple[float, float]:
        vx, vy = pt[0] - self.origine[0], pt[1] - self.origine[1]
        return (vx * self.u[0] + vy * self.u[1], vx * self.n[0] + vy * self.n[1])

    def point(self, s: float, t: float) -> Point:
        return (
            self.origine[0] + s * self.u[0] + t * self.n[0],
            self.origine[1] + s * self.u[1] + t * self.n[1],
        )


def repere_du_patio(forme: list[Point]) -> Repere:
    """Repère porté par le plus long des deux côtés C et D, depuis le côté A."""
    a0, a1, b1, b0 = forme
    longe_c = math.dist(a0, b0) >= math.dist(a1, b1)
    origine, bout = (a0, b0) if longe_c else (a1, b1)
    longueur = math.dist(origine, bout)
    u = ((bout[0] - origine[0]) / longueur, (bout[1] - origine[1]) / longueur)
    centre = (sum(p[0] for p in forme) / 4, sum(p[1] for p in forme) / 4)
    n = (-u[1], u[0])
    if n[0] * (centre[0] - origine[0]) + n[1] * (centre[1] - origine[1]) < 0:
        n = (-n[0], -n[1])
    repere = Repere(origine, u, n, longueur, 0.0)
    profondeur = max(repere.local(pt)[1] for pt in forme)
    return Repere(origine, u, n, longueur, profondeur)


def _decouper(polygone: list[tuple[float, float]], t_limite: float, garder_dessus: bool):
    """Garde la partie du polygone (en coordonnées s, t) d'un côté de t = limite."""
    resultat: list[tuple[float, float]] = []
    for i, courant in enumerate(polygone):
        precedent = polygone[i - 1]

        def dedans(pt: tuple[float, float]) -> bool:
            return pt[1] >= t_limite - 1e-12 if garder_dessus else pt[1] <= t_limite + 1e-12

        def coupe() -> tuple[float, float]:
            k = (t_limite - precedent[1]) / (courant[1] - precedent[1])
            return (precedent[0] + k * (courant[0] - precedent[0]), t_limite)

        if dedans(courant):
            if not dedans(precedent):
                resultat.append(coupe())
            resultat.append(courant)
        elif dedans(precedent):
            resultat.append(coupe())
    return resultat


@dataclass(frozen=True)
class Velum:
    longueur: float
    largeur: float
    polygone: list[Point]


def implanter_velums_repliables(
    forme: list[Point], nb: int, largeur: float, espacement: float
) -> list[Velum]:
    """Vélums de la couverture repliable.

    Ils sont parallèles au grand côté du patio et s'empilent depuis celui-ci.
    Chacun couvre le patio sur toute l'étendue de sa bande : sa longueur va du
    point du patio le plus proche du côté A au point le plus éloigné, quitte à
    dépasser du contour là où le patio se rétrécit.
    """
    repere = repere_du_patio(forme)
    local = [repere.local(pt) for pt in forme]
    velums: list[Velum] = []
    for i in range(nb):
        t0 = i * (largeur + espacement)
        t1 = t0 + largeur
        tranche = _decouper(_decouper(local, t0, True), t1, False)
        if len(tranche) < 2:
            continue
        debut = min(pt[0] for pt in tranche)
        fin = max(pt[0] for pt in tranche)
        if fin - debut <= 0:
            continue
        velums.append(
            Velum(
                longueur=fin - debut,
                largeur=largeur,
                polygone=[
                    repere.point(debut, t0),
                    repere.point(fin, t0),
                    repere.point(fin, t1),
                    repere.point(debut, t1),
                ],
            )
        )
    return velums


def implanter_velums_fixes(
    forme: list[Point], nb: int, marge: float = MARGE_COUVERTURE_FIXE_M
) -> list[list[Point]]:
    """Couverture fixe : tout le patio, en retrait de `marge` sur sa périphérie,
    divisé en `nb` vélums jointifs empilés depuis le grand côté."""
    sens = 1 if _aire_signee(forme) >= 0 else -1
    droites = []
    for i, p in enumerate(forme):
        q = forme[(i + 1) % 4]
        longueur = math.dist(p, q) or 1.0
        d = ((q[0] - p[0]) / longueur, (q[1] - p[1]) / longueur)
        normale = (-d[1] * sens, d[0] * sens)
        droites.append(((p[0] + normale[0] * marge, p[1] + normale[1] * marge), d))

    def croiser(l1, l2) -> Point | None:
        (p1, d1), (p2, d2) = l1, l2
        det = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(det) < 1e-12:
            return None
        k = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / det
        return (p1[0] + k * d1[0], p1[1] + k * d1[1])

    sommets = [croiser(droites[(i + 3) % 4], droites[i]) for i in range(4)]
    if any(pt is None for pt in sommets):
        return []
    retrait: list[Point] = sommets  # type: ignore[assignment]
    if _aire_signee(retrait) * sens <= 0:
        return []

    # Les toiles sont jointives dans le sens du grand côté, comme les vélums
    # repliables : on découpe la couverture en bandes égales depuis ce côté.
    repere = repere_du_patio(forme)
    local = [repere.local(pt) for pt in retrait]
    t_min = min(pt[1] for pt in local)
    t_max = max(pt[1] for pt in local)
    velums: list[list[Point]] = []
    for i in range(nb):
        bas = t_min + (t_max - t_min) * i / nb
        haut = t_min + (t_max - t_min) * (i + 1) / nb
        tranche = _decouper(_decouper(local, bas, True), haut, False)
        if len(tranche) >= 3:
            velums.append([repere.point(s, t) for s, t in tranche])
    return velums
