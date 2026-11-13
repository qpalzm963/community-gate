from __future__ import annotations

from fastapi import Depends, HTTPException, Request, WebSocket, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
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


def create_camera_token(lane_id: int, secret_key: str, expires_in_sec: int = 86400) -> str:
    s = URLSafeTimedSerializer(secret_key, salt="camera-push")
    return s.dumps({"lane_id": lane_id})


def verify_camera_token(token: str, lane_id: int, secret_key: str, max_age: int = 86400) -> bool:
    s = URLSafeTimedSerializer(secret_key, salt="camera-push")
    try:
        data = s.loads(token, max_age=max_age)
        return data.get("lane_id") == lane_id
    except (BadSignature, SignatureExpired, Exception):
        return False

