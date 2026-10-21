from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..db import (
    create_account,
    delete_account,
    get_account,
    list_accounts,
    update_account,
)
from ..models import (
    AccountCreate,
    AccountUpdate,
    missing_credentials,
    validate_options,
    validate_target,
)
from ..service import service

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("")
async def list_all_accounts():
    return {"items": [account.to_public() for account in list_accounts()]}


@router.post("", status_code=201)
async def add_account(payload: AccountCreate):
    try:
        validate_target(payload.platform, payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    missing = missing_credentials(payload.platform, payload.mode, payload.credentials)
    if missing:
        raise HTTPException(
            status_code=400, detail=f"缺少必填凭据：{'、'.join(missing)}"
        )

    try:
        validate_options(payload.options)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    account = create_account(
        platform=payload.platform,
        mode=payload.mode,
        label=payload.label.strip(),
        credentials=payload.credentials,
        options=payload.options,
        enabled=payload.enabled,
    )
    service.invalidate()
    return account.to_public()


@router.put("/{account_id}")
async def edit_account(account_id: int, payload: AccountUpdate):
    account = get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    target_mode = payload.mode or account.mode
    try:
        validate_target(account.platform, target_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.credentials is not None:
        merged = dict(account.credentials)
        merged.update({k: v for k, v in payload.credentials.items() if v})
        missing = missing_credentials(account.platform, target_mode, merged)
        if missing:
            raise HTTPException(
                status_code=400, detail=f"缺少必填凭据：{'、'.join(missing)}"
            )

    if payload.options is not None:
        try:
            validate_options(payload.options)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    updated = update_account(
        account_id,
        label=payload.label.strip() if payload.label else None,
        mode=payload.mode,
        credentials=payload.credentials,
        options=payload.options,
        enabled=payload.enabled,
    )
    service.invalidate(account_id)
    return updated.to_public() if updated else {}


@router.delete("/{account_id}")
async def remove_account(account_id: int):
    if not delete_account(account_id):
        raise HTTPException(status_code=404, detail="账号不存在")
    service.invalidate(account_id)
    return {"deleted": account_id}


@router.post("/{account_id}/refresh")
async def refresh_account(account_id: int):
    """按当前筛选条件重新抓取该账号，并返回完整快照。"""
    account = get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    snapshot = await service.refresh_account(account)
    return snapshot.to_dict()


@router.post("/{account_id}/test")
async def test_account(account_id: int):
    account = get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    snapshot = await service.refresh_account(account)
    return {
        "ok": snapshot.status == "ok",
        "error": snapshot.error,
        "latency_ms": snapshot.latency_ms,
        "metrics": [metric.to_dict() for metric in snapshot.metrics],
    }
