from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str

    VERIFICATION_CODE_TTL_SECONDS: int = 300
    APP_ENV: str = "development"

    # Expéditeur (Resend ou SMTP)
    EMAIL_FROM: str = "Urbyn <noreply@urbanize.site>"

    # Resend — https://resend.com (recommandé, simple)
    RESEND_API_KEY: str | None = None

    # SMTP classique (Gmail, Brevo, OVH…)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None
    SMTP_USE_TLS: bool = True

    ADMIN_ID: str = ""
    ADMIN_PWD: str = ""

    # Fiches techniques totem (Google Drive) — secrets uniquement côté serveur
    # JSON: {"caisson-bois-80":"<DRIVE_FILE_ID>", "sign-iz":"<DRIVE_FILE_ID>", ...}
    FICHE_TECHNIQUE_DRIVE_MAP: str = ""
    # Chemin vers le JSON du compte de service Google, OU JSON inline
    GOOGLE_SERVICE_ACCOUNT_JSON: str | None = None
    # public = liens Drive « toute personne disposant du lien » ; service_account = Drive privé
    FICHE_TECHNIQUE_DRIVE_MODE: str = "public"

    # ── Google Sheets (module NOUVEAU — écriture 2 cellules + lookup colonne) ─
    # Ne remplace rien : indépendant des fiches Drive / panier / commandes.
    # ID spreadsheet (URL : …/spreadsheets/d/<ID>/edit)
    GOOGLE_SHEETS_SPREADSHEET_ID: str = ""
    # Nom de l’onglet (ex. "Feuille 1"). Préfixé automatiquement aux adresses A1.
    GOOGLE_SHEETS_SHEET_NAME: str = ""
    # Cellule 1 = Région (dropdown) — top-left si fusionnée, ex. B10
    GOOGLE_SHEETS_WRITE_CELL_1: str = ""
    # Cellule 2 = Catégorie Terrain (dropdown) — ex. B11
    GOOGLE_SHEETS_WRITE_CELL_2: str = ""
    # Ligne d’en-têtes produits où chercher le totem sélectionné (ex. B21:P21)
    GOOGLE_SHEETS_LOOKUP_HEADER_RANGE: str = ""
    # Ligne de valeurs à lire sur la MÊME colonne (ex. B46:P46)
    GOOGLE_SHEETS_LOOKUP_VALUE_RANGE: str = ""
    # Délai (ms) après écriture pour laisser Sheets recalculer les formules
    GOOGLE_SHEETS_SETTLE_MS: int = 1500
    # Credentials dédiées Sheets (chemin JSON ou JSON inline).
    # Si vide → fallback sur GOOGLE_SERVICE_ACCOUNT_JSON.
    GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON: str | None = None

    @property
    def admin_id(self) -> str:
        return self.ADMIN_ID.strip()

    @property
    def admin_pwd(self) -> str:
        return self.ADMIN_PWD.strip()

    @property
    def admin_configured(self) -> bool:
        return bool(self.admin_id and self.admin_pwd)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_USER and self.SMTP_PASSWORD)

    @property
    def resend_configured(self) -> bool:
        return bool(self.RESEND_API_KEY and self.RESEND_API_KEY.strip())

    @property
    def email_configured(self) -> bool:
        return self.resend_configured or self.smtp_configured

    @property
    def mail_from(self) -> str:
        if self.SMTP_FROM:
            return self.SMTP_FROM
        return self.EMAIL_FROM


settings = Settings()
