import pandas as pd
import numpy as np


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).round(2)


def calc_macd(close: pd.Series, fast=12, slow=26, signal=9) -> pd.DataFrame:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return pd.DataFrame({"macd": macd.round(2), "signal": signal_line.round(2), "histogram": histogram.round(2)})


def calc_bollinger(close: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    ma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = ma + std_dev * std
    lower = ma - std_dev * std
    return pd.DataFrame({"bb_upper": upper.round(2), "bb_mid": ma.round(2), "bb_lower": lower.round(2)})


def calc_moving_averages(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({
        "ma5": close.rolling(5).mean().round(2),
        "ma20": close.rolling(20).mean().round(2),
        "ma60": close.rolling(60).mean().round(2),
        "ma120": close.rolling(120).mean().round(2),
    })


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["close"].astype(float)

    df["rsi"] = calc_rsi(close)

    macd_df = calc_macd(close)
    df = pd.concat([df, macd_df], axis=1)

    bb_df = calc_bollinger(close)
    df = pd.concat([df, bb_df], axis=1)

    ma_df = calc_moving_averages(close)
    df = pd.concat([df, ma_df], axis=1)

    df["volume_ma20"] = df["volume"].astype(float).rolling(20).mean().round(0)

    return df


def compute_score(df: pd.DataFrame) -> dict:
    """기술적 분석 기반 종목 점수 계산 (0~100점)"""
    if df.empty or len(df) < 30:
        return {"score": 0, "signals": []}

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else latest
    signals = []
    score = 50  # 기본 점수

    # RSI 분석
    rsi = latest.get("rsi")
    if pd.notna(rsi):
        if 30 <= rsi <= 50:
            score += 15
            signals.append({"type": "buy", "label": f"RSI 매수구간 ({rsi:.1f})"})
        elif rsi < 30:
            score += 10
            signals.append({"type": "buy", "label": f"RSI 과매도 ({rsi:.1f})"})
        elif rsi > 70:
            score -= 15
            signals.append({"type": "sell", "label": f"RSI 과매수 ({rsi:.1f})"})

    # MACD 골든크로스
    macd_cur = latest.get("macd")
    signal_cur = latest.get("signal")
    macd_prev = prev.get("macd")
    signal_prev = prev.get("signal")
    if all(pd.notna(v) for v in [macd_cur, signal_cur, macd_prev, signal_prev]):
        if macd_prev < signal_prev and macd_cur >= signal_cur:
            score += 20
            signals.append({"type": "buy", "label": "MACD 골든크로스"})
        elif macd_prev > signal_prev and macd_cur <= signal_cur:
            score -= 20
            signals.append({"type": "sell", "label": "MACD 데드크로스"})
        elif macd_cur > signal_cur:
            score += 5
            signals.append({"type": "buy", "label": "MACD 상승세"})

    # 볼린저밴드
    close = latest.get("close")
    bb_lower = latest.get("bb_lower")
    bb_upper = latest.get("bb_upper")
    bb_mid = latest.get("bb_mid")
    if all(pd.notna(v) for v in [close, bb_lower, bb_upper, bb_mid]):
        if close <= bb_lower:
            score += 15
            signals.append({"type": "buy", "label": "볼린저밴드 하단 지지"})
        elif close >= bb_upper:
            score -= 15
            signals.append({"type": "sell", "label": "볼린저밴드 상단 저항"})
        elif close > bb_mid:
            score += 5
            signals.append({"type": "neutral", "label": "볼린저밴드 중심 상회"})

    # 이동평균선 정배열
    ma5 = latest.get("ma5")
    ma20 = latest.get("ma20")
    ma60 = latest.get("ma60")
    if all(pd.notna(v) for v in [close, ma5, ma20, ma60]):
        if close > ma5 > ma20 > ma60:
            score += 15
            signals.append({"type": "buy", "label": "이동평균 정배열"})
        elif close < ma5 < ma20 < ma60:
            score -= 15
            signals.append({"type": "sell", "label": "이동평균 역배열"})

    # 거래량 급증
    vol = latest.get("volume")
    vol_ma = latest.get("volume_ma20")
    if pd.notna(vol) and pd.notna(vol_ma) and vol_ma > 0:
        vol_ratio = vol / vol_ma
        if vol_ratio >= 2.0:
            score += 10
            signals.append({"type": "buy", "label": f"거래량 급증 ({vol_ratio:.1f}배)"})

    score = max(0, min(100, score))
    return {"score": int(score), "signals": signals}
