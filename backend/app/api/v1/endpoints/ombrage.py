from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.google_sheets import GoogleSheetsError
from app.services.patio_sheets import MAX_PATIOS, write_patio_hypotheses

router = APIRouter()


class PatioHypotheseIn(BaseModel):
    nom: str = ""
    largeur_a: float = Field(ge=0)
    largeur_b: float = Field(ge=0)
    longueur_c: float = Field(ge=0)
    longueur_d: float = Field(ge=0)


class PatioHypothesesIn(BaseModel):
    patios: list[PatioHypotheseIn] = Field(min_length=1, max_length=MAX_PATIOS)


@router.post("/patios/hypotheses")
def enregistrer_hypotheses_patios(body: PatioHypothesesIn) -> dict:
    try:
        return write_patio_hypotheses([patio.model_dump() for patio in body.patios])
    except GoogleSheetsError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
