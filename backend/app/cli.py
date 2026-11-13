"""命令列工具：gate create-admin / serve / backup / reset-password。"""
from __future__ import annotations

import argparse
import getpass
import shutil
import sys
from datetime import datetime
from pathlib import Path

import uvicorn

from .auth import create_user, hash_password
from .config import get_config
from .db import SessionLocal, init_engine
from .migrate import upgrade_db
from .models import User


def _prompt_password(confirm: bool = True) -> str:
    pw = getpass.getpass("請輸入密碼（至少 6 碼）：")
    if len(pw) < 6:
        raise ValueError("密碼至少需要 6 個字元")
    if confirm:
        pw2 = getpass.getpass("再次確認密碼：")
        if pw != pw2:
            raise ValueError("兩次輸入的密碼不一致")
    return pw


def cmd_create_admin(args: argparse.Namespace) -> int:
    init_engine()
    upgrade_db()
    username = (args.username or input("帳號名稱 [admin]：") or "admin").strip()
    display_name = args.display_name or input(f"顯示名稱 [{username}]：").strip() or username
    password = args.password or _prompt_password(confirm=True)
    db = SessionLocal()
    try:
        user = create_user(db, username, password, display_name)
    except ValueError as e:
        print(f"建立失敗：{e}", file=sys.stderr)
        return 1
    finally:
        db.close()
    print(f"已建立帳號：{user.username}（{user.display_name}）")
    return 0


def cmd_reset_password(args: argparse.Namespace) -> int:
    init_engine()
    upgrade_db()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if user is None:
            print(f"找不到帳號：{args.username}", file=sys.stderr)
            return 1
        pw = args.password or _prompt_password(confirm=True)
        user.password_hash = hash_password(pw)
        db.commit()
        print(f"已重設 {user.username} 的密碼")
        return 0
    except ValueError as e:
        print(f"失敗：{e}", file=sys.stderr)
        return 1
    finally:
        db.close()


def cmd_backup(args: argparse.Namespace) -> int:
    cfg = get_config()
    if not cfg.db_path.exists():
        print(f"找不到資料庫：{cfg.db_path}", file=sys.stderr)
        return 1
    out = Path(args.output) if args.output else cfg.data_dir / f"backup_{datetime.now():%Y%m%d_%H%M%S}.db"
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cfg.db_path, out)
    print(f"已備份資料庫至：{out}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    cfg = get_config()
    host = args.host or cfg.host
    port = args.port or cfg.port
    init_engine()
    upgrade_db()
    db = SessionLocal()
    try:
        has_user = db.query(User).first() is not None
    finally:
        db.close()
    if not has_user:
        print("提醒：目前尚無任何操作帳號，請先執行 `uv run gate create-admin` 建立管理員帳號。", file=sys.stderr)

    ssl_certfile = args.ssl_cert
    ssl_keyfile = args.ssl_key
    if args.ssl and (not ssl_certfile or not ssl_keyfile):
        from .ssl_cert import ensure_self_signed_cert
        cert_p, key_p = ensure_self_signed_cert(cfg.data_dir)
        ssl_certfile = str(cert_p)
        ssl_keyfile = str(key_p)
        print(f"已啟用 HTTPS（使用本機自我簽署憑證：{cert_p}）")

    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gate", description="社區出入管理系統 CLI")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("create-admin", help="建立管理員／操作員帳號")
    c.add_argument("-u", "--username", help="帳號名稱")
    c.add_argument("-p", "--password", help="密碼（省略時互動輸入）")
    c.add_argument("-n", "--display-name", help="顯示名稱")
    c.set_defaults(func=cmd_create_admin)

    r = sub.add_parser("reset-password", help="重設帳號密碼")
    r.add_argument("username", help="帳號名稱")
    r.add_argument("-p", "--password", help="新密碼（省略時互動輸入）")
    r.set_defaults(func=cmd_reset_password)

    b = sub.add_parser("backup", help="備份 SQLite 資料庫")
    b.add_argument("-o", "--output", help="備份輸出檔案路徑")
    b.set_defaults(func=cmd_backup)

    s = sub.add_parser("serve", help="啟動單機版伺服器")
    s.add_argument("--host", help="監聽位址（預設 127.0.0.1，手機連線建議 0.0.0.0）")
    s.add_argument("--port", type=int, help="監聽埠號（預設 8000）")
    s.add_argument("--ssl", action="store_true", help="啟用 HTTPS（手機瀏覽器相機權限必備）")
    s.add_argument("--ssl-cert", help="自訂 SSL 憑證路徑")
    s.add_argument("--ssl-key", help="自訂 SSL 私鑰路徑")
    s.add_argument("--reload", action="store_true", help="開發模式自動重載")
    s.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
