from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import authenticate, create_user, current_user, hash_password, verify_password
from ..db import get_db
from ..models import User
from ..schemas import ChangePasswordIn, LoginIn, UserCreateIn, UserUpdateIn

router = APIRouter(prefix="/api", tags=["auth"])


def user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "is_active": u.is_active, "created_at": u.created_at}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = authenticate(db, body.username.strip(), body.password)
    if user is None:
        raise HTTPException(401, "帳號或密碼錯誤")
    request.session.clear()
    request.session["uid"] = user.id
    return user_dict(user)


@router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_dict(user)


@router.post("/auth/change-password")
def change_password(body: ChangePasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = db.get(User, user.id)
    if not verify_password(body.old_password, u.password_hash):
        raise HTTPException(400, "舊密碼錯誤")
    u.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


# ---- 帳號管理（基本版：所有登入者權限相同） ----


@router.get("/users")
def list_users(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [user_dict(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/users")
def add_user(body: UserCreateIn, _: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return user_dict(create_user(db, body.username, body.password, body.display_name))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/users/{user_id}")
def update_user(user_id: int, body: UserUpdateIn, me_: User = Depends(current_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "帳號不存在")
    if body.is_active is False and u.id == me_.id:
        raise HTTPException(400, "不能停用自己的帳號")
    if body.is_active is False:
        active = db.query(User).filter(User.is_active.is_(True), User.id != u.id).count()
        if active == 0:
            raise HTTPException(400, "至少需保留一個啟用中的帳號")
    if body.display_name is not None:
        u.display_name = body.display_name
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.password:
        u.password_hash = hash_password(body.password)
    db.commit()
    return user_dict(u)
