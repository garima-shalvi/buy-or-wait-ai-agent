from decimal import Decimal
import pandas as pd

def get_rate(exchange_rates, date, from_currency, to_currency):
    if from_currency == to_currency:
        return Decimal("1")

    rates = exchange_rates[
        (exchange_rates["rate_date"] == date) &
        (exchange_rates["from_currency"] == from_currency) &
        (exchange_rates["to_currency"] == to_currency)
    ]

    if rates.empty:
        raise ValueError(
            f"No exchange rate for {from_currency}->{to_currency} on {date}"
        )

    return Decimal(str(rates.iloc[0]["rate"]))

def normalize_events(events, profiles, exchange_rates):
    events = events.copy()

    home_currency_map = profiles.set_index("user_id")["home_currency"]

    normalized_amounts = []

    for _, event in events.iterrows():
        amount = event["amount"]

        if pd.isna(amount):
            normalized_amounts.append(None)
            continue

        home_currency = home_currency_map[event["user_id"]]

        rate = get_rate(
            exchange_rates,
            event["event_date"],
            event["currency"],
            home_currency
        )

        normalized_amounts.append(
            Decimal(str(amount)) * rate
        )

    events["amount_home"] = normalized_amounts
    return events

if __name__ == "__main__":
    from data_loader import load_data

    data = load_data()

    events = normalize_events(
        data["events"],
        data["profiles"],
        data["exchange_rates"]
    )

    different_currency = events[
        events["currency"] != events["user_id"].map(
            data["profiles"].set_index("user_id")["home_currency"]
        )
    ]

    print(
        different_currency[
            [
                "event_id",
                "user_id",
                "amount",
                "currency",
                "amount_home"
            ]
        ].head(20).to_string(index=False)
    )