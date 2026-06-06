from pydantic import BaseModel, EmailStr, Field


class SupplierAddressCreate(BaseModel):
    type: str = Field(
        "headquarter",
        description="Type d'adresse (headquarter | delivery | production, etc.)",
    )
    street: str | None = Field(
        None, description="Rue et numéro du siège / adresse principale"
    )
    city: str | None = Field(None, description="Ville")
    zip_code: str | None = Field(None, description="Code postal")
    state: str | None = Field(None, description="Région / État")
    country_code: str | None = Field(
        None, description="Code pays ISO 3166-1 alpha-2 (ex: FR, BE)"
    )
    siret: str | None = Field(None, description="SIRET")
    intra_communal: str | None = Field(None, description="Identifiant intracommunautaire (adresse)")
    is_primary: bool = Field(
        True,
        description="Indique s'il s'agit de l'adresse principale de la société",
    )


class SupplierAccountCreate(BaseModel):
    """
    Données nécessaires à la création d'un compte fournisseur complet
    (utilisateur + profil + société + companies_users + adresse principale).
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

    # Profil utilisateur
    language_id: int = Field(
        ..., description="ID de la langue préférée (table languages)"
    )
    title: str | None = Field(None, description="Civilité / titre")
    first_name: str | None = Field(None, description="Prénom du contact")
    last_name: str | None = Field(None, description="Nom du contact")

    # Société (fournisseur) — PK = tva_intra_com
    tva_intra_com: str = Field(
        ...,
        description="Numéro de TVA intracommunautaire (clé primaire companies)",
    )
    company_name: str = Field(..., description="Raison sociale")
    registration_number: str | None = Field(
        None,
        description="Numéro d'immatriculation (SIRET / équivalent), si disponible",
    )
    company_slug: str | None = Field(
        None,
        description="Slug / identifiant lisible de la société (URL friendly), optionnel",
    )
    company_description: str | None = Field(
        None, description="Description courte de la société"
    )
    code_naf: str | None = Field(None, description="Code NAF")
    company_email: str | None = Field(None, description="Email société")
    condition_reglement: str | None = Field(None, description="Conditions de règlement")
    branche: str | None = Field(None, description="Branche")
    extrait_kbis: str | None = Field(None, description="Lien extrait Kbis")
    cgv_accepted: bool = Field(False, description="CGV acceptées")
    website: str | None = Field(None, description="Site web")
    logo: str | None = Field(None, description="URL logo")

    # Adresse principale
    address: SupplierAddressCreate | None = Field(
        None,
        description="Adresse principale de la société (si fournie, sera stockée dans addresses)",
    )


class SupplierAccount(BaseModel):
    """Compte fournisseur fraîchement créé."""

    user_id: int = Field(..., description="ID de l'utilisateur créé")
    tva_intra_com: str = Field(..., description="TVA intracommunautaire (PK société)")
    email: EmailStr = Field(..., description="Email de connexion du fournisseur")
    role_id: int | None = Field(None, description="Rôle applicatif (table roles)")
    is_active: bool = Field(..., description="Compte utilisateur actif ou non")
    is_verified: bool = Field(
        ..., description="Statut de vérification de la société (KYC, validation interne, etc.)"
    )
