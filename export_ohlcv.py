import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://data-api.binance.vision/api/v3/klines"
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT",
    "TRXUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT", "NEARUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "ATOMUSDT", "FILUSDT",
    "INJUSDT", "UNIUSDT", "ETCUSDT", "AAVEUSDT", "SEIUSDT",
]
INTERVAL = "15m"
LIMIT = 1000  # Binance Spot klines maximum page size
START_UTC = "2026-10-23T00:00:00+00:00"
# End at the current UTC time so the script never requests future candles.
OUTPUT = "binance_spot_15m_oct23_to_now_2026.csv"

def to_ms(iso_text):
    return int(datetime.fromisoformat(iso_text).timestamp() * 1000)

def fetch_page(symbol, start_ms, end_ms):
    params = urllib.parse.urlencode({
        "symbol": symbol,
        "interval": INTERVAL,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": LIMIT,
    })
    url = f"{BASE_URL}?{params}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 OHLCV-history-export"},
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)

def main():
    start_ms = to_ms(START_UTC)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    # Exclude the currently forming 15-minute candle.
    end_ms = (now_ms // (15 * 60 * 1000)) * (15 * 60 * 1000) - 1

    columns = [
        "symbol", "open_time_utc", "open", "high", "low", "close",
        "volume", "close_time_utc", "quote_asset_volume",
        "number_of_trades", "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
    ]
    total_rows = 0
    with open(OUTPUT, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()

        for index, symbol in enumerate(SYMBOLS, start=1):
            print(f"[{index}/{len(SYMBOLS)}] Downloading {symbol} ...")
            cursor = start_ms
            symbol_rows = 0

            while cursor <= end_ms:
                candles = fetch_page(symbol, cursor, end_ms)
                if not candles:
                    break

                for k in candles:
                    # Kline array: open time, OHLC, volume, close time, quote volume,
                    # trade count, taker buy base, taker buy quote, ignore.
                    open_time = int(k[0])
                    close_time = int(k[6])
                    if close_time > end_ms:
                        continue
                    writer.writerow({
                        "symbol": symbol,
                        "open_time_utc": datetime.fromtimestamp(
                            open_time / 1000, timezone.utc
                        ).isoformat(),
                        "open": k[1],
                        "high": k[2],
                        "low": k[3],
                        "close": k[4],
                        "volume": k[5],
                        "close_time_utc": datetime.fromtimestamp(
                            close_time / 1000, timezone.utc
                        ).isoformat(),
                        "quote_asset_volume": k[7],
                        "number_of_trades": k[8],
                        "taker_buy_base_asset_volume": k[9],
                        "taker_buy_quote_asset_volume": k[10],
                    })
                    symbol_rows += 1

                total_rows += len(candles)
                next_cursor = int(candles[-1][0]) + 1
                if next_cursor <= cursor:
                    raise RuntimeError(f"Pagination did not advance for {symbol}")
                cursor = next_cursor
                time.sleep(0.15)

            print(f"  {symbol}: {symbol_rows} candles")

    print(f"Saved {OUTPUT}")
    print(f"Total candles downloaded: {total_rows}")

if __name__ == "__main__":
    main()
