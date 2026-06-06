from pydantic import BaseModel, EmailStr, Field


class ClientAddressCreate(BaseModel):
    """Adresse du client (livraison, facturation, etc.)."""
    type: str = Field(
        "headquarter",
        description="Type d'adresse (headquarter | delivery | etc.)",
    )
    street: str | None = Field(None, description="Rue et numéro")
    city: str | None = Field(None, description="Ville")
    zip_code: str | None = Field(None, description="Code postal")
    state: str | None = Field(None, description="Région / État")
    country_code: str | None = Field(
        None,
        description="Code pays ISO 3166-1 alpha-2 (ex: FR, BE)",
    )
    siret: str | None = Field(None, description="SIRET sur le site (adresse)")
    intra_communal: str | None = Field(None, description="TVA / identifiant intracommunautaire (adresse)")
    is_primary: bool = Field(True, description="Adresse principale")


class ClientAccountCreate(BaseModel):
    """
    Données nécessaires à la création d'un compte client complet
    (utilisateur + profil + société client + liaison companies_users + adresse optionnelle).
    """

    # Utilisateur
    email: EmailStr = Field(..., description="Email de connexion, unique")
    password: str = Field(..., min_length=8, description="Mot de passe en clair")
    mobile_phone: str | None = Field(None, description="Téléphone mobile")
    fixe_phone: str | None = Field(None, description="Téléphone fixe")
    phone: str | None = Field(
        None,
        description="[Déprécié] Alias vers mobile_phone si mobile_phone absent",
    )

    # Profil utilisateur (identification)
    language_id: int = Field(
        ...,
        description="ID de la langue préférée (table languages)",
    )
    title: str | None = Field(None, description="Civilité / titre")
    first_name: str | None = Field(None, description="Prénom")
    last_name: str | None = Field(None, description="Nom")

    # Société client — PK métier = tva_intra_com
    tva_intra_com: str = Field(
        ...,
        description="Numéro de TVA intracommunautaire (clé primaire companies)",
    )
    company_name: str = Field(..., description="Raison sociale")
    registration_number: str | None = Field(
        None,
        description="Numéro d'immatriculation (SIRET, etc.), optionnel",
    )
    company_slug: str | None = Field(None, description="Slug optionnel (traduction)")
    company_description: str | None = Field(None, description="Description optionnelle (traduction)")
    code_naf: str | None = Field(None, description="Code NAF")
    company_email: str | None = Field(None, description="Email de contact société")
    condition_reglement: str | None = Field(None, description="Conditions de règlement")
    branche: str | None = Field(None, description="Branche d'activité")
    extrait_kbis: str | None = Field(None, description="Lien / référence extrait Kbis")
    cgv_accepted: bool = Field(False, description="CGV acceptées")
    website: str | None = Field(None, description="Site web")
    logo: str | None = Field(None, description="URL logo")

    # Adresse principale (optionnelle)
    address: ClientAddressCreate | None = Field(
        None,
        description="Adresse principale (livraison / facturation)",
    )


class ClientAccount(BaseModel):
    """Compte client créé."""

    user_id: int = Field(..., description="ID de l'utilisateur créé")
    tva_intra_com: str = Field(..., description="TVA intracommunautaire (PK société)")
    email: EmailStr = Field(..., description="Email de connexion")
    role_id: int | None = Field(None, description="Rôle applicatif (table roles)")
    is_active: bool = Field(..., description="Compte actif ou non")
    is_verified: bool = Field(..., description="Statut de vérification de la société")
