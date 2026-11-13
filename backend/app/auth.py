from __future__ import annotations

from fastapi import Depends, HTTPException, Request, WebSocket, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .db import SessionLocal, get_db
from .models import User

_hasher = PasswordHash.recommended()


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(pw, hashed)
    except Exception:  # noqa: BLE001
        return False


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        # 仍執行一次雜湊比對，避免以回應時間推測帳號是否存在
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    if uid:
        user = db.get(User, uid)
        if user is not None and user.is_active:
            return user
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "請先登入")


def ws_user(ws: WebSocket) -> User | None:
    uid = ws.session.get("uid") if "session" in ws.scope else None
    if not uid:
        return None
    db = SessionLocal()
    try:
        user = db.get(User, uid)
        return user if user and user.is_active else None
    finally:
        db.close()


def create_user(db: Session, username: str, password: str, display_name: str = "") -> User:
    if len(password) < 6:
        raise ValueError("密碼至少 6 個字元")
    if db.query(User).filter(User.username == username).first():
        raise ValueError("帳號已存在")
    user = User(username=username, password_hash=hash_password(password), display_name=display_name or username)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
