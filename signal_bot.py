import os
import requests
import pandas as pd

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "SUIUSDT"
]

INTERVAL = "15m"


def get_klines(symbol):
    url = "https://api.binance.com/api/v3/klines"

    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "limit": 200
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()

    df = pd.DataFrame(data, columns=[
        "time",
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
    ])

    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column])

    return df


def calculate_signal(df):

    df["ema20"] = df["close"].ewm(span=20).mean()
    df["ema50"] = df["close"].ewm(span=50).mean()

    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))

    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()

    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()

    df["volume_avg"] = df["volume"].rolling(20).mean()

    last = df.iloc[-1]

    price = last["close"]

    bullish = (
        last["ema20"] > last["ema50"]
        and 45 <= last["rsi"] <= 68
        and last["macd"] > last["macd_signal"]
        and last["volume"] > last["volume_avg"]
    )

    bearish = (
        last["ema20"] < last["ema50"]
        and 32 <= last["rsi"] <= 55
        and last["macd"] < last["macd_signal"]
        and last["volume"] > last["volume_avg"]
    )

    if bullish:
        return "BUY", price, last["rsi"]

    if bearish:
        return "SELL", price, last["rsi"]

    return None, price, last["rsi"]


def send_telegram(message):

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=data, timeout=15)


def main():

    send_telegram("✅ TEST MESSAGE\n\nSupunCryptoSignalBot is connected successfully!")

    signals = []

    for symbol in SYMBOLS:

        try:

            df = get_klines(symbol)

            signal, price, rsi = calculate_signal(df)

            if signal:

                signals.append(
                    f"{'🟢' if signal == 'BUY' else '🔴'} "
                    f"{signal} {symbol}\n"
                    f"Price: {price:.6f}\n"
                    f"RSI: {rsi:.1f}\n"
                    f"Timeframe: 15M"
                )

        except Exception as e:

            print(f"{symbol}: {e}")

    if signals:

        message = "📊 BINANCE CRYPTO SIGNAL\n\n"
        message += "\n\n".join(signals)

        message += (
            "\n\n⚠️ Signal only — "
            "no automatic trading."
        )

        send_telegram(message)


if __name__ == "__main__":
    main()
