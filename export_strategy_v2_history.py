#!/usr/bin/env python3
"""Download Binance Spot 15m klines through the latest fully closed candle (UTC)."""
import csv
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
START = datetime(2025, 11, 1, tzinfo=timezone.utc)
END_TARGET_EXCLUSIVE = datetime(2026, 11, 10, tzinfo=timezone.utc)
INTERVAL_MS = 15 * 60 * 1000
START_MS = int(START.timestamp() * 1000)
END_TARGET_MS = int(END_TARGET_EXCLUSIVE.timestamp() * 1000)
END_MS = min(END_TARGET_MS, (int(datetime.now(timezone.utc).timestamp() * 1000) // INTERVAL_MS) * INTERVAL_MS)
END_EXCLUSIVE = datetime.fromtimestamp(END_MS / 1000, timezone.utc)
BASE_URL = "https://data-api.binance.vision/api/v3/klines"
OUT = Path("strategy_v2_binance_spot_15m_2025-11-01_to_2026-11-09.csv")
FIELDS = ["symbol", "open_time", "open", "high", "low", "close", "volume", "close_time", "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume"]


def fetch(symbol, start_ms):
    params = urlencode({"symbol": symbol, "interval": "15m", "startTime": start_ms, "endTime": END_MS - 1, "limit": 1000})
    req = Request(f"{BASE_URL}?{params}", headers={"User-Agent": "StrategyV2HistoricalExport/1.0"})
    for attempt in range(9):
        try:
            with urlopen(req, timeout=35) as resp:
                return json.load(resp)
        except HTTPError as exc:
            if exc.code not in (418, 429, 500, 502, 503, 504):
                raise
            wait = min(90, 2 ** attempt + random.uniform(0, 2))
            retry_after = exc.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                wait = max(wait, int(retry_after))
            print(f"HTTP {exc.code} for {symbol}; retry in {wait:.1f}s", flush=True)
        except (URLError, TimeoutError) as exc:
            wait = min(90, 2 ** attempt + random.uniform(0, 2))
            print(f"Network issue for {symbol}: {exc}; retry in {wait:.1f}s", flush=True)
        time.sleep(wait)
    raise RuntimeError(f"Could not download {symbol} after retries")


def iso_utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def main():
    if END_MS <= START_MS:
        raise RuntimeError("No complete candles available after start date")
    print(f"Exporting completed candles through {END_EXCLUSIVE.isoformat()} (exclusive)", flush=True)
    expected_per_symbol = (END_MS - START_MS) // INTERVAL_MS
    summary = {}
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        for symbol in SYMBOLS:
            cursor = START_MS
            count = 0
            previous = None
            while cursor < END_MS:
                batch = fetch(symbol, cursor)
                if not isinstance(batch, list) or not batch:
                    raise RuntimeError(f"Missing data: {symbol} at {iso_utc(cursor)}")
                for k in batch:
                    stamp = int(k[0])
                    if stamp < cursor or stamp >= END_MS:
                        continue
                    if previous is not None and stamp != previous + INTERVAL_MS:
                        raise RuntimeError(f"Candle gap for {symbol}: {iso_utc(previous)} -> {iso_utc(stamp)}")
                    if previous is None and stamp != START_MS:
                        raise RuntimeError(f"Start gap for {symbol}: expected {iso_utc(START_MS)}, got {iso_utc(stamp)}")
                    writer.writerow([symbol, iso_utc(stamp), k[1], k[2], k[3], k[4], k[5], iso_utc(int(k[6])), k[7], k[8], k[9], k[10], k[11]])
                    previous = stamp
                    count += 1
                next_cursor = int(batch[-1][0]) + INTERVAL_MS
                if next_cursor <= cursor:
                    raise RuntimeError(f"No pagination progress for {symbol}")
                cursor = next_cursor
                if count % 10000 < len(batch):
                    print(f"{symbol}: {count}/{expected_per_symbol} candles", flush=True)
                time.sleep(0.12)
            if count != expected_per_symbol:
                raise RuntimeError(f"{symbol}: expected {expected_per_symbol} candles, received {count}")
            summary[symbol] = count
            print(f"Completed {symbol}: {count} candles", flush=True)
    Path("strategy_v2_export_summary.json").write_text(json.dumps({"period_start_utc": START.isoformat(), "period_end_exclusive_utc": END_EXCLUSIVE.isoformat(), "interval": "15m", "counts": summary, "csv": OUT.name}, indent=2), encoding="utf-8")
    print(f"SUCCESS: {OUT} ({OUT.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
