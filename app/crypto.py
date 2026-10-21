from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from .config import KEY_PATH, ensure_dirs


class DecryptError(RuntimeError):
    pass


def _fernet() -> Fernet:
    ensure_dirs()
    if not KEY_PATH.exists():
        KEY_PATH.write_bytes(Fernet.generate_key())
        try:
            KEY_PATH.chmod(0o600)
        except OSError:
            pass
    return Fernet(KEY_PATH.read_bytes().strip())


def encrypt(plaintext: str) -> str:
    if plaintext == "":
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    if token == "":
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise DecryptError("密钥无法解密，可能主密钥已变更") from exc


def mask(secret: str, keep: int = 4) -> str:
    if not secret:
        return ""
    if len(secret) <= keep * 2:
        return "*" * len(secret)
    return f"{secret[:keep]}{'*' * 6}{secret[-keep:]}"
