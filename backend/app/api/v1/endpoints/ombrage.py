from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.admin_deps import require_admin
from app.core.deps import get_db
from app.models.ombrage_patio import OmbragePatioDemande, OmbragePatioPhoto
from app.schemas.patio_ombrage import PatioDemande, PatioQuoteRequest
from app.services.patio_ombrage import MAX_PATIOS, DimensionsImpossibles, public_quote
from app.services.patio_ombrage_demandes import (
    MAX_PHOTO_BYTES,
    PhotoInvalide,
    PhotoRecue,
    enregistrer_demande,
    notifier_demande,
    to_patio_inputs,
)

router = APIRouter()


@router.post("/patios/quote")
def quote_patios(body: PatioQuoteRequest) -> dict:
    """Chiffrage par patio : prix de vente uniquement, aucun coût ni marge."""
    try:
        return public_quote(
            to_patio_inputs(body),
            verification_annuelle=body.verification_annuelle,
            intervention_saisonniere=body.intervention_saisonniere,
            duree_annees=body.duree_annees,
        )
    except DimensionsImpossibles as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "dimensions_impossibles", "message": str(exc)},
        ) from exc


@router.post("/patios/demandes", status_code=status.HTTP_201_CREATED)
async def creer_demande(
    payload: str = Form(...),
    photos: list[UploadFile] = File(default=[]),
    photo_patios: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
) -> dict:
    """Enregistre une demande et les photos de patio jointes pour simulation.

    `payload` : JSON conforme à PatioDemande. `photo_patios[i]` donne l'index
    du patio auquel se rattache `photos[i]`.
    """
    try:
        demande = PatioDemande.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "demande_invalide", "errors": exc.errors(include_input=False)},
        ) from exc

    if len(photos) != len(photo_patios) or len(photos) > MAX_PATIOS:
        raise HTTPException(
            status_code=422,
            detail={"code": "photos_invalides", "message": "Photos et patios ne correspondent pas."},
        )

    recues: list[PhotoRecue] = []
    for fichier, index in zip(photos, photo_patios):
        # Lecture bornée : on ne charge jamais plus que la limite en mémoire.
        data = await fichier.read(MAX_PHOTO_BYTES + 1)
        recues.append(PhotoRecue(patio_index=index, data=data))

    try:
        ligne = enregistrer_demande(db, demande, recues)
    except PhotoInvalide as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "photo_invalide", "message": str(exc)},
        ) from exc
    except DimensionsImpossibles as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "dimensions_impossibles", "message": str(exc)},
        ) from exc

    notifier_demande(ligne)
    return {"id": ligne.id, "photos": len(ligne.photos)}


@router.get("/patios/demandes", dependencies=[Depends(require_admin)])
def lister_demandes(db: Session = Depends(get_db)) -> dict:
    lignes = db.query(OmbragePatioDemande).order_by(OmbragePatioDemande.id.desc()).limit(200).all()
    return {
        "demandes": [
            {
                "id": ligne.id,
                "created_at": ligne.created_at.isoformat(),
                "contact": {
                    "prenom": ligne.prenom,
                    "nom": ligne.nom,
                    "email": ligne.email,
                    "telephone": ligne.telephone,
                    "societe": ligne.societe,
                    "message": ligne.message,
                },
                "chantier": {
                    "adresse": ligne.chantier_adresse,
                    "complement": ligne.chantier_complement,
                    "code_postal": ligne.chantier_code_postal,
                    "ville": ligne.chantier_ville,
                    "pays": ligne.chantier_pays,
                },
                "duree_annees": ligne.duree_annees,
                "mise_en_place": ligne.mise_en_place,
                "patios": ligne.patios,
                "devis": ligne.devis,
                "photos": [
                    {"id": photo.id, "patio_index": photo.patio_index, "size": photo.size}
                    for photo in ligne.photos
                ],
            }
            for ligne in lignes
        ]
    }


@router.get("/patios/photos/{photo_id}", dependencies=[Depends(require_admin)])
def telecharger_photo(photo_id: int, db: Session = Depends(get_db)) -> Response:
    photo = db.get(OmbragePatioPhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo introuvable.")
    return Response(
        content=photo.data,
        media_type=photo.content_type,
        headers={"Content-Disposition": f'inline; filename="{photo.filename}"'},
    )
