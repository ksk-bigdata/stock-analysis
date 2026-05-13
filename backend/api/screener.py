from fastapi import APIRouter, Query, BackgroundTasks
from data.fetcher import get_krx_stock_list, get_stock_ohlcv, get_smart_money_data
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


_smart_money_task = {"status": "idle"}


async def _run_smart_money():
    _smart_money_task["status"] = "running"
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as ex:
            await loop.run_in_executor(ex, get_smart_money_data)
        _smart_money_task["status"] = "done"
    except Exception as e:
        _smart_money_task["status"] = f"error: {e}"


@router.get("/smart-money/run")
async def smart_money_run(background_tasks: BackgroundTasks):
    if _smart_money_task["status"] == "running":
        return {"status": "running"}
    background_tasks.add_task(_run_smart_money)
    return {"status": "started"}


@router.get("/smart-money/status")
async def smart_money_status():
    return {"status": _smart_money_task["status"]}


@router.get("/smart-money/results")
async def smart_money_results(
    type: str = Query("all"),   # "foreign" | "inst" | "both" | "all"
    min_days: int = Query(5),
):
    from data.fetcher import _smart_money_cache
    if _smart_money_cache["data"] is None:
        return {"status": _smart_money_task["status"], "results": []}

    data = _smart_money_cache["data"]

    if type == "foreign":
        data = [d for d in data if d["foreign_streak"] >= min_days]
    elif type == "inst":
        data = [d for d in data if d["inst_streak"] >= min_days]
    elif type == "both":
        data = [d for d in data if d["foreign_streak"] >= min_days and d["inst_streak"] >= min_days]

    return {"status": "done", "total": len(data), "results": data}


# ── MA60 돌파 스크리너 ────────────────────────────────
_ma60_cache = {"data": None, "timestamp": 0, "status": "idle", "progress": 0, "total": 0}
_ma60_executor = ThreadPoolExecutor(max_workers=10)


def _check_ma60(code, name, market):
    try:
        df = get_stock_ohlcv(code, period_days=100)
        if len(df) < 65:
            return None
        df_ind = add_all_indicators(df)

        # 최신부터 연속으로 close > ma60인 날 수
        streak = 0
        for i in range(len(df_ind) - 1, -1, -1):
            row = df_ind.iloc[i]
            if pd.notna(row["ma60"]) and row["close"] > row["ma60"]:
                streak += 1
            else:
                break

        if streak < 2:
            return None

        latest = df_ind.iloc[-1]
        prev   = df_ind.iloc[-2]

        # 돌파 여부: 현재 streak 시작 직전 날이 ma60 이하였으면 신규 돌파
        cross_idx = len(df_ind) - 1 - streak
        is_new_cross = (cross_idx >= 0 and
                        pd.notna(df_ind.iloc[cross_idx]["ma60"]) and
                        df_ind.iloc[cross_idx]["close"] <= df_ind.iloc[cross_idx]["ma60"])

        # ma60 대비 현재 괴리율
        gap_pct = round((float(latest["close"]) - float(latest["ma60"])) / float(latest["ma60"]) * 100, 2)

        change_pct = round((float(latest["close"]) - float(prev["close"])) / float(prev["close"]) * 100, 2)

        return {
            "code": code,
            "name": name,
            "market": market,
            "close": int(latest["close"]),
            "ma60": round(float(latest["ma60"]), 0),
            "gap_pct": gap_pct,
            "streak": streak,
            "is_new_cross": is_new_cross,
            "change_pct": change_pct,
            "volume": int(latest["volume"]),
        }
    except Exception:
        return None


async def _run_ma60_screener(top_n: int):
    _ma60_cache["status"] = "running"
    _ma60_cache["data"] = None
    _ma60_cache["progress"] = 0

    stock_list = get_krx_stock_list()
    rows = stock_list.head(top_n).to_dict("records")
    _ma60_cache["total"] = len(rows)

    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(_ma60_executor, _check_ma60, r["code"], r["name"], r["market"])
        for r in rows
    ]

    results = []
    for coro in asyncio.as_completed(tasks):
        result = await coro
        _ma60_cache["progress"] += 1
        if result:
            results.append(result)

    # 신규 돌파 우선, 그 다음 streak 길이 순
    results.sort(key=lambda x: (x["is_new_cross"], x["streak"]), reverse=True)
    _ma60_cache["data"] = results
    _ma60_cache["status"] = "done"


@router.get("/ma60/run")
async def ma60_run(background_tasks: BackgroundTasks, top_n: int = Query(300, ge=50, le=1000)):
    if _ma60_cache["status"] == "running":
        return {"status": "running"}
    background_tasks.add_task(_run_ma60_screener, top_n)
    return {"status": "started"}


@router.get("/ma60/status")
async def ma60_status():
    return {
        "status": _ma60_cache["status"],
        "progress": _ma60_cache["progress"],
        "total": _ma60_cache["total"],
        "count": len(_ma60_cache["data"]) if _ma60_cache["data"] else 0,
    }


@router.get("/ma60/results")
async def ma60_results(
    filter: str = Query("all"),   # "all" | "new_cross" (신규 돌파만)
    market: str = Query("ALL"),
    min_streak: int = Query(2),
):
    if _ma60_cache["data"] is None:
        return {"status": _ma60_cache["status"], "results": []}

    data = _ma60_cache["data"]
    if market != "ALL":
        data = [d for d in data if d["market"] == market]
    if filter == "new_cross":
        data = [d for d in data if d["is_new_cross"]]
    data = [d for d in data if d["streak"] >= min_streak]

    return {"status": "done", "total": len(data), "results": data}
