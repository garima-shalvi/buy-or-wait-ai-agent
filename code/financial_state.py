from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
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
    max_installment_months: Optional[int]


def make_event_record(event):
    return {
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "category": event["category"],
        "description": event["description"],
        "amount": Decimal(str(event["amount_home"])),
        "event_date": str(event["event_date"]),
        "settlement_date": (
            None
            if pd.isna(event["settlement_date"])
            else str(event["settlement_date"])
        ),
        "status": event["status"],
        "direction": event["direction"],
        "flexibility": event["flexibility"],
        "minimum_allowed_amount": (
            None
            if pd.isna(event["minimum_allowed_amount"])
            else Decimal(str(event["minimum_allowed_amount"]))
        )
    }


def is_future(event, request_date):
    return (
        pd.to_datetime(event["event_date"])
        > pd.to_datetime(request_date)
    )


def build_financial_state(
    context,
    resolved_events,
    evidence_facts=None
):
    profile = context["profile"]
    request = context["request"]
    request_date = request["request_date"]

    state = FinancialState(
        user_id=str(profile["user_id"]),
        home_currency=str(profile["home_currency"]),
        current_balance=Decimal(
            str(profile["current_available_balance"])
        ),
        minimum_balance=Decimal(
            str(profile["minimum_balance_to_keep"])
        ),
        protected_categories=[
            x
            for x in str(
                profile["expense_categories_to_protect"]
            ).split("|")
            if x
        ],
        reducible_expenses=[],
        stoppable_expenses=[],
        recurring_income=[],
        recurring_expenses=[],
        recurring_patterns=[],
        future_confirmed_income=[],
        future_confirmed_expenses=[],
        one_time_events=[],
        payment_methods=[
            x
            for x in str(
                profile["payment_methods_user_will_consider"]
            ).split("|")
            if x
        ],
        max_installment_months=(
            None
            if pd.isna(profile["max_installment_months"])
            else int(profile["max_installment_months"])
        )
    )

    historical_events = []

    for _, event in resolved_events.iterrows():
        if pd.isna(event["amount_home"]):
            raise ValueError(
                f"Unresolved amount for event {event['event_id']}"
            )

        flexibility = str(
            event["flexibility"]
        ).lower()

        record = make_event_record(event)

        if flexibility in {
            "reducible",
            "reducible_or_stoppable"
        }:
            state.reducible_expenses.append(record)

        if flexibility == "reducible_or_stoppable":
            state.stoppable_expenses.append(record)

        future = is_future(
            event,
            request_date
        )

        status = str(
            event["status"]
        ).lower()

        direction = str(
            event["direction"]
        ).lower()

        if future and status in {
            "scheduled",
            "confirmed"
        }:
            if direction == "credit":
                state.future_confirmed_income.append(record)
            elif direction == "debit":
                state.future_confirmed_expenses.append(record)
            continue

        if not bool(event["include"]):
            continue

        if future:
            continue

        if direction in {"credit", "debit"}:
            historical_events.append(record)

    recurrence_patterns = resolve_recurrence(
        historical_events
    )

    state.recurring_patterns = [
        pattern
        for pattern in recurrence_patterns
        if pattern["classification"]
        == "reliable_recurring"
    ]

    recurring_ids = set()

    for pattern in state.recurring_patterns:
        for event in pattern["events"]:
            recurring_ids.add(
                event["event_id"]
            )

    for event in historical_events:
        if event["event_id"] in recurring_ids:
            if event["direction"] == "credit":
                state.recurring_income.append(event)
            elif event["direction"] == "debit":
                state.recurring_expenses.append(event)
        else:
            state.one_time_events.append(event)

    if evidence_facts:
        for fact in evidence_facts:
            if fact.get("financial_effect") != "income":
                continue

            amount = fact.get("amount")
            date = fact.get("as_of_date")

            if amount is None or date is None:
                continue

            if pd.to_datetime(date) <= pd.to_datetime(
                request_date
            ):
                continue

            state.future_confirmed_income.append({
                "event_id": fact.get("event_id"),
                "event_type": "evidence_income",
                "category": "income",
                "description": fact.get(
                    "notes",
                    ""
                ),
                "amount": Decimal(
                    str(amount)
                ),
                "event_date": date,
                "settlement_date": date,
                "status": "confirmed",
                "direction": "credit",
                "flexibility": "fixed",
                "minimum_allowed_amount": None
            })

    return state