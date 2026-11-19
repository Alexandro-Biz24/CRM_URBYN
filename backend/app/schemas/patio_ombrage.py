from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints

from app.services.patio_ombrage import MAX_PATIOS

# Bornes de saisie : en dehors, le modèle de chiffrage n'a plus de sens et la
# demande relève d'une étude spécifique.
COTE_MIN_MM = 1_000
COTE_MAX_MM = 50_000


class PatioIn(BaseModel):
    # Obligatoire : il identifie le patio dans le devis et la demande.
    nom: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    largeur_1_mm: float = Field(ge=COTE_MIN_MM, le=COTE_MAX_MM)
    largeur_2_mm: float = Field(ge=COTE_MIN_MM, le=COTE_MAX_MM)
    longueur_1_mm: float = Field(ge=COTE_MIN_MM, le=COTE_MAX_MM)
    longueur_2_mm: float = Field(ge=COTE_MIN_MM, le=COTE_MAX_MM)


class PatioQuoteRequest(BaseModel):
    patios: list[PatioIn] = Field(min_length=1, max_length=MAX_PATIOS)
    # La mise en place est obligatoire : elle n'est pas un choix du client et un
    # champ « mise_en_place » éventuellement envoyé est ignoré.
    # Options facultatives, chacune propre à une solution :
    # vérification annuelle (repliable, acquisition) ; intervention pour installer
    # en avril et démonter en octobre (fixe).
    verification_annuelle: bool = False
    intervention_saisonniere: bool = False


class PatioContact(BaseModel):
    prenom: str = Field(min_length=1, max_length=80)
    nom: str = Field(min_length=1, max_length=80)
    email: EmailStr
    telephone: str = Field(min_length=6, max_length=30)
    societe: str = Field(default="", max_length=120)
    message: str = Field(default="", max_length=2000)


class PatioDemande(PatioQuoteRequest):
    contact: PatioContact
