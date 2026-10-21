from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import load_settings, save_settings
from ..models import SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def read_settings():
    return load_settings()


@router.put("")
async def write_settings(payload: SettingsUpdate):
    updates = payload.model_dump(exclude_none=True)
    if "minimax_base_url" in updates:
        url = str(updates["minimax_base_url"]).strip()
        if not url.startswith("https://"):
            raise HTTPException(status_code=400, detail="MiniMax 地址必须以 https:// 开头")
        updates["minimax_base_url"] = url.rstrip("/")
    if "locale" in updates and updates["locale"] not in ("zh-CN", "en-US"):
        raise HTTPException(status_code=400, detail="locale 仅支持 zh-CN 或 en-US")
    if "bill_month" in updates:
        month = str(updates["bill_month"]).strip()
        if month and (len(month) != 7 or month[4] != "-"):
            raise HTTPException(status_code=400, detail="账期月份格式应为 YYYY-MM")
        updates["bill_month"] = month
    return save_settings(updates)
