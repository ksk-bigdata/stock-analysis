import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta
from functools import lru_cache
import time

_stock_list_cache = {"data": None, "timestamp": 0}
CACHE_TTL = 3600  # 1시간


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
    end = datetime.today()
    start = end - timedelta(days=period_days)
    df = fdr.DataReader(code, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    df = df.reset_index()
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"date": "date", "open": "open", "high": "high",
                             "low": "low", "close": "close", "volume": "volume"})
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df[["date", "open", "high", "low", "close", "volume"]].dropna()


def get_stock_info(code: str) -> dict:
    df = get_krx_stock_list()
    row = df[df["code"] == code]
    if row.empty:
        return {"code": code, "name": code, "market": ""}
    return row.iloc[0].to_dict()


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
