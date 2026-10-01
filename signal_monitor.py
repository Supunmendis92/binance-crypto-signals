import os
import json
import time
import requests

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

STATE_FILE = "signal_state.json"


def get_price(symbol):
    url = "https://data-api.binance.vision/api/v3/ticker/price"

    response = requests.get(
        url,
        params={"symbol": symbol},
        timeout=15
    )

    response.raise_for_status()

    return float(response.json()["price"])


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


def send_telegram(message):
    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_TOKEN
        + "/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=15
    )

    response.raise_for_status()


def format_price(price):
    if price >= 1000:
        return f"{price:,.2f}"

    if price >= 1:
        return f"{price:,.4f}"

    if price >= 0.01:
        return f"{price:.5f}"

    return f"{price:.8f}"


def main():

    state = load_state()

    changed = False

    for symbol, data in list(state.items()):

        # Ignore non-signal state entries
        if symbol == "last_status_time":
            continue

        if not isinstance(data, dict):
            continue

        signal = data.get("signal")

        if signal not in ["BUY", "SELL"]:
            continue

        if data.get("completed", False):
            continue

        entry = data.get("entry")
        stop_loss = data.get("stop_loss")
        tp1 = data.get("tp1")
        tp2 = data.get("tp2")
        tp3 = data.get("tp3")

        if None in [
            entry,
            stop_loss,
            tp1,
            tp2,
            tp3
        ]:
            continue

        try:
            price = get_price(symbol)

        except Exception as error:
            print(
                f"{symbol}: ERROR - {error}"
            )
            continue

        # BUY signal monitoring
        if signal == "BUY":

            if (
                not data.get("tp1_hit", False)
                and price >= tp1
            ):

                send_telegram(
                    f"🎯 TP1 REACHED\n\n"
                    f"💎 {symbol}\n\n"
                    f"Entry: {format_price(entry)}\n"
                    f"Current: {format_price(price)}\n\n"
                    f"TP1: {format_price(tp1)}"
                )

                data["tp1_hit"] = True
                changed = True

            if (
                data.get("tp1_hit", False)
                and not data.get("tp2_hit", False)
                and price >= tp2
            ):

                send_telegram(
                    f"🎯 TP2 REACHED\n\n"
                    f"💎 {symbol}\n\n"
                    f"Entry: {format_price(entry)}\n"
                    f"Current: {format_price(price)}\n\n"
                    f"TP2: {format_price(tp2)}"
                )

                data["tp2_hit"] = True
                changed = True

            if (
                data.get("tp2_hit", False)
                and not data.get("tp3_hit", False)
                and price >= tp3
            ):

                send_telegram(
                    f"🏆 TP3 REACHED\n\n"
                    f"💎 {symbol}\n\n"
                    f"Entry: {format_price(entry)}\n"
                    f"Current: {format_price(price)}\n\n"
                    f"TP3: {format_price(tp3)}\n\n"
                    f"✅ Signal completed."
                )

                data["tp3_hit"] = True
                data["completed"] = True
                changed = True

            elif price <= stop_loss:

                send_telegram(
                    f"🛑 STOP LOSS REACHED\n\n"
                    f"💎 {symbol}\n\n"
                    f"Entry: {format_price(entry)}\n"
                    f"Current: {format_price(price)}\n\n"
                    f"Stop Loss: "
                    f"{format_price(stop_loss)}\n\n"
                    f"⚠️ Signal completed."
                )

                data["completed"] = True
                changed = True

        # SELL signal monitoring
        elif signal == "SELL":

            if (
                not data.get("tp1_hit", False)
                and price <= tp1
            ):

                send_telegram(
                    f"🎯 TP1 REACHED\n\n"
                    f"💎 {symbol}\n\n"
                    f"Entry: {format_price(entry)}\n"
                    f"Current: {format_price(price)}\n\n"
                    f"TP1: {format_price(tp1)}"
                )

                data["tp1_hit"] = True
                changed = True

            if (
                data.get("tp1_hit", False)
                and not data.get("tp2_hit", False)
                and price <= tp2
            ):

                send_telegram(
                    f"🎯 TP2 REACHED\n\n"
                    f"💎 {symbol}\n\n"
                    f"Entry: {format_price(entry)}\n"
                    f"Current: {format_price(price)}\n\n"
                    f"TP2: {format_price(tp2)}"
                )

                data["tp2_hit"] = True
                changed = True

            if (
                data.get("tp2_hit", False)
                and not data.get("tp3_hit", False)
                and price <= tp3
            ):

                send_telegram(
                    f"🏆 TP3 REACHED\n\n"
                    f"💎 {symbol}\n\n"
                    f"Entry: {format_price(entry)}\n"
                    f"Current: {format_price(price)}\n\n"
                    f"TP3: {format_price(tp3)}\n\n"
                    f"✅ Signal completed."
                )

                data["tp3_hit"] = True
                data["completed"] = True
                changed = True

            elif price >= stop_loss:

                send_telegram(
                    f"🛑 STOP LOSS REACHED\n\n"
                    f"💎 {symbol}\n\n"
                    f"Entry: {format_price(entry)}\n"
                    f"Current: {format_price(price)}\n\n"
                    f"Stop Loss: "
                    f"{format_price(stop_loss)}\n\n"
                    f"⚠️ Signal completed."
                )

                data["completed"] = True
                changed = True

        print(
            f"{symbol}: "
            f"{signal} "
            f"Current={format_price(price)}"
        )

    if changed:
        save_state(state)

    print("Signal monitoring completed.")


if __name__ == "__main__":
    main()
