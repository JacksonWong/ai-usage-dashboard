from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from custom_components.llm_balance.core.models import Account

from .config import DB_PATH, ensure_dirs
from .crypto import decrypt, encrypt

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,
    mode            TEXT NOT NULL,
    label           TEXT NOT NULL,
    credentials_enc TEXT NOT NULL DEFAULT '',
    options_json    TEXT NOT NULL DEFAULT '{}',
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    last_ok_at      TEXT,
    last_error      TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    try:
        Path(DB_PATH).chmod(0o600)
    except OSError:
        pass


def _row_to_account(row: sqlite3.Row) -> Account:
    try:
        options = json.loads(row["options_json"] or "{}")
        if not isinstance(options, dict):
            options = {}
    except json.JSONDecodeError:
        options = {}
    return Account(
        id=row["id"],
        platform=row["platform"],
        mode=row["mode"],
        label=row["label"],
        credentials=_decrypt_credentials(row["credentials_enc"]),
        options=options,
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_ok_at=row["last_ok_at"],
        last_error=row["last_error"],
    )


def _encrypt_credentials(credentials: dict[str, str]) -> str:
    return json.dumps(
        {key: encrypt(value) for key, value in credentials.items() if value},
        ensure_ascii=False,
    )


def _decrypt_credentials(payload: str) -> dict[str, str]:
    try:
        raw = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        try:
            result[key] = decrypt(value)
        except Exception:  # noqa: BLE001 - 主密钥变更时降级为空
            result[key] = ""
    return result


def list_accounts(enabled_only: bool = False) -> list[Account]:
    conn = _connect()
    try:
        sql = "SELECT * FROM accounts"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY platform, mode, id"
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()
    return [_row_to_account(row) for row in rows]


def get_account(account_id: int) -> Account | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    finally:
        conn.close()
    return _row_to_account(row) if row else None


def create_account(
    platform: str,
    mode: str,
    label: str,
    credentials: dict[str, str],
    options: dict[str, Any] | None = None,
    enabled: bool = True,
) -> Account:
    now = _now()
    conn = _connect()
    try:
        cursor = conn.execute(
            "INSERT INTO accounts (platform, mode, label, credentials_enc, options_json,"
            " enabled, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                platform,
                mode,
                label,
                _encrypt_credentials(credentials),
                json.dumps(options or {}, ensure_ascii=False),
                1 if enabled else 0,
                now,
                now,
            ),
        )
        conn.commit()
        account_id = int(cursor.lastrowid or 0)
    finally:
        conn.close()
    account = get_account(account_id)
    assert account is not None
    return account


def update_account(
    account_id: int,
    *,
    label: str | None = None,
    mode: str | None = None,
    credentials: dict[str, str] | None = None,
    options: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> Account | None:
    existing = get_account(account_id)
    if existing is None:
        return None

    merged_credentials = dict(existing.credentials)
    if credentials is not None:
        for key, value in credentials.items():
            if value:
                merged_credentials[key] = value
    merged_options = dict(existing.options)
    if options is not None:
        merged_options.update(options)

    conn = _connect()
    try:
        conn.execute(
            "UPDATE accounts SET mode=?, label=?, credentials_enc=?, options_json=?,"
            " enabled=?, updated_at=? WHERE id=?",
            (
                mode or existing.mode,
                label if label is not None else existing.label,
                _encrypt_credentials(merged_credentials),
                json.dumps(merged_options, ensure_ascii=False),
                (1 if enabled else 0) if enabled is not None else (1 if existing.enabled else 0),
                _now(),
                account_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_account(account_id)


def delete_account(account_id: int) -> bool:
    conn = _connect()
    try:
        cursor = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def record_result(account_id: int, ok: bool, error: str | None) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE accounts SET last_ok_at = ?, last_error = ? WHERE id = ?",
            (_now() if ok else None, None if ok else error, account_id),
        )
        conn.commit()
    finally:
        conn.close()
