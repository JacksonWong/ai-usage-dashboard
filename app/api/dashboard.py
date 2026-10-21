from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import list_accounts
from ..service import service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard(refresh: int = Query(default=0, ge=0, le=1)):
    snapshots = await service.snapshots(force=bool(refresh))
    accounts = {account.id: account for account in list_accounts()}

    items = []
    for snapshot in snapshots:
        payload = snapshot.to_dict()
        account = accounts.get(snapshot.account_id)
        payload["enabled"] = account.enabled if account else True
        payload["credential_mask"] = (
            account.to_public()["credential_mask"] if account else {}
        )
        items.append(payload)

    ok = sum(1 for item in items if item["status"] == "ok")
    last_update = max((item["fetched_at"] for item in items), default="")

    return {
        "items": items,
        "summary": {
            "total": len(items),
            "ok": ok,
            "failed": len(items) - ok,
            "last_update": last_update,
        },
    }
