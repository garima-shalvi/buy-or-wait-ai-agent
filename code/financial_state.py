from dataclasses import dataclass
from decimal import Decimal
import pandas as pd
from recurrence_resolver import resolve_recurrence

@dataclass
class FinancialState:
    user_id: str
    home_currency: str
    current_balance: Decimal
    minimum_balance: Decimal
    protected_categories: list
    reducible_expenses: list
    stoppable_expenses: list
    recurring_income: list
    recurring_expenses: list
    recurring_patterns: list
    future_confirmed_income: list
    future_confirmed_expenses: list
    one_time_events: list
    payment_methods: list
    max_installment_months: int

def split_profile_value(value):
    if pd.isna(value):
        return []
    return [x.strip() for x in str(value).split("|") if x.strip()]

def make_event_record(event):
    amount = event["amount_home"]
    if pd.isna(amount):
        raise ValueError(f"Unresolved event amount: {event['event_id']}")
    return {
        "event_id": event["event_id"],
        "user_id": event["user_id"],
        "event_type": event["event_type"],
        "description": event["description"],
        "category": event["category"],
        "direction": event["direction"],
        "amount": Decimal(str(amount)),
        "currency": event["currency"],
        "event_date": str(event["event_date"])[:10],
        "settlement_date": None if pd.isna(event["settlement_date"]) else str(event["settlement_date"])[:10],
        "status": event["status"],
        "flexibility": event["flexibility"],
        "minimum_allowed_amount": None if pd.isna(event["minimum_allowed_amount"]) else Decimal(str(event["minimum_allowed_amount"]))
    }

def is_future(event, request_date):
    return pd.to_datetime(event["event_date"]).date() > pd.to_datetime(request_date).date()

def build_financial_state(context, resolved_events, evidence_facts=None, exchange_rates=None):
    profile = context["profile"]
    request = context["request"]
    request_date = request["request_date"]

    protected_categories = split_profile_value(profile["expense_categories_to_protect"])
    payment_methods = split_profile_value(profile["payment_methods_user_will_consider"])

    state = FinancialState(
        user_id=str(profile["user_id"]),
        home_currency=str(profile["home_currency"]),
        current_balance=Decimal(str(profile["current_available_balance"])),
        minimum_balance=Decimal(str(profile["minimum_balance_to_keep"])),
        protected_categories=protected_categories,
        reducible_expenses=[],
        stoppable_expenses=[],
        recurring_income=[],
        recurring_expenses=[],
        recurring_patterns=[],
        future_confirmed_income=[],
        future_confirmed_expenses=[],
        one_time_events=[],
        payment_methods=payment_methods,
        max_installment_months=None if pd.isna(profile["max_installment_months"]) else int(profile["max_installment_months"])
    )

    allowed_reduce = {x.lower() for x in split_profile_value(profile["expense_categories_user_is_willing_to_reduce"])}
    allowed_stop = {x.lower() for x in split_profile_value(profile["expense_categories_user_is_willing_to_stop"])}
    protected = {x.lower() for x in protected_categories}

    historical_events = []

    for event in resolved_events.to_dict("records"):
        if pd.isna(event["amount_home"]):
            raise ValueError(f"Unresolved financial event amount: {event['event_id']}")

        record = make_event_record(event)

        if is_future(event, request_date):
            status = str(event["status"]).lower()
            direction = str(event["direction"]).lower()

            if status in {"confirmed", "scheduled"}:
                if direction == "credit":
                    state.future_confirmed_income.append(record)
                elif direction == "debit":
                    state.future_confirmed_expenses.append(record)
            continue

        if not bool(event["include"]):
            continue

        direction = str(event["direction"]).lower()

        if direction in {"credit", "debit"}:
            historical_events.append(record)

    recurrence_patterns = resolve_recurrence(historical_events)

    reliable_patterns = []
    recurring_ids = set()

    for pattern in recurrence_patterns:
        if not pattern.get("reliable", True):
            continue

        reliable_patterns.append(pattern)

        for event in pattern.get("events", []):
            recurring_ids.add(event["event_id"])

        last_event = pattern.get("last_event")
        if last_event:
            recurring_ids.add(last_event["event_id"])

    state.recurring_patterns = reliable_patterns

    for event in historical_events:
        if event["event_id"] in recurring_ids:
            if str(event["direction"]).lower() == "credit":
                state.recurring_income.append(event)
            else:
                state.recurring_expenses.append(event)
        else:
            state.one_time_events.append(event)

    for pattern in reliable_patterns:
        if str(pattern.get("direction", "")).lower() != "debit":
            continue

        pattern_events = pattern.get("events", [])
        if not pattern_events:
            last_event = pattern.get("last_event")
            if last_event:
                pattern_events = [last_event]

        if not pattern_events:
            continue

        representative = pattern_events[-1]

        category = str(representative.get("category", "")).strip().lower()
        flexibility = str(representative.get("flexibility", "")).strip().lower()

        if category in protected:
            continue

        minimum = representative.get("minimum_allowed_amount")

        if minimum is not None and exchange_rates is not None:
            currency = str(representative.get("currency", ""))
            home_currency = state.home_currency
            event_date = representative.get("event_date")

            if currency != home_currency:
                rates = exchange_rates[
                    (exchange_rates["rate_date"] == event_date) &
                    (exchange_rates["from_currency"] == currency) &
                    (exchange_rates["to_currency"] == home_currency)
                ]

                if rates.empty:
                    raise ValueError(
                        f"Missing exchange rate for minimum amount: "
                        f"{currency}->{home_currency} on {event_date}"
                    )

                minimum = Decimal(str(minimum)) * Decimal(str(rates.iloc[0]["rate"]))

        item = {
            "event_id": representative["event_id"],
            "category": category,
            "description": representative.get("description", ""),
            "amount": Decimal(str(representative["amount"])),
            "minimum_allowed_amount": minimum,
            "flexibility": flexibility,
            "pattern": pattern
        }

        can_reduce = (
            category in allowed_reduce and
            flexibility in {"reducible", "reducible_or_stoppable", "flexible"}
        )

        can_stop = (
            category in allowed_stop and
            flexibility in {"stoppable", "reducible_or_stoppable", "flexible"}
        )

        if can_stop:
            state.stoppable_expenses.append(item)

        if can_reduce:
            state.reducible_expenses.append(item)

    if evidence_facts:
        for fact in evidence_facts:
            effect = str(fact.get("financial_effect", "")).lower()
            amount = fact.get("amount")
            date = fact.get("as_of_date")

            if (
                effect == "income"
                and amount is not None
                and date is not None
                and pd.to_datetime(date).date() > pd.to_datetime(request_date).date()
            ):
                state.future_confirmed_income.append({
                    "event_id": fact.get("event_id") or fact.get("fact_id"),
                    "event_type": "evidence_income",
                    "description": fact.get("notes", ""),
                    "category": "income",
                    "direction": "credit",
                    "amount": Decimal(str(amount)),
                    "event_date": str(date)[:10],
                    "settlement_date": str(date)[:10],
                    "status": "confirmed",
                    "flexibility": "fixed",
                    "minimum_allowed_amount": None
                })

    return state