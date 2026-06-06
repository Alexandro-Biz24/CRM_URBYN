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
    EMAIL_FROM: str = "Urbyn <noreply@urbyn.fr>"

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
