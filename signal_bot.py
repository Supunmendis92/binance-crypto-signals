import os
import json
import time
import requests
import pandas as pd

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

STATE_FILE = "signal_state.json"
SIGNAL_COOLDOWN = 3600

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
    "SEIUSDT",
]


def get_klines(symbol, interval, limit=250):

    url = "https://data-api.binance.vision/api/v3/klines"

    response = requests.get(
        url,
        params={
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        },
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trades",
        "taker_buy_base",
        "taker_buy_quote",
        "ignore",
    ]

    df = pd.DataFrame(data, columns=columns)

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["open_time"] = pd.to_numeric(df["open_time"], errors="coerce")
    df["close_time"] = pd.to_numeric(df["close_time"], errors="coerce")

    current_time_ms = int(time.time() * 1000)

    # Remove currently open candle
    df = df[df["close_time"] <= current_time_ms].copy()

    return df


def add_indicators(df):

    df = df.copy()

    # EMA
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

    # RSI
    delta = df["close"].diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)

    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi"] = df["rsi"].fillna(50)

    # MACD
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()

    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

    # Volume
    df["volume_avg"] = df["volume"].rolling(20).mean()

    # ATR
    previous_close = df["close"].shift(1)

    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - previous_close).abs()
    tr3 = (df["low"] - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    df["atr"] = true_range.rolling(14).mean()

    return df


def calculate_signal(df_1h, df_15m):

    if len(df_1h) < 60 or len(df_15m) < 60:
        return None

    h1 = df_1h.iloc[-1]
    m15 = df_15m.iloc[-1]

    h1_bullish = h1["ema20"] > h1["ema50"]
    h1_bearish = h1["ema20"] < h1["ema50"]

    m15_bullish = m15["ema20"] > m15["ema50"]
    m15_bearish = m15["ema20"] < m15["ema50"]

    macd_bullish = m15["macd"] > m15["macd_signal"]
    macd_bearish = m15["macd"] < m15["macd_signal"]

    rsi_bullish = 50 <= m15["rsi"] <= 68
    rsi_bearish = 32 <= m15["rsi"] <= 50

    volume_ok = (
        pd.notna(m15["volume_avg"])
        and m15["volume"] >= m15["volume_avg"] * 1.10
    )

    buy_score = 0

    if h1_bullish:
        buy_score += 25

    if m15_bullish:
        buy_score += 20

    if macd_bullish:
        buy_score += 15

    if rsi_bullish:
        buy_score += 10

    if volume_ok:
        buy_score += 10

    if h1["close"] > h1["ema20"]:
        buy_score += 10

    if m15["close"] > m15["ema20"]:
        buy_score += 10

    sell_score = 0

    if h1_bearish:
        sell_score += 25

    if m15_bearish:
        sell_score += 20

    if macd_bearish:
        sell_score += 15

    if rsi_bearish:
        sell_score += 10

    if volume_ok:
        sell_score += 10

    if h1["close"] < h1["ema20"]:
        sell_score += 10

    if m15["close"] < m15["ema20"]:
        sell_score += 10

    price = float(m15["close"])
    rsi = float(m15["rsi"])
    atr = float(m15["atr"])

    if (
        h1_bullish
        and m15_bullish
        and macd_bullish
        and rsi_bullish
        and volume_ok
        and buy_score >= 90
    ):

        volume_change = (
            ((m15["volume"] / m15["volume_avg"]) - 1) * 100
            if m15["volume_avg"] > 0
            else 0
        )

        return {
            "signal": "BUY",
            "price": price,
            "rsi": rsi,
            "atr": atr,
            "score": buy_score,
            "candle_time": int(m15["close_time"]),
            "trend_1h": "BULLISH",
            "trend_15m": "BULLISH",
            "volume_change": float(volume_change),
        }

    if (
        h1_bearish
        and m15_bearish
        and macd_bearish
        and rsi_bearish
        and volume_ok
        and sell_score >= 90
    ):

        volume_change = (
            ((m15["volume"] / m15["volume_avg"]) - 1) * 100
            if m15["volume_avg"] > 0
            else 0
        )

        return {
            "signal": "SELL",
            "price": price,
            "rsi": rsi,
            "atr": atr,
            "score": sell_score,
            "candle_time": int(m15["close_time"]),
            "trend_1h": "BEARISH",
            "trend_15m": "BEARISH",
            "volume_change": float(volume_change),
        }

    return None


def calculate_levels(signal, price, atr):

    risk = atr * 1.5

    if signal == "BUY":

        stop_loss = price - risk
        tp1 = price + risk
        tp2 = price + (risk * 2)
        tp3 = price + (risk * 3)

    else:

        stop_loss = price + risk
        tp1 = price - risk
        tp2 = price - (risk * 2)
        tp3 = price - (risk * 3)

    return {
        "entry": price,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
    }


def format_price(price):

    if price >= 1000:
        return f"{price:,.2f}"

    if price >= 1:
        return f"{price:.4f}"

    if price >= 0.1:
        return f"{price:.5f}"

    if price >= 0.01:
        return f"{price:.6f}"

    return f"{price:.8f}"


def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    try:

        with open(STATE_FILE, "r") as file:
            return json.load(file)

    except Exception:

        return {}


def save_state(state):

    with open(STATE_FILE, "w") as file:

        json.dump(
            state,
            file,
            indent=2
        )


def should_send_signal(
    state,
    symbol,
    signal,
    candle_time,
    current_time
):

    previous = state.get(symbol, {})

    if not isinstance(previous, dict):
        return True

    # IMPORTANT:
    # Never overwrite an active signal that is still being monitored.

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

    # Same candle + same direction
    if (
        previous.get("candle_time") == candle_time
        and previous.get("signal") == signal
    ):

        return False

    # Same signal within cooldown
    if (
        previous.get("signal") == signal
        and current_time - previous.get("sent_time", 0)
        < SIGNAL_COOLDOWN
    ):

        return False

    return True


def send_telegram(message):

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
        },
        timeout=15,
    )

    response.raise_for_status()


