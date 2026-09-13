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

def normalize_evidence(facts, profile, exchange_rates):
    normalized = []

    home_currency = str(profile["home_currency"])

    for fact in facts:
        fact = dict(fact)

        amount = fact.get("amount")
        currency = fact.get("currency")
        date = fact.get("as_of_date")

        if amount is not None:
            if currency is None:
                raise ValueError(
                    f"Evidence {fact['fact_id']} has amount but no currency"
                )

            if date is None:
                raise ValueError(
                    f"Evidence {fact['fact_id']} has amount but no date"
                )

            rate = get_rate(
                exchange_rates,
                date,
                currency,
                home_currency
            )

            fact["amount"] = Decimal(str(amount)) * rate
            fact["currency"] = home_currency

        normalized.append(fact)

    return normalized