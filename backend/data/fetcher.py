import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta
import time

_stock_list_cache = {"data": None, "timestamp": 0}
_ohlcv_cache = {}
_fundamental_cache = {}
CACHE_TTL = 3600
OHLCV_CACHE_TTL = 1800
FUNDAMENTAL_CACHE_TTL = 86400  # 1일


def get_krx_stock_list() -> pd.DataFrame:
    now = time.time()
    if _stock_list_cache["data"] is None or now - _stock_list_cache["timestamp"] > CACHE_TTL:
        krx = fdr.StockListing("KRX")
        krx = krx[["Code", "Name", "Market"]].dropna()
        krx.columns = ["code", "name", "market"]
        _stock_list_cache["data"] = krx
        _stock_list_cache["timestamp"] = now
    return _stock_list_cache["data"]


def search_stocks(query: str) -> list[dict]:
    df = get_krx_stock_list()
    matched = df[df["name"].str.contains(query, na=False) | df["code"].str.contains(query, na=False)]
    return matched.head(20).to_dict(orient="records")


def get_stock_ohlcv(code: str, period_days: int = 365) -> pd.DataFrame:
    cache_key = f"{code}_{period_days}"
    now = time.time()
    if cache_key in _ohlcv_cache:
        cached_df, cached_at = _ohlcv_cache[cache_key]
        if now - cached_at < OHLCV_CACHE_TTL:
            return cached_df

    end = datetime.today()
    start = end - timedelta(days=period_days)
    df = fdr.DataReader(code, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    df = df.reset_index()
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"date": "date", "open": "open", "high": "high",
                             "low": "low", "close": "close", "volume": "volume"})
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    result = df[["date", "open", "high", "low", "close", "volume"]].dropna()
    _ohlcv_cache[cache_key] = (result, now)
    return result


def get_stock_info(code: str) -> dict:
    df = get_krx_stock_list()
    row = df[df["code"] == code]
    if row.empty:
        return {"code": code, "name": code, "market": ""}
    return row.iloc[0].to_dict()


def get_stock_fundamental(code: str) -> dict:
    now = time.time()
    if code in _fundamental_cache:
        data, ts = _fundamental_cache[code]
        if now - ts < FUNDAMENTAL_CACHE_TTL:
            return data
    try:
        from pykrx import stock as pykrx_stock
        result = {}
        for days_back in range(0, 5):
            date = (datetime.today() - timedelta(days=days_back)).strftime("%Y%m%d")
            try:
                df_f = pykrx_stock.get_market_fundamental(date, date, code)
                df_c = pykrx_stock.get_market_cap(date, date, code)
                if not df_f.empty:
                    r = df_f.iloc[-1]
                    result['per'] = round(float(r['PER']), 2) if r.get('PER', 0) != 0 else None
                    result['pbr'] = round(float(r['PBR']), 2) if r.get('PBR', 0) != 0 else None
                    result['div'] = round(float(r['DIV']), 2) if r.get('DIV', 0) != 0 else None
                    result['eps'] = int(r['EPS']) if r.get('EPS', 0) != 0 else None
                if not df_c.empty:
                    r = df_c.iloc[-1]
                    result['market_cap'] = int(r['시가총액']) if r.get('시가총액', 0) != 0 else None
                if result:
                    break
            except Exception:
                continue
        _fundamental_cache[code] = (result, now)
        return result
    except Exception:
        return {}


def get_all_stocks_for_screening(period_days: int = 120) -> dict[str, pd.DataFrame]:
    stock_list = get_krx_stock_list()
    result = {}
    for _, row in stock_list.iterrows():
        try:
            df = get_stock_ohlcv(row["code"], period_days)
            if len(df) >= 60:
                result[row["code"]] = df
        except Exception:
            continue
    return result
