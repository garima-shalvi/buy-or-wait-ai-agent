from decimal import Decimal
import pandas as pd

def get_rate(exchange_rates, date, from_currency, to_currency):
    if from_currency == to_currency:
        return Decimal("1")
    date = pd.to_datetime(date).date()
    rates = exchange_rates[
        (exchange_rates["from_currency"] == from_currency) &
        (exchange_rates["to_currency"] == to_currency)
    ].copy()
    rates["rate_date"] = pd.to_datetime(rates["rate_date"]).dt.date
    rates = rates[rates["rate_date"] <= date]
    if rates.empty:
        raise ValueError(
            f"No exchange rate available for {from_currency}->{to_currency} on or before {date}"
        )
    return Decimal(str(rates.sort_values("rate_date").iloc[-1]["rate"]))

def normalize_evidence(facts, profile, exchange_rates):
    normalized = []
    home_currency = str(profile["home_currency"])

    for fact in facts:
        fact = dict(fact)
        amount = fact.get("amount")
        currency = fact.get("currency")

        if amount is not None and currency is None:
            evidence_type = str(fact.get("evidence_type", "")).lower()
            summary = str(fact.get("summary", "")).lower()

            if (
                evidence_type == "expense_change"
                or "%" in summary
                or "percent" in summary
                or "percentage" in summary
            ):
                fact["change_percent"] = Decimal(str(amount))
                normalized.append(fact)
                continue

            raise ValueError(
                f"Evidence {fact['fact_id']} has amount but no currency"
            )

        if amount is not None and currency is not None:
            fact["original_currency"] = str(currency).upper()

        date = fact.get("as_of_date")
        if date is None:
            date = fact.get("effective_date")
        if date is None:
            date = fact.get("event_date")

        if amount is not None and currency is not None and date is not None:
            rate = get_rate(
                exchange_rates,
                date,
                str(currency).upper(),
                home_currency
            )
            fact["amount_home"] = Decimal(str(amount)) * rate

        normalized.append(fact)

    return normalized

def apply_evidence_to_events(events, facts, exchange_rates):
    events = events.copy()

    if "amount_home" not in events.columns:
        events["amount_home"] = None

    event_index = {
        str(row["event_id"]): index
        for index, row in events.iterrows()
    }

    for fact in facts:
        event_id = fact.get("event_id")
        amount = fact.get("amount")

        if event_id is None or amount is None:
            continue

        event_id = str(event_id)

        if event_id not in event_index:
            continue

        index = event_index[event_id]
        existing_amount = events.at[index, "amount"]

        if pd.isna(existing_amount):
            currency = fact.get("original_currency") or fact.get("currency")
            event_date = events.at[index, "event_date"]
            home_currency = str(events.at[index, "_home_currency"])

            rate = get_rate(
                exchange_rates,
                event_date,
                str(currency).upper(),
                home_currency
            )

            events.at[index, "amount"] = float(amount)
            events.at[index, "currency"] = str(currency).upper()
            events.at[index, "amount_home"] = Decimal(str(amount)) * rate

    return events