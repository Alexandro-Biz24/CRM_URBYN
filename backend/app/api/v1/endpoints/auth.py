from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.auth import (
    AccountType,
    EmailCheckResponse,
    LoginRequest,
    SessionUser,
    SignupResendRequest,
    SignupResendResponse,
    SignupStartRequest,
    SignupStartResponse,
    SignupVerifyRequest,
)
from app.schemas.onboarding import OnboardingProfileResponse, OnboardingProfileUpdate
from app.schemas.onboarding_prefill import SiblingOnboardingPrefillResponse
from app.schemas.onboarding_company import (
    CompanyOption,
    EntrepriseSearchResult,
    OnboardingCompanyRequest,
    OnboardingCompanyResponse,
)
from app.services.auth import AuthError, login
from app.services.entreprise_search import search_french_companies
from app.services.onboarding import OnboardingError, complete_user_profile
from app.services.onboarding_prefill import get_sibling_onboarding_prefill
from app.services.onboarding_company import OnboardingCompanyError, complete_user_company, list_company_options
from app.services.signup import SignupError, check_email_availability, resend_verification_code, start_signup, verify_signup_code

router = APIRouter()


def _http_error(
    exc: AuthError | SignupError | OnboardingError | OnboardingCompanyError,
) -> HTTPException:
    code = exc.code
    status_code = status.HTTP_400_BAD_REQUEST
    if code in ("invalid_credentials",):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif code in ("role_mismatch",):
        status_code = status.HTTP_403_FORBIDDEN
    elif code in ("email_taken",):
        status_code = status.HTTP_409_CONFLICT
    elif code in ("email_delivery_failed",):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif code in ("email_not_verified",):
        status_code = status.HTTP_403_FORBIDDEN
    elif code in ("company_exists", "email_taken"):
        status_code = status.HTTP_409_CONFLICT
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": exc.message},
    )


@router.get(
    "/check-email",
    response_model=EmailCheckResponse,
    summary="Vérifier si un email est déjà utilisé",
)
def auth_check_email(
    email: str = Query(..., min_length=3),
    account_type: AccountType = Query(...),
    db: Session = Depends(get_db),
) -> EmailCheckResponse:
    return EmailCheckResponse(**check_email_availability(db, email, account_type))


@router.post(
    "/signup/start",
    response_model=SignupStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Créer le compte (email + mot de passe) et envoyer le code à 6 chiffres",
)
def auth_signup_start(
    payload: SignupStartRequest,
    db: Session = Depends(get_db),
) -> SignupStartResponse:
    try:
        result = start_signup(
            db,
            email=str(payload.email),
            password=payload.password,
            account_type=payload.account_type,
        )
        return SignupStartResponse(**result)
    except SignupError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/signup/verify",
    response_model=SessionUser,
    summary="Valider le code email (6 chiffres, 5 minutes)",
)
def auth_signup_verify(
    payload: SignupVerifyRequest,
    db: Session = Depends(get_db),
) -> SessionUser:
    try:
        return verify_signup_code(
            db,
            email=str(payload.email),
            code=payload.code,
            account_type=payload.account_type,
        )
    except SignupError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/signup/resend-code",
    response_model=SignupResendResponse,
    summary="Renvoyer un code de vérification",
)
def auth_signup_resend(
    payload: SignupResendRequest,
    db: Session = Depends(get_db),
) -> SignupResendResponse:
    try:
        result = resend_verification_code(
            db,
            email=str(payload.email),
            password=payload.password,
            account_type=payload.account_type,
        )
        return SignupResendResponse(**result)
    except SignupError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/onboarding/profile",
    response_model=OnboardingProfileResponse,
    summary="Compléter le profil utilisateur (étape 2 inscription)",
)
def auth_onboarding_profile(
    payload: OnboardingProfileUpdate,
    db: Session = Depends(get_db),
) -> OnboardingProfileResponse:
    """
    Met à jour `user_profiles` (title, prénom, nom, langue) et optionnellement
    `users.mobile_phone`. Le front envoie `user_id` + `email` issus de la session.
    """
    try:
        session, profile_completed = complete_user_profile(db=db, payload=payload)
        return OnboardingProfileResponse(
            **session.model_dump(),
            profile_completed=profile_completed,
        )
    except OnboardingError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/onboarding/sibling-prefill",
    response_model=SiblingOnboardingPrefillResponse,
    summary="Préremplissage profil/société depuis l'autre compte (même email)",
)
def auth_onboarding_sibling_prefill(
    user_id: int = Query(...),
    email: str = Query(..., min_length=3),
    db: Session = Depends(get_db),
) -> SiblingOnboardingPrefillResponse:
    return get_sibling_onboarding_prefill(db, user_id=user_id, email=email)


@router.get(
    "/onboarding/companies",
    response_model=list[CompanyOption],
    summary="Liste des sociétés (dropdown affiliation client / fournisseur)",
)
def auth_onboarding_companies(db: Session = Depends(get_db)) -> list[CompanyOption]:
    return [CompanyOption(**row) for row in list_company_options(db)]


@router.get(
    "/onboarding/company-search",
    response_model=list[EntrepriseSearchResult],
    summary="Recherche entreprise FR (API publique data.gouv — préremplissage)",
)
def auth_onboarding_company_search(
    q: str = Query(..., min_length=2),
) -> list[EntrepriseSearchResult]:
    return search_french_companies(q)


@router.post(
    "/onboarding/company",
    response_model=OnboardingCompanyResponse,
    summary="Rattacher ou créer la société (étape finale client / fournisseur)",
)
def auth_onboarding_company(
    payload: OnboardingCompanyRequest,
    db: Session = Depends(get_db),
) -> OnboardingCompanyResponse:
    try:
        return complete_user_company(db=db, payload=payload)
    except OnboardingCompanyError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/login",
    response_model=SessionUser,
    summary="Connexion email / mot de passe (sans JWT)",
)
def auth_login(payload: LoginRequest, db: Session = Depends(get_db)) -> SessionUser:
    try:
        return login(db=db, payload=payload)
    except AuthError as exc:
        raise _http_error(exc) from exc
