from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import asyncio
import time

from db.client import get_supabase

router = APIRouter()

TELEGRAM_TOKEN = "8926379749:AAHT9N2eJF97FHQDz5Pu8FseT09Q9I3x8qU"
TELEGRAM_CHAT_ID = "8288748039"


class AlertRequest(BaseModel):
    code: str
    name: str
    target: float
    direction: str  # "above" | "below"


async def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})


def _load_alerts() -> dict:
    try:
        sb = get_supabase()
        result = sb.table("alerts").select("*").execute()
        return {row["code"]: row for row in result.data}
    except Exception:
        return {}


def _save_alert(alert: dict):
    sb = get_supabase()
    sb.table("alerts").upsert(alert).execute()


def _delete_alert(code: str):
    sb = get_supabase()
    sb.table("alerts").delete().eq("code", code).execute()


async def check_alerts_loop():
    from data.fetcher import get_stock_ohlcv
    await asyncio.sleep(30)
    while True:
        alerts = _load_alerts()
        triggered = []
        for code, alert in alerts.items():
            try:
                df = get_stock_ohlcv(code, period_days=5)
                if df.empty:
                    continue
                current = float(df.iloc[-1]["close"])
                target = float(alert["target"])
                direction = alert["direction"]
                hit = (direction == "above" and current >= target) or \
                      (direction == "below" and current <= target)
                if hit:
                    arrow = "📈" if direction == "above" else "📉"
                    msg = (
                        f"{arrow} <b>{alert['name']} ({code})</b> 알림\n"
                        f"현재가: <b>{int(current):,}원</b>\n"
                        f"목표가: {int(target):,}원 {'이상' if direction == 'above' else '이하'} 도달!"
                    )
                    await send_telegram(msg)
                    triggered.append(code)
            except Exception:
                continue

        for code in triggered:
            _delete_alert(code)

        await asyncio.sleep(600)


@router.get("")
async def get_alerts():
    alerts = _load_alerts()
    return {"alerts": list(alerts.values())}


@router.post("")
async def set_alert(req: AlertRequest):
    alert = {
        "code": req.code,
        "name": req.name,
        "target": req.target,
        "direction": req.direction,
        "set_at": time.time(),
    }
    try:
        _save_alert(alert)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"알림 저장 실패: {e}")

    arrow = "📈" if req.direction == "above" else "📉"
    await send_telegram(
        f"{arrow} <b>{req.name} ({req.code})</b> 알림 설정\n"
        f"목표가: <b>{int(req.target):,}원</b> {'이상' if req.direction == 'above' else '이하'}"
    )
    return {"status": "ok"}


@router.delete("/{code}")
async def delete_alert(code: str):
    _delete_alert(code)
    return {"status": "ok"}