def create_signal_message(symbol, signal):

    direction = signal["signal"]

    levels = calculate_levels(
        direction,
        signal["price"],
        signal["atr"]
    )

    entry = levels["entry"]
    stop_loss = levels["stop_loss"]
    tp1 = levels["tp1"]
    tp2 = levels["tp2"]
    tp3 = levels["tp3"]

    risk = abs(entry - stop_loss)

    reward = abs(tp3 - entry)

    rr = reward / risk if risk > 0 else 0

    message = f"""
🚨 BINANCE SIGNAL

📊 Pair: {symbol}
📈 Signal: {direction}

💰 Entry: {format_price(entry)}
🛑 Stop Loss: {format_price(stop_loss)}

🎯 TP1: {format_price(tp1)}
🎯 TP2: {format_price(tp2)}
🎯 TP3: {format_price(tp3)}

📊 1H Trend: {signal["trend_1h"]}
📊 15M Trend: {signal["trend_15m"]}

RSI: {signal["rsi"]:.2f}
MACD: Confirmed
Volume: +{signal["volume_change"]:.1f}%

⭐ Score: {signal["score"]}/100
⚖️ Risk/Reward: 1:{rr:.1f}

⚠️ Signal only — no automatic trading.
"""

    return message.strip(), levels


def main():

    state = load_state()

    current_time = int(time.time())

    new_signals = []

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

            df_1h = add_indicators(df_1h)
            df_15m = add_indicators(df_15m)

            signal = calculate_signal(
                df_1h,
                df_15m
            )

            if signal is None:

                print(
                    f"{symbol}: No signal"
                )

                continue

            if not should_send_signal(
                state,
                symbol,
                signal["signal"],
                signal["candle_time"],
                current_time
            ):

                continue

            message, levels = create_signal_message(
                symbol,
                signal
            )

            new_signals.append(
                {
                    "symbol": symbol,
                    "signal": signal,
                    "levels": levels,
                    "message": message,
                }
            )

        except Exception as error:

            print(
                f"{symbol}: ERROR - {error}"
            )

    if not new_signals:

        print(
            "No new qualifying signals."
        )

        return

    # Send all new signals
    for item in new_signals:

        symbol = item["symbol"]
        signal = item["signal"]
        levels = item["levels"]
        message = item["message"]

        try:

            send_telegram(message)

            # Defensive check:
            # Do not overwrite an active signal.

            existing = state.get(symbol, {})

            if (
                isinstance(existing, dict)
                and existing.get("completed", False) is False
                and existing.get("entry") is not None
            ):

                print(
                    f"{symbol}: Existing active signal "
                    f"detected. State not overwritten."
                )

                continue

            state[symbol] = {
                "signal": signal["signal"],
                "candle_time": signal["candle_time"],
                "sent_time": current_time,

                "entry": levels["entry"],
                "stop_loss": levels["stop_loss"],
                "tp1": levels["tp1"],
                "tp2": levels["tp2"],
                "tp3": levels["tp3"],

                "tp1_hit": False,
                "tp2_hit": False,
                "tp3_hit": False,

                "completed": False,
            }

            print(
                f"{symbol}: {signal['signal']} signal sent."
            )

        except Exception as error:

            print(
                f"{symbol}: Telegram/state ERROR - {error}"
            )

    save_state(state)

    print(
        f"New signals sent: {len(new_signals)}"
    )


if __name__ == "__main__":
    main()
