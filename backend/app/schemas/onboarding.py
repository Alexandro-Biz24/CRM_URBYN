from pydantic import BaseModel, EmailStr, Field

from app.schemas.auth import SessionUser


class OnboardingProfileUpdate(BaseModel):
    user_id: int = Field(..., description="ID utilisateur (session front)")
    email: EmailStr = Field(..., description="Email de la session (contrôle de cohérence)")
    title: str = Field(..., description="Civilité : Monsieur, Madame, M., Mme…")
    first_name: str = Field(..., min_length=1, description="Prénom")
    last_name: str = Field(..., min_length=1, description="Nom")
    mobile_phone: str | None = Field(None, description="Téléphone mobile (users.mobile_phone)")
    language_id: int = Field(1, description="Langue (user_profiles.language_id)")


class OnboardingProfileResponse(SessionUser):
    profile_completed: bool = True
