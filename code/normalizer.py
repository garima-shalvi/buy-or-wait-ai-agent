from decimal import Decimal
import pandas as pd


def get_rate(exchange_rates, date, from_currency, to_currency):
    if from_currency == to_currency:
        return Decimal("1")

    date = str(pd.to_datetime(date).date())

    rates = exchange_rates[
        (exchange_rates["rate_date"].astype(str) == date) &
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

    home_currency_map = profiles.set_index(
        "user_id"
    )["home_currency"]

    events["_home_currency"] = events["user_id"].map(
        home_currency_map
    )

    normalized_amounts = []

    for _, event in events.iterrows():
        amount = event["amount"]

        if pd.isna(amount):
            normalized_amounts.append(None)
            continue

        rate = get_rate(
            exchange_rates,
            event["event_date"],
            event["currency"],
            event["_home_currency"]
        )

        normalized_amounts.append(
            Decimal(str(amount)) * rate
        )

    events["amount_home"] = normalized_amounts

    return events