```python
import os
import json
import time
import requests
import pandas as pd


TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "TRXUSDT",
    "DOTUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "NEARUSDT",
    "APTUSDT",
    "ARBUSDT",
    "OPUSDT",
    "ATOMUSDT",
    "FILUSDT",
    "INJUSDT",
    "UNIUSDT",
    "ETCUSDT",
    "AAVEUSDT",
    "SEIUSDT"
]

STATE_FILE = "signal_state.json"

SIGNAL_COOLDOWN = 60 * 60


# ============================================================
# BINANCE DATA
# ============================================================

def get_klines(symbol, interval, limit=250):

    url = "https://data-api.binance.vision/api/v3/klines"

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    response = requests.get(
        url,
        params=params,
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    df = pd.DataFrame(
        data,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "buy_base",
            "buy_quote",
            "ignore"
        ]
    )

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]:
        df[column] = pd.to_numeric(df[column])

    current_time_ms = int(time.time() * 1000)

    df = df[
        df["close_time"] <= current_time_ms
    ].copy()

    return df


# ============================================================
# INDICATORS
# ============================================================

def add_indicators(df):

    df["ema20"] = df["close"].ewm(
        span=20,
        adjust=False
    ).mean()

    df["ema50"] = df["close"].ewm(
        span=50,
        adjust=False
    ).mean()

    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss

    df["rsi"] = 100 - (
        100 / (1 + rs)
    )

    df["rsi"] = df["rsi"].fillna(50)

    ema12 = df["close"].ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = df["close"].ewm(
        span=26,
        adjust=False
    ).mean()

    df["macd"] = ema12 - ema26

    df["macd_signal"] = df["macd"].ewm(
        span=9,
        adjust=False
    ).mean()

    df["volume_avg"] = df["volume"].rolling(
        20
    ).mean()

    previous_close = df["close"].shift(1)

    tr1 = df["high"] - df["low"]

    tr2 = (
        df["high"] - previous_close
    ).abs()

    tr3 = (
        df["low"] - previous_close
    ).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    df["atr"] = true_range.rolling(
        14
    ).mean()

    return df


# ============================================================
# SIGNAL CALCULATION
# ============================================================

def calculate_signal(df_1h, df_15m):

    df_1h = add_indicators(df_1h)
    df_15m = add_indicators(df_15m)

    h1 = df_1h.iloc[-1]
    m15 = df_15m.iloc[-1]

    price = m15["close"]

    # -------------------------
    # BUY CONDITIONS
    # -------------------------

    bullish_h1 = (
        h1["ema20"] > h1["ema50"]
    )

    bullish_15m = (
        m15["ema20"] > m15["ema50"]
    )

    bullish_macd = (
        m15["macd"] > m15["macd_signal"]
    )

    bullish_rsi = (
        50 <= m15["rsi"] <= 68
    )

    # -------------------------
    # SELL CONDITIONS
    # -------------------------

    bearish_h1 = (
        h1["ema20"] < h1["ema50"]
    )

    bearish_15m = (
        m15["ema20"] < m15["ema50"]
    )

    bearish_macd = (
        m15["macd"] < m15["macd_signal"]
    )

    bearish_rsi = (
        32 <= m15["rsi"] <= 50
    )

    # -------------------------
    # VOLUME
    # -------------------------

    volume_ok = (
        m15["volume"]
        >= m15["volume_avg"] * 1.10
    )

    # -------------------------
    # BUY SCORE
    # -------------------------

    buy_score = 0

    if bullish_h1:
        buy_score += 25

    if bullish_15m:
        buy_score += 20

    if bullish_macd:
        buy_score += 15

    if bullish_rsi:
        buy_score += 10

    if volume_ok:
        buy_score += 10

    if h1["close"] > h1["ema20"]:
        buy_score += 10

    if m15["close"] > m15["ema20"]:
        buy_score += 10

    # -------------------------
    # SELL SCORE
    # -------------------------

    sell_score = 0

    if bearish_h1:
        sell_score += 25

    if bearish_15m:
        sell_score += 20

    if bearish_macd:
        sell_score += 15

    if bearish_rsi:
        sell_score += 10

    if volume_ok:
        sell_score += 10

    if h1["close"] < h1["ema20"]:
        sell_score += 10

    if m15["close"] < m15["ema20"]:
        sell_score += 10

    # -------------------------
    # VOLUME CHANGE
    # -------------------------

    volume_change = (
        (m15["volume"] / m15["volume_avg"]) - 1
    ) * 100

    # -------------------------
    # BUY SIGNAL
    # -------------------------

    if (
        bullish_h1
        and bullish_15m
        and bullish_macd
        and bullish_rsi
        and volume_ok
        and buy_score >= 90
    ):

        return {
            "signal": "BUY",
            "price": price,
            "rsi": m15["rsi"],
            "atr": m15["atr"],
            "score": buy_score,
            "candle_time": int(m15["open_time"]),
            "h1_trend": "BULLISH",
            "m15_trend": "BULLISH",
            "macd_trend": "BULLISH",
            "volume_change": volume_change
        }

    # -------------------------
    # SELL SIGNAL
    # -------------------------

    if (
        bearish_h1
        and bearish_15m
        and bearish_macd
        and bearish_rsi
        and volume_ok
        and sell_score >= 90
    ):

        return {
            "signal": "SELL",
            "price": price,
            "rsi": m15["rsi"],
            "atr": m15["atr"],
            "score": sell_score,
            "candle_time": int(m15["open_time"]),
            "h1_trend": "BEARISH",
            "m15_trend": "BEARISH",
            "macd_trend": "BEARISH",
            "volume_change": volume_change
        }

    return None


# ============================================================
# ENTRY / STOP LOSS / TARGETS
# ============================================================

def calculate_levels(result):

    signal = result["signal"]
    price = result["price"]
    atr = result["atr"]

    risk = atr * 1.5

    entry = price

    if signal == "BUY":

        stop_loss = price - risk

        tp1 = price + risk
        tp2 = price + risk * 2
        tp3 = price + risk * 3

    else:

        stop_loss = price + risk

        tp1 = price - risk
        tp2 = price - risk * 2
        tp3 = price - risk * 3

    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3
    }


# ============================================================
# PRICE FORMAT
# ============================================================

def format_price(price):

    if price >= 1000:
        return f"{price:,.2f}"

    if price >= 1:
        return f"{price:,.4f}"

    if price >= 0.01:
        return f"{price:.5f}"

    return f"{price:.8f}"


# ============================================================
# STATE
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    try:

        with open(
            STATE_FILE,
            "r"
        ) as file:

            return json.load(file)

    except Exception:

        return {}


def save_state(state):

    with open(
        STATE_FILE,
        "w"
    ) as file:

        json.dump(
            state,
            file,
            indent=2
        )


# ============================================================
# SIGNAL CHECK
# ============================================================

def should_send_signal(
    state,
    symbol,
    signal,
    candle_time
):

    current_time = int(time.time())

    previous = state.get(
        symbol,
        {}
    )

    if not isinstance(previous, dict):
        return True

    # --------------------------------------------------------
    # Existing active signal
    # --------------------------------------------------------

    if (
        previous.get("completed", False) is False
        and previous.get("signal") in ["BUY", "SELL"]
        and previous.get("entry") is not None
    ):

        print(
            f"{symbol}: Existing active "
            f"{previous.get('signal')} signal."
        )

        return False

    # --------------------------------------------------------
    # Same candle + same signal
    # --------------------------------------------------------

    if (
        previous.get("candle_time")
        == candle_time
        and previous.get("signal")
        == signal
    ):

        return False

    # --------------------------------------------------------
    # Cooldown
    # --------------------------------------------------------

    if (
        previous.get("signal")
        == signal
        and current_time
        - previous.get("sent_time", 0)
        < SIGNAL_COOLDOWN
    ):

        return False

    return True


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    response = requests.post(
        url,
        data=data,
        timeout=15
    )

    response.raise_for_status()


# ============================================================
# SIGNAL MESSAGE
# ============================================================

def create_signal_message(
    symbol,
    result
):

    signal = result["signal"]
    price = result["price"]
    score = result["score"]
    rsi = result["rsi"]

    volume_change = result.get(
        "volume_change",
        0
    )

    h1_trend = result.get(
        "h1_trend",
        "UNKNOWN"
    )

    m15_trend = result.get(
        "m15_trend",
        "UNKNOWN"
    )

    macd_trend = result.get(
        "macd_trend",
        "UNKNOWN"
    )

    levels = calculate_levels(result)

    entry = levels["entry"]
    stop_loss = levels["stop_loss"]
    tp1 = levels["tp1"]
    tp2 = levels["tp2"]
    tp3 = levels["tp3"]

    if signal == "BUY":

        emoji = "🟢"
        title = "BUY SIGNAL"

    else:

        emoji = "🔴"
        title = "SELL / EXIT SIGNAL"

    volume_text = (
        f"+{volume_change:.1f}% above average"
        if volume_change >= 0
        else f"{volume_change:.1f}% below average"
    )

    h1_emoji = (
        "🟢"
        if h1_trend == "BULLISH"
        else "🔴"
    )

    m15_emoji = (
        "🟢"
        if m15_trend == "BULLISH"
        else "🔴"
    )

    macd_emoji = (
        "🟢"
        if macd_trend == "BULLISH"
        else "🔴"
    )

    message = (
        f"{emoji} {title}\n\n"
        f"💎 {symbol}\n\n"
        f"💰 ENTRY\n"
        f"{format_price(entry)}\n\n"
        f"🛑 STOP LOSS\n"
        f"{format_price(stop_loss)}\n\n"
        f"🎯 TARGETS\n"
        f"TP1  {format_price(tp1)}\n"
        f"TP2  {format_price(tp2)}\n"
        f"TP3  {format_price(tp3)}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 MARKET CONFIRMATION\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"1H Trend: {h1_emoji} {h1_trend}\n"
        f"15M Trend: {m15_emoji} {m15_trend}\n\n"
        f"RSI: {rsi:.1f}\n"
        f"MACD: {macd_emoji} {macd_trend}\n"
        f"Volume: {volume_text}\n\n"
        f"⭐ Setup Score: {score}/100\n\n"
        f"📐 Risk / Reward\n"
        f"TP1 = 1:1\n"
        f"TP2 = 1:2\n"
        f"TP3 = 1:3\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"⚠️ Signal only\n"
        f"No automatic trading."
    )

    return message


# ============================================================
# MAIN
# ============================================================

def main():

    state = load_state()

    signals = []

    for symbol in SYMBOLS:

        try:

            df_1h = get_klines(
                symbol,
                "1h"
            )

            df_15m = get_klines(
                symbol,
                "15m"
            )

            result = calculate_signal(
                df_1h,
                df_15m
            )

            if result is None:

                print(
                    f"{symbol}: No signal"
                )

                continue

            signal = result["signal"]

            candle_time = result["candle_time"]

            # ------------------------------------------------
            # IMPORTANT:
            # Do not prepare or send a new signal if there
            # is already an active signal for this symbol.
            # ------------------------------------------------

            if not should_send_signal(
                state,
                symbol,
                signal,
                candle_time
            ):

                continue

            message = create_signal_message(
                symbol,
                result
            )

            levels = calculate_levels(
                result
            )

            signals.append(
                (
                    symbol,
                    signal,
                    candle_time,
                    message,
                    levels
                )
            )

            print(
                f"{symbol}: "
                f"{signal} "
                f"Score={result['score']}"
            )

        except Exception as error:

            print(
                f"{symbol}: ERROR - {error}"
            )

    # ========================================================
    # SEND NEW SIGNALS
    # ========================================================

    if signals:

        messages = []

        for (
            symbol,
            signal,
            candle_time,
            message,
            levels
        ) in signals:

            messages.append(message)

        final_message = (
            "📊 BINANCE CRYPTO SIGNALS\n\n"
            + "\n\n".join(messages)
        )

        try:

            send_telegram(
                final_message
            )

            current_time = int(
                time.time()
            )

            # ------------------------------------------------
            # Save each newly sent signal
            # ------------------------------------------------

            for (
                symbol,
                signal,
                candle_time,
                message,
                levels
            ) in signals:

                # Extra protection:
                # never overwrite an active signal.
                previous = state.get(
                    symbol,
                    {}
                )

                if (
                    isinstance(previous, dict)
                    and previous.get(
                        "completed",
                        False
                    ) is False
                    and previous.get(
                        "signal"
                    ) in ["BUY", "SELL"]
                    and previous.get(
                        "entry"
                    ) is not None
                ):

                    print(
                        f"{symbol}: Active signal "
                        f"preserved."
                    )

                    continue

                state[symbol] = {
                    "signal": signal,
                    "candle_time": candle_time,
                    "sent_time": current_time,

                    "entry": levels["entry"],
                    "stop_loss": levels["stop_loss"],

                    "tp1": levels["tp1"],
                    "tp2": levels["tp2"],
                    "tp3": levels["tp3"],

                    "tp1_hit": False,
                    "tp2_hit": False,
                    "tp3_hit": False,

                    "completed": False
                }

            save_state(state)

            print(
                "Telegram notification sent."
            )

        except Exception as error:

            print(
                f"Telegram ERROR: {error}"
            )

    else:

        print(
            "No new qualifying signals."
        )


if __name__ == "__main__":
    main()
```
