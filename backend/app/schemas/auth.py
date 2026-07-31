from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class AccountType(str, Enum):
    buyer = "buyer"
    partner = "partner"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)
    account_type: AccountType = Field(
        ...,
        description="buyer → rôle Client, partner → rôle Fournisseur",
    )


class SignupStartRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    account_type: AccountType


class SignupVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    account_type: AccountType


class SignupResendRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)
    account_type: AccountType


class SessionUser(BaseModel):
    user_id: int
    email: EmailStr
    role_id: int | None
    role_name: str | None
    account_type: AccountType
    first_name: str | None = None
    last_name: str | None = None
    mobile_phone: str | None = None
    fixe_phone: str | None = None
    is_active: bool
    email_verified: bool = False


class EmailCheckResponse(BaseModel):
    exists: bool
    available: bool
    email_verified: bool | None = None


class SignupStartResponse(BaseModel):
    user_id: int
    email: EmailStr
    expires_in_seconds: int
    message: str


class SignupResendResponse(BaseModel):
    expires_in_seconds: int
    message: str


class PasswordResetStartRequest(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    account_type: AccountType


class PasswordResetStartResponse(BaseModel):
    email: EmailStr
    expires_in_seconds: int
    message: str


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    account_type: AccountType
    new_password: str = Field(..., min_length=8)


class PasswordResetConfirmResponse(BaseModel):
    message: str
