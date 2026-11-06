from __future__ import annotations

import getpass
import os
import sys

from sqlalchemy import select

from apps.api.asdos_api.database import Base, SessionLocal, engine
from apps.api.asdos_api import models  # noqa: F401
from apps.api.asdos_api.models import User
from apps.api.asdos_api.security import hash_password


def main() -> int:
    username = input("Username dosen: ").strip()
    display_name = input("Nama tampilan: ").strip()
    password = getpass.getpass("Kata sandi (minimal 12 karakter): ")
    confirmation = getpass.getpass("Ulangi kata sandi: ")
    if not username or not display_name or password != confirmation:
        print("Input tidak lengkap atau kata sandi tidak cocok.", file=sys.stderr)
        return 2
    try:
        encoded = hash_password(password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.username == username)):
            print("Username sudah terdaftar.", file=sys.stderr)
            return 2
        user = User(username=username, display_name=display_name, password_hash=encoded, role="owner")
        db.add(user)
        db.commit()
        print(f"Akun dosen '{username}' dibuat.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
