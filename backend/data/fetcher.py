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

    result = {}
    try:
        import httpx, re
        from bs4 import BeautifulSoup

        url = f"https://finance.naver.com/item/main.naver?code={code}"
        r = httpx.get(url, headers=_NAVER_HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        def safe_float(el_id):
            el = soup.select_one(f"em#{el_id}")
            if not el:
                return None
            txt = re.sub(r"[^\d.]", "", el.get_text(strip=True))
            try:
                v = float(txt)
                return v if v != 0 else None
            except Exception:
                return None

        result['per'] = safe_float('_per')
        result['pbr'] = safe_float('_pbr')
        result['div'] = safe_float('_dvr')

        # 시가총액: "1,660조" → 억원 단위로 저장
        mkt_el = soup.select_one("em#_market_sum")
        if mkt_el:
            raw = ""
            for node in mkt_el.contents:
                s = str(node).strip()
                if s:
                    raw = s
                    break
            raw = re.sub(r"[^\d조억]", "", raw)
            if "조" in raw:
                num = float(re.sub(r"[^\d]", "", raw.split("조")[0]) or 0)
                result['market_cap'] = int(num * 1e12)
            elif "억" in raw:
                num = float(re.sub(r"[^\d]", "", raw.split("억")[0]) or 0)
                result['market_cap'] = int(num * 1e8)

    except Exception:
        pass

    _fundamental_cache[code] = (result, now)
    return result


_smart_money_cache = {"data": None, "timestamp": 0}
SMART_MONEY_CACHE_TTL = 1800

_NAVER_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _get_candidate_codes() -> set[str]:
    """네이버 증권 거래량 상위에서 종목코드 수집 (KOSPI+KOSDAQ)"""
    import httpx, re
    from bs4 import BeautifulSoup

    codes: set[str] = set()
    for sosok in ("0", "1"):
        for page in range(1, 4):
            try:
                url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}&page={page}"
                r = httpx.get(url, headers=_NAVER_HEADERS, timeout=10)
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    m = re.search(r"code=(\d{6})", a["href"])
                    if m:
                        codes.add(m.group(1))
            except Exception:
                continue
    return codes


def _get_investor_data(code: str) -> dict | None:
    """네이버 frgn.naver에서 외국인/기관 일별 순매수 파싱"""
    import httpx, re
    from bs4 import BeautifulSoup

    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        r = httpx.get(url, headers=_NAVER_HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.find_all("table")

        # 기관/외국인 컬럼이 있는 테이블 탐색
        target_table = None
        for t in tables:
            headers = [th.get_text(strip=True) for th in t.find_all("th")]
            if "기관" in headers and "외국인" in headers:
                target_table = t
                break
        if target_table is None:
            return None
        rows = target_table.find_all("tr")

        def parse_num(s: str) -> int:
            s = s.replace(",", "").replace("+", "")
            try:
                return int(s)
            except Exception:
                return 0

        records = []
        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) >= 7 and re.match(r"\d{4}\.\d{2}\.\d{2}", cols[0]):
                records.append({"inst": parse_num(cols[5]), "foreign": parse_num(cols[6])})

        if not records:
            return None

        f_streak = i_streak = 0
        for rec in records:
            if rec["foreign"] > 0:
                f_streak += 1
            else:
                break
        for rec in records:
            if rec["inst"] > 0:
                i_streak += 1
            else:
                break

        # 최근 5일 누적 (억원)
        recent = records[:5]
        f_net = round(sum(r["foreign"] for r in recent) / 1e4, 1)  # 억원
        i_net = round(sum(r["inst"] for r in recent) / 1e4, 1)

        return {"foreign_streak": f_streak, "inst_streak": i_streak,
                "foreign_net": f_net, "inst_net": i_net}
    except Exception:
        return None


def get_smart_money_data(min_days: int = 3) -> list[dict]:
    """외국인/기관이 min_days 이상 연속 순매수 중인 종목 반환"""
    import httpx
    from concurrent.futures import ThreadPoolExecutor, as_completed

    now = time.time()
    if _smart_money_cache["data"] is not None and now - _smart_money_cache["timestamp"] < SMART_MONEY_CACHE_TTL:
        return _smart_money_cache["data"]

    stock_list = get_krx_stock_list()
    name_map = dict(zip(stock_list["code"], stock_list["name"]))
    market_map = dict(zip(stock_list["code"], stock_list["market"]))

    candidates = _get_candidate_codes()

    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {executor.submit(_get_investor_data, code): code for code in candidates}
        for future in as_completed(future_map):
            code = future_map[future]
            data = future.result()
            if data and (data["foreign_streak"] >= min_days or data["inst_streak"] >= min_days):
                results.append({
                    "code": code,
                    "name": name_map.get(code, code),
                    "market": market_map.get(code, ""),
                    **data,
                })

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
