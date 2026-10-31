"""Administrator account management for the community edition."""

from typing import Optional, Literal

from core.auth.local_users import LocalUserService
from core.auth.users import UserService
from core.db.engine import get_db
from core.db.models import LocalUser, UserShadow
from core.infra.responses import success_response
from api.deps import require_super_admin
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/admin/users", tags=["Admin Users"])


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
    nickname: Optional[str] = Field(None, max_length=32)
    email: Optional[str] = None
    role: Literal["member", "super_admin"] = "member"


class UpdateRoleRequest(BaseModel):
    role: Literal["member", "super_admin"]


def _serialize(shadow: UserShadow, local: Optional[LocalUser]) -> dict:
    meta = dict(shadow.extra_data or {})
    return {
        "user_id": shadow.user_id,
        "username": shadow.username,
        "email": shadow.email,
        "nickname": local.nickname if local else None,
        "status": local.status if local else "active",
        "role": "super_admin" if meta.get("role") == "super_admin" else "member",
        "created_at": shadow.created_at.isoformat() if shadow.created_at else None,
    }


@router.get("")
def list_users(_: str = Depends(require_super_admin), db: Session = Depends(get_db)):
    rows = db.query(UserShadow).order_by(UserShadow.created_at.asc()).all()
    local_by_id = {u.user_id: u for u in db.query(LocalUser).all()}
    return success_response(data=[_serialize(row, local_by_id.get(row.user_id)) for row in rows])


@router.post("")
def create_user(
    payload: CreateUserRequest,
    _: str = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    result = LocalUserService(db).create_by_admin(
        username=payload.username,
        password=payload.password,
        nickname=payload.nickname,
        email=payload.email,
        actor="admin",
    )
    if not result.ok or not result.user_id:
        from core.infra.exceptions import ValidationError
        raise ValidationError(errors=[{"message": result.message}], message=result.message)
    if payload.role == "super_admin":
        UserService(db).update_user_metadata(result.user_id, {"role": "super_admin"})
    shadow = db.query(UserShadow).filter(UserShadow.user_id == result.user_id).one()
    local = db.query(LocalUser).filter(LocalUser.user_id == result.user_id).one()
    return success_response(data=_serialize(shadow, local), message="账号已创建")


@router.patch("/{user_id}/role")
def update_role(
    user_id: str,
    payload: UpdateRoleRequest,
    _: str = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    shadow = db.query(UserShadow).filter(UserShadow.user_id == user_id).one_or_none()
    local = db.query(LocalUser).filter(LocalUser.user_id == user_id).one_or_none()
    if not shadow or not local:
        from core.infra.exceptions import ResourceNotFoundError
        raise ResourceNotFoundError(resource_type="user", resource_id=user_id)
    UserService(db).update_user_metadata(
        user_id,
        {"role": "super_admin"} if payload.role == "super_admin" else {"role": "member"},
    )
    return success_response(data=_serialize(shadow, local), message="角色已更新")
