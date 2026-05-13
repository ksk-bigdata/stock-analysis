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


_smart_money_cache = {"data": None, "timestamp": 0}
SMART_MONEY_CACHE_TTL = 1800


def get_smart_money_data(min_days: int = 5) -> list[dict]:
    """외국인/기관이 min_days 이상 연속 순매수 중인 종목 반환"""
    now = time.time()
    if _smart_money_cache["data"] is not None and now - _smart_money_cache["timestamp"] < SMART_MONEY_CACHE_TTL:
        return _smart_money_cache["data"]

    from pykrx import stock as pykrx_stock

    # 최근 거래일 최대 10개 수집
    foreign_daily: dict[str, dict] = {}  # date -> {code: net}
    inst_daily: dict[str, dict] = {}

    current = datetime.today()
    dates_found = []
    days_checked = 0

    while len(dates_found) < 10 and days_checked < 30:
        if current.weekday() < 5:
            date_str = current.strftime("%Y%m%d")
            try:
                df_f = pykrx_stock.get_market_net_purchases_of_equities_by_ticker(
                    date_str, date_str, "ALL", "외국인"
                )
                if df_f is not None and not df_f.empty and "순매수" in df_f.columns:
                    foreign_daily[date_str] = df_f["순매수"].to_dict()
                    try:
                        df_i = pykrx_stock.get_market_net_purchases_of_equities_by_ticker(
                            date_str, date_str, "ALL", "기관합계"
                        )
                        inst_daily[date_str] = df_i["순매수"].to_dict() if (df_i is not None and not df_i.empty and "순매수" in df_i.columns) else {}
                    except Exception:
                        inst_daily[date_str] = {}
                    dates_found.append(date_str)
            except Exception:
                pass
        current -= timedelta(days=1)
        days_checked += 1

    dates_found.sort()

    # 전체 종목 코드 수집
    all_codes: set[str] = set()
    for d in foreign_daily.values():
        all_codes.update(d.keys())

    stock_list = get_krx_stock_list()
    name_map = dict(zip(stock_list["code"], stock_list["name"]))
    market_map = dict(zip(stock_list["code"], stock_list["market"]))

    results = []
    for code in all_codes:
        # 최신 날짜부터 연속 순매수 일수 계산
        f_streak = 0
        for date in reversed(dates_found):
            if foreign_daily.get(date, {}).get(code, 0) > 0:
                f_streak += 1
            else:
                break

        i_streak = 0
        for date in reversed(dates_found):
            if inst_daily.get(date, {}).get(code, 0) > 0:
                i_streak += 1
            else:
                break

        if f_streak < min_days and i_streak < min_days:
            continue

        # 최근 5일 누적 순매수금액 (억원)
        recent = dates_found[-5:]
        f_total = sum(foreign_daily.get(d, {}).get(code, 0) for d in recent)
        i_total = sum(inst_daily.get(d, {}).get(code, 0) for d in recent)

        results.append({
            "code": code,
            "name": name_map.get(code, code),
            "market": market_map.get(code, ""),
            "foreign_streak": f_streak,
            "inst_streak": i_streak,
            "foreign_net": round(f_total / 1e8, 1),   # 억원
            "inst_net": round(i_total / 1e8, 1),
        })

    # 외국인+기관 연속일수 합산 내림차순
    results.sort(key=lambda x: x["foreign_streak"] + x["inst_streak"], reverse=True)
    _smart_money_cache["data"] = results
    _smart_money_cache["timestamp"] = now
    return results


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
