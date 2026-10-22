from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_super_admin
from app.models.admin import Admin
from app.schemas.auth import AccountStatusUpdate, AdminOut, RoleUpdate

router = APIRouter(prefix="/api/admin/users", tags=["User Management"])


def _lock_user_management(db: Session) -> None:
    db.query(Admin).order_by(Admin.id).with_for_update().first()


def _get_actor(db: Session, actor_id: int) -> Admin:
    actor = (
        db.query(Admin)
        .filter(Admin.id == actor_id)
        .populate_existing()
        .first()
    )
    if not actor or not actor.is_active or actor.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super administrator access required",
        )
    return actor


def _get_target(db: Session, user_id: int) -> Admin:
    account = (
        db.query(Admin)
        .filter(Admin.id == user_id)
        .populate_existing()
        .first()
    )
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return account


def _ensure_active_super_admin_remains(db: Session, account: Admin) -> None:
    if account.role == "super_admin" and account.is_active:
        active_super_admins = db.query(Admin).filter(
            Admin.role == "super_admin",
            Admin.is_active.is_(True),
        ).count()
        if active_super_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one active Super Admin must remain",
            )


@router.get("", response_model=list[AdminOut])
def list_users(
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_super_admin),
):
    return db.query(Admin).order_by(Admin.id).all()


@router.patch("/{user_id}/role", response_model=AdminOut)
def update_user_role(
    user_id: int,
    body: RoleUpdate,
    db: Session = Depends(get_db),
    current_account: Admin = Depends(get_current_super_admin),
):
    _lock_user_management(db)
    actor = _get_actor(db, current_account.id)
    account = _get_target(db, user_id)

    if account.id == actor.id and body.role != account.role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role",
        )

    if body.role == account.role:
        return account

    if account.role == "super_admin" and body.role != "super_admin":
        _ensure_active_super_admin_remains(db, account)

    account.role = body.role
    account.auth_version += 1
    db.commit()
    db.refresh(account)
    return account


@router.patch("/{user_id}/status", response_model=AdminOut)
def update_user_status(
    user_id: int,
    body: AccountStatusUpdate,
    db: Session = Depends(get_db),
    current_account: Admin = Depends(get_current_super_admin),
):
    _lock_user_management(db)
    actor = _get_actor(db, current_account.id)
    account = _get_target(db, user_id)

    if account.id == actor.id and not body.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot suspend your own account",
        )

    if body.is_active == account.is_active:
        return account

    if not body.is_active:
        _ensure_active_super_admin_remains(db, account)

    account.is_active = body.is_active
    account.auth_version += 1
    db.commit()
    db.refresh(account)
    return account
