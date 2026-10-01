import os
import json
import time
import requests

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

STATE_FILE = "signal_state.json"


def get_price(symbol):

    url = (
        "https://data-api.binance.vision"
        "/api/v3/ticker/price"
    )

    response = requests.get(
        url,
        params={
            "symbol": symbol
        },
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    return float(data["price"])


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


def calculate_performance(
    signal,
    entry,
    current_price,
    stop_loss
):

    if signal == "BUY":

        percentage = (
            (current_price - entry)
            / entry
        ) * 100

        risk = entry - stop_loss

        if risk > 0:
            r_value = (
                current_price - entry
            ) / risk
        else:
            r_value = 0

    else:

        percentage = (
            (entry - current_price)
            / entry
        ) * 100

        risk = stop_loss - entry

        if risk > 0:
            r_value = (
                entry - current_price
            ) / risk
        else:
            r_value = 0

    return percentage, r_value


def create_update_message(
    symbol,
    signal,
    current_price,
    entry,
    stop_loss,
    tp1,
    tp2,
    tp3,
    tp1_hit,
    tp2_hit,
    tp3_hit,
    result=None
):

    percentage, r_value = (
        calculate_performance(
            signal,
            entry,
            current_price,
            stop_loss
        )
    )

    if result == "TP1":

        title = (
            f"🟢 SIGNAL UPDATE\n\n"
            f"{symbol} {signal}\n\n"
            f"🎯 TP1 HIT"
        )

    elif result == "TP2":

        title = (
            f"🟢 SIGNAL UPDATE\n\n"
            f"{symbol} {signal}\n\n"
            f"🎯 TP2 HIT"
        )

    elif result == "TP3":

        title = (
            f"🏆 SIGNAL COMPLETED\n\n"
            f"{symbol} {signal}\n\n"
            f"🎯 TP3 HIT"
        )

    elif result == "SL":

        title = (
            f"🔴 SIGNAL COMPLETED\n\n"
            f"{symbol} {signal}\n\n"
            f"🛑 STOP LOSS HIT"
        )

    else:

        title = (
            f"📊 SIGNAL PERFORMANCE\n\n"
            f"{symbol} {signal}"
        )

    if result in ["TP3", "SL"]:

        status = "COMPLETED"

    else:

        status = "ACTIVE"

    if result == "TP3":

        result_text = "🟢 TP3"

    elif result == "SL":

        result_text = "🔴 STOP LOSS"

    elif result == "TP2":

        result_text = "🟢 TP2"

    elif result == "TP1":

        result_text = "🟢 TP1"

    else:

        result_text = "⏳ ACTIVE"

    message = f"""
{title}

━━━━━━━━━━━━━━━━
📊 SIGNAL PERFORMANCE
━━━━━━━━━━━━━━━━

Entry: {format_price(entry)}
Current: {format_price(current_price)}

Current P/L:
{percentage:+.2f}%

Performance:
{r_value:+.2f}R

TP1: {"✅" if tp1_hit else "❌"} {format_price(tp1)}
TP2: {"✅" if tp2_hit else "❌"} {format_price(tp2)}
TP3: {"✅" if tp3_hit else "❌"} {format_price(tp3)}
SL: {"✅" if result == "SL" else "❌"} {format_price(stop_loss)}

Result: {result_text}
Status: {status}
"""

    return message.strip()


def main():

    state = load_state()

    changed = False

    for symbol, data in list(
        state.items()
    ):

        if symbol == "last_status_time":
            continue

        if not isinstance(data, dict):
            continue

        signal = data.get("signal")

        if signal not in ["BUY", "SELL"]:
            continue

        if data.get("completed", False):
            continue

        required_fields = [
            "entry",
            "stop_loss",
            "tp1",
            "tp2",
            "tp3",
        ]

        if any(
            data.get(field) is None
            for field in required_fields
        ):
            print(
                f"{symbol}: Missing "
                f"performance data."
            )

            continue

        try:

            current_price = get_price(
                symbol
            )

            entry = float(
                data["entry"]
            )

            stop_loss = float(
                data["stop_loss"]
            )

            tp1 = float(
                data["tp1"]
            )

            tp2 = float(
                data["tp2"]
            )

            tp3 = float(
                data["tp3"]
            )

            tp1_hit = data.get(
                "tp1_hit",
                False
            )

            tp2_hit = data.get(
                "tp2_hit",
                False
            )

            tp3_hit = data.get(
                "tp3_hit",
                False
            )

            result = None

            if signal == "BUY":

                if (
                    not tp1_hit
                    and current_price >= tp1
                ):

                    data["tp1_hit"] = True
                    tp1_hit = True

                    send_telegram(
                        create_update_message(
                            symbol,
                            signal,
                            current_price,
                            entry,
                            stop_loss,
                            tp1,
                            tp2,
                            tp3,
                            tp1_hit,
                            tp2_hit,
                            tp3_hit,
                            "TP1",
                        )
                    )

                    changed = True

                if (
                    tp1_hit
                    and not tp2_hit
                    and current_price >= tp2
                ):

                    data["tp2_hit"] = True
                    tp2_hit = True

                    send_telegram(
                        create_update_message(
                            symbol,
                            signal,
                            current_price,
                            entry,
                            stop_loss,
                            tp1,
                            tp2,
                            tp3,
                            tp1_hit,
                            tp2_hit,
                            tp3_hit,
                            "TP2",
                        )
                    )

                    changed = True

                if (
                    tp2_hit
                    and not tp3_hit
                    and current_price >= tp3
                ):

                    data["tp3_hit"] = True
                    data["completed"] = True

                    tp3_hit = True

                    send_telegram(
                        create_update_message(
                            symbol,
                            signal,
                            current_price,
                            entry,
                            stop_loss,
                            tp1,
                            tp2,
                            tp3,
                            tp1_hit,
                            tp2_hit,
                            tp3_hit,
                            "TP3",
                        )
                    )

                    changed = True

                elif current_price <= stop_loss:

                    data["completed"] = True

                    send_telegram(
                        create_update_message(
                            symbol,
                            signal,
                            current_price,
                            entry,
                            stop_loss,
                            tp1,
                            tp2,
                            tp3,
                            tp1_hit,
                            tp2_hit,
                            tp3_hit,
                            "SL",
                        )
                    )

                    changed = True

            else:

                if (
                    not tp1_hit
                    and current_price <= tp1
                ):

                    data["tp1_hit"] = True
                    tp1_hit = True

                    send_telegram(
                        create_update_message(
                            symbol,
                            signal,
                            current_price,
                            entry,
                            stop_loss,
                            tp1,
                            tp2,
                            tp3,
                            tp1_hit,
                            tp2_hit,
                            tp3_hit,
                            "TP1",
                        )
                    )

                    changed = True

                if (
                    tp1_hit
                    and not tp2_hit
                    and current_price <= tp2
                ):

                    data["tp2_hit"] = True
                    tp2_hit = True

                    send_telegram(
                        create_update_message(
                            symbol,
                            signal,
                            current_price,
                            entry,
                            stop_loss,
                            tp1,
                            tp2,
                            tp3,
                            tp1_hit,
                            tp2_hit,
                            tp3_hit,
                            "TP2",
                        )
                    )

                    changed = True

                if (
                    tp2_hit
                    and not tp3_hit
                    and current_price <= tp3
                ):

                    data["tp3_hit"] = True
                    data["completed"] = True

                    tp3_hit = True

                    send_telegram(
                        create_update_message(
                            symbol,
                            signal,
                            current_price,
                            entry,
                            stop_loss,
                            tp1,
                            tp2,
                            tp3,
                            tp1_hit,
                            tp2_hit,
                            tp3_hit,
                            "TP3",
                        )
                    )

                    changed = True

                elif current_price >= stop_loss:

                    data["completed"] = True

                    send_telegram(
                        create_update_message(
                            symbol,
                            signal,
                            current_price,
                            entry,
                            stop_loss,
                            tp1,
                            tp2,
                            tp3,
                            tp1_hit,
                            tp2_hit,
                            tp3_hit,
                            "SL",
                        )
                    )

                    changed = True

            print(
                f"{symbol}: {signal} "
                f"Current={format_price(current_price)}"
            )

        except Exception as error:

            print(
                f"{symbol}: ERROR - {error}"
            )

    if changed:
        save_state(state)

    print(
        "Signal monitoring completed."
    )


if __name__ == "__main__":
    main()
