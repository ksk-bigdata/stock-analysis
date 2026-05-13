from fastapi import APIRouter, Query, BackgroundTasks
from data.fetcher import get_krx_stock_list, get_stock_ohlcv
from data.indicators import add_all_indicators, compute_score
import pandas as pd
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

router = APIRouter()

_screener_cache = {"data": None, "timestamp": 0, "status": "idle", "progress": 0, "total": 0}
CACHE_TTL = 1800  # 30분
_executor = ThreadPoolExecutor(max_workers=10)


def _process_one(code, name, market):
    try:
        df = get_stock_ohlcv(code, period_days=120)
        if len(df) < 60:
            return None
        df_ind = add_all_indicators(df)
        score_data = compute_score(df_ind)
        latest = df_ind.iloc[-1]
        prev_close = df_ind.iloc[-2]["close"] if len(df_ind) >= 2 else latest["close"]
        change_pct = (latest["close"] - prev_close) / prev_close * 100 if prev_close else 0
        return {
            "code": code,
            "name": name,
            "market": market,
            "close": int(latest["close"]),
            "change_pct": round(float(change_pct), 2),
            "volume": int(latest["volume"]),
            "rsi": round(float(latest["rsi"]), 2) if pd.notna(latest.get("rsi")) else None,
            "score": score_data["score"],
            "signals": score_data["signals"],
        }
    except Exception:
        return None


async def _run_screening(top_n: int = 50):
    _screener_cache["status"] = "running"
    _screener_cache["data"] = None
    _screener_cache["progress"] = 0

    stock_list = get_krx_stock_list()
    codes = stock_list["code"].tolist()[:top_n]
    names = dict(zip(stock_list["code"], stock_list["name"]))
    markets = dict(zip(stock_list["code"], stock_list["market"]))
    _screener_cache["total"] = len(codes)

    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(_executor, _process_one, code, names.get(code, code), markets.get(code, ""))
        for code in codes
    ]

    results = []
    for coro in asyncio.as_completed(tasks):
        result = await coro
        _screener_cache["progress"] += 1
        if result:
            results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)
    _screener_cache["data"] = results
    _screener_cache["timestamp"] = time.time()
    _screener_cache["status"] = "done"


@router.get("/run")
async def run_screener(background_tasks: BackgroundTasks, top_n: int = Query(50, ge=10, le=200)):
    now = time.time()
    if _screener_cache["status"] == "running":
        return {"status": "running", "message": "스크리닝 진행 중입니다."}
    if _screener_cache["data"] is not None and now - _screener_cache["timestamp"] < CACHE_TTL:
        return {"status": "done", "message": "캐시된 결과 반환", "count": len(_screener_cache["data"])}

    background_tasks.add_task(_run_screening, top_n)
    return {"status": "started", "message": f"스크리닝 시작 ({top_n}개 종목)"}


@router.get("/status")
async def screener_status():
    return {
        "status": _screener_cache["status"],
        "count": len(_screener_cache["data"]) if _screener_cache["data"] else 0,
        "progress": _screener_cache["progress"],
        "total": _screener_cache["total"],
        "cached_at": _screener_cache["timestamp"],
    }


@router.get("/results")
async def screener_results(
    min_score: int = Query(60, ge=0, le=100),
    market: str = Query("ALL"),
    limit: int = Query(50, ge=1, le=200),
):
    if _screener_cache["data"] is None:
        return {"status": _screener_cache["status"], "results": []}

    data = _screener_cache["data"]
    if market != "ALL":
        data = [d for d in data if d["market"] == market]
    data = [d for d in data if d["score"] >= min_score]

    return {
        "status": "done",
        "total": len(data),
        "results": data[:limit],
    }
