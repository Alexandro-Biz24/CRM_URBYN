"""Enregistrement des demandes de chiffrage patio et de leurs photos."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ombrage_patio import OmbragePatioDemande, OmbragePatioPhoto
from app.schemas.patio_ombrage import PatioDemande
from app.services.email_sender import EmailDeliveryError, send_internal_notification
from app.services.patio_ombrage import PatioInput, public_quote

logger = logging.getLogger(__name__)

MAX_PHOTO_BYTES = 6 * 1024 * 1024

# Le type est déduit du contenu, jamais du nom de fichier ni de l'en-tête
# Content-Type, tous deux fournis par le client.
_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
]


class PhotoInvalide(ValueError):
    """Photo refusée : format non reconnu ou fichier trop lourd."""


@dataclass(frozen=True)
class PhotoRecue:
    patio_index: int
    data: bytes


def detecter_image(data: bytes) -> tuple[str, str]:
    """Renvoie (type MIME, extension) d'après la signature du fichier."""
    for signature, mime, extension in _SIGNATURES:
        if data.startswith(signature):
            return mime, extension
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise PhotoInvalide("Format de photo non reconnu : JPEG, PNG ou WebP attendu.")


def to_patio_inputs(demande) -> list[PatioInput]:
    return [
        PatioInput(
            nom=(patio.nom or "").strip() or f"Patio {index + 1}",
            largeur_1_mm=patio.largeur_1_mm,
            largeur_2_mm=patio.largeur_2_mm,
            longueur_1_mm=patio.longueur_1_mm,
            longueur_2_mm=patio.longueur_2_mm,
        )
        for index, patio in enumerate(demande.patios)
    ]


def enregistrer_demande(
    db: Session, demande: PatioDemande, photos: list[PhotoRecue]
) -> OmbragePatioDemande:
    """Recalcule le devis côté serveur, enregistre la demande et ses photos."""
    patios = to_patio_inputs(demande)
    devis = public_quote(patios, mise_en_place=demande.mise_en_place)

    ligne = OmbragePatioDemande(
        prenom=demande.contact.prenom.strip(),
        nom=demande.contact.nom.strip(),
        email=str(demande.contact.email),
        telephone=demande.contact.telephone.strip(),
        societe=demande.contact.societe.strip(),
        message=demande.contact.message.strip(),
        mise_en_place=demande.mise_en_place,
        patios=[patio.model_dump() for patio in demande.patios],
        devis=devis,
    )

    deja_vus: set[int] = set()
    for photo in photos:
        if not 0 <= photo.patio_index < len(patios):
            raise PhotoInvalide("Photo rattachée à un patio inexistant.")
        if photo.patio_index in deja_vus:
            raise PhotoInvalide("Une seule photo par patio.")
        deja_vus.add(photo.patio_index)
        if len(photo.data) > MAX_PHOTO_BYTES:
            raise PhotoInvalide("Photo trop lourde (6 Mo au maximum).")
        mime, extension = detecter_image(photo.data)
        ligne.photos.append(
            OmbragePatioPhoto(
                patio_index=photo.patio_index,
                filename=f"patio-{photo.patio_index + 1}.{extension}",
                content_type=mime,
                size=len(photo.data),
                data=photo.data,
            )
        )

    db.add(ligne)
    db.commit()
    db.refresh(ligne)
    return ligne


def _eur(value: float) -> str:
    return f"{value:,.0f} €".replace(",", " ")


def notifier_demande(ligne: OmbragePatioDemande) -> bool:
    """Prévient Urbanize par email, photos jointes. Ne fait jamais échouer la demande."""
    destinataire = settings.OMBRAGE_DEMANDE_EMAIL.strip()
    if not destinataire:
        logger.info("Demande ombrage n°%s enregistrée (aucun destinataire configuré)", ligne.id)
        return False

    devis = ligne.devis
    lignes = [
        f"Demande n° {ligne.id} — solution d'ombrage pour patio",
        "",
        f"Contact  : {ligne.prenom} {ligne.nom}",
        f"Société  : {ligne.societe or '—'}",
        f"Email    : {ligne.email}",
        f"Téléphone: {ligne.telephone}",
        f"Message  : {ligne.message or '—'}",
        "",
        f"Mise en place : {'oui — ' + _eur(devis['mise_en_place']['forfait']) if ligne.mise_en_place else 'non'}",
        "",
    ]
    avec_photo = {photo.patio_index for photo in ligne.photos}
    for index, patio in enumerate(devis["patios"]):
        retractable, fixe = patio["retractable"], patio["fixe"]
        lignes += [
            f"{patio['nom']} — {patio['surface_m2']:g} m²"
            f"{' — photo jointe' if index in avec_photo else ''}",
            "  Vélums repliables              : "
            + ", ".join(f"{v['longueur_mm'] / 1000:.2f} m" for v in retractable["velums"]),
            f"  Repliable, acquisition         : {_eur(retractable['acquisition']['prix_net'])}",
            f"  Repliable, mise à disposition  : {_eur(retractable['mise_a_disposition']['loyer_mensuel'])} / mois"
            f" sur {retractable['mise_a_disposition']['duree_mois']} mois",
            f"  Fixe, acquisition              : {_eur(fixe['acquisition']['prix_net'])}",
            "",
        ]
    lignes.append("Montants HT, tels que présentés au client sur le site.")

    try:
        send_internal_notification(
            to_email=destinataire,
            subject=f"Urbyn — Demande ombrage patio n° {ligne.id} ({ligne.societe or ligne.nom})",
            text="\n".join(lignes),
            reply_to=ligne.email,
            attachments=[(photo.filename, photo.content_type, photo.data) for photo in ligne.photos],
        )
    except EmailDeliveryError as exc:
        logger.error("Notification de la demande ombrage n°%s non envoyée : %s", ligne.id, exc)
        return False
    return True
