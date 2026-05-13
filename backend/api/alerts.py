from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import asyncio
import time

router = APIRouter()

TELEGRAM_TOKEN = "8926379749:AAHT9N2eJF97FHQDz5Pu8FseT09Q9I3x8qU"
TELEGRAM_CHAT_ID = "8288748039"

# {code: {name, target, direction, set_at}}
_alerts: dict = {}


class AlertRequest(BaseModel):
    code: str
    name: str
    target: float
    direction: str  # "above" | "below"


async def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})


async def check_alerts_loop():
    from data.fetcher import get_stock_ohlcv
    await asyncio.sleep(30)  # 서버 시작 후 30초 대기
    while True:
        triggered = []
        for code, alert in list(_alerts.items()):
            try:
                df = get_stock_ohlcv(code, period_days=5)
                if df.empty:
                    continue
                current = float(df.iloc[-1]["close"])
                target = alert["target"]
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
            _alerts.pop(code, None)

        await asyncio.sleep(600)  # 10분마다 체크


@router.get("")
async def get_alerts():
    return {"alerts": list(_alerts.values())}


@router.post("")
async def set_alert(req: AlertRequest):
    _alerts[req.code] = {
        "code": req.code,
        "name": req.name,
        "target": req.target,
        "direction": req.direction,
        "set_at": time.time(),
    }
    arrow = "📈" if req.direction == "above" else "📉"
    await send_telegram(
        f"{arrow} <b>{req.name} ({req.code})</b> 알림 설정\n"
        f"목표가: <b>{int(req.target):,}원</b> {'이상' if req.direction == 'above' else '이하'}"
    )
    return {"status": "ok"}


@router.delete("/{code}")
async def delete_alert(code: str):
    _alerts.pop(code, None)
    return {"status": "ok"}
