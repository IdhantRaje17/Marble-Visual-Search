from typing import Literal
from pydantic import BaseModel, EmailStr

AccountRole = Literal["super_admin", "admin", "user"]

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    account_id: int
    admin_name: str
    admin_email: str
    role: AccountRole

class AdminOut(BaseModel):
    id: int
    name: str
    email: str
    is_active: bool
    role: AccountRole

    class Config:
        from_attributes = True


class RoleUpdate(BaseModel):
    role: AccountRole


class AccountStatusUpdate(BaseModel):
    is_active: bool