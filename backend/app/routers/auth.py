from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.admin import Admin
from app.schemas.auth import LoginRequest, TokenResponse, AdminOut, RegisterRequest
from app.middleware.auth import (
    verify_password, create_access_token, get_current_account, hash_password
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/register", response_model=TokenResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    # Check if email already exists
    existing = db.query(Admin).filter(Admin.email == request.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    account = Admin(
        name=request.name,
        email=request.email,
        password_hash=hash_password(request.password),
        role="user",
        is_active=True
    )
    
    db.add(account)
    db.commit()
    db.refresh(account)
    
    # Create token and return
    token = create_access_token(data={
        "sub": account.email,
        "role": account.role,
        "ver": account.auth_version,
    })
    
    return TokenResponse(
        access_token=token,
        account_id=account.id,
        admin_name=account.name,
        admin_email=account.email,
        role=account.role,
    )

@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    account = db.query(Admin).filter(Admin.email == request.email).first()

    if not account or not verify_password(request.password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated"
        )

    token = create_access_token(data={
        "sub": account.email,
        "role": account.role,
        "ver": account.auth_version,
    })

    return TokenResponse(
        access_token=token,
        account_id=account.id,
        admin_name=account.name,
        admin_email=account.email,
        role=account.role,
    )

@router.get("/me", response_model=AdminOut)
def get_me(current_account: Admin = Depends(get_current_account)):
    return current_account

@router.post("/logout")
def logout(current_admin: Admin = Depends(get_current_account)):
    # JWT is stateless — client drops the token
    return {"message": f"Goodbye, {current_admin.name}"}