from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from data.fetcher import get_stock_ohlcv, get_stock_info, search_stocks
from data.indicators import add_all_indicators
import math

router = APIRouter()


def _clean(v):
    if v is None:
        return None
    try:
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v
    except Exception:
        return v


def _clean_record(rec: dict) -> dict:
    return {k: _clean(v) for k, v in rec.items()}


@router.get("/search")
async def search(q: str = Query(..., min_length=1)):
    results = search_stocks(q)
    return {"results": results}


@router.get("/{code}")
async def get_stock(code: str, period: int = Query(365, ge=30, le=1825)):
    try:
        df = get_stock_ohlcv(code, period)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"데이터 조회 실패: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=404, detail="데이터 없음")

    info = get_stock_info(code)
    df_with_indicators = add_all_indicators(df)

    records = [_clean_record(r) for r in df_with_indicators.to_dict(orient="records")]

    latest = df_with_indicators.iloc[-1]
    prev_close = df_with_indicators.iloc[-2]["close"] if len(df_with_indicators) >= 2 else latest["close"]
    change = latest["close"] - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0
    rsi_val = latest["rsi"]

    return {
        "info": info,
        "summary": {
            "close": int(latest["close"]),
            "change": int(change),
            "change_pct": round(float(change_pct), 2),
            "volume": int(latest["volume"]),
            "rsi": round(float(rsi_val), 2) if (rsi_val is not None and not math.isnan(float(rsi_val))) else None,
        },
        "ohlcv": records,
    }
