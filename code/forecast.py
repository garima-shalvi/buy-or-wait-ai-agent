from decimal import Decimal
from datetime import timedelta
import pandas as pd


def option_is_eligible(option, max_installment_months):
    if max_installment_months is None:
        return True

    frequency = option["payment_frequency_days"]
    number_of_payments = option["number_of_payments"]

    if pd.isna(frequency) or pd.isna(number_of_payments):
        return True

    duration_days = int(frequency) * (int(number_of_payments) - 1)

    return duration_days <= max_installment_months * 31


def get_horizon(request, payment_options=None, max_installment_months=None):
    request_date = pd.to_datetime(request["request_date"])
    desired_date = pd.to_datetime(request["desired_completion_date"])

    dates = [
        request_date + timedelta(days=90),
        desired_date
    ]

    if payment_options is not None and not payment_options.empty:
        for _, option in payment_options.iterrows():
            if not option_is_eligible(option, max_installment_months):
                continue

            first_date = option["first_payment_date"]

            if pd.isna(first_date):
                continue

            first_date = pd.to_datetime(first_date)
            frequency = option["payment_frequency_days"]

            if pd.isna(frequency):
                dates.append(first_date)
                continue

            payments = int(option["number_of_payments"])

            last_date = first_date + timedelta(
                days=int(frequency) * (payments - 1)
            )

            dates.append(last_date)

    return max(dates).date()


def event_cash_effect(event):
    direction = str(event["direction"]).strip().lower()

    if direction == "credit":
        return event["amount"]

    if direction == "debit":
        return -event["amount"]

    if direction == "non_cash":
        return Decimal("0")

    raise ValueError(
        f"Unrecognized direction {direction!r} "
        f"for event {event['event_id']}"
    )


def generate_recurring_events(recurring_patterns, request_date, horizon):
    if not recurring_patterns:
        return []

    generated = []

    request_date = pd.to_datetime(request_date).date()
    horizon = pd.to_datetime(horizon).date()

    for pattern in recurring_patterns:
        last_event = pattern["last_event"]
        next_date = pd.to_datetime(last_event["event_date"])

        while True:
            if pattern["frequency_type"] == "monthly":
                next_date = next_date + pd.DateOffset(months=1)
            else:
                next_date = next_date + timedelta(
                    days=pattern["frequency_days"]
                )

            next_date = pd.to_datetime(next_date)

            if next_date.date() > horizon:
                break

            if next_date.date() < request_date:
                continue

            amount = pattern["typical_amount"]

            if pattern["direction"] == "debit":
                amount = -amount
            elif pattern["direction"] != "credit":
                raise ValueError(
                    f"Unknown recurring direction: "
                    f"{pattern['direction']}"
                )

            generated.append({
                "date": next_date.date(),
                "event_id": (
                    f"forecast:{last_event['event_id']}:"
                    f"{next_date.date()}"
                ),
                "amount": amount,
                "type": "forecast_recurring"
            })

    return generated


def build_cash_events(state, request_date, horizon):
    cash_events = []

    cash_events.extend(
        generate_recurring_events(
            state.recurring_patterns,
            request_date,
            horizon
        )
    )

    for event in state.future_confirmed_income:
        date = pd.to_datetime(event["event_date"]).date()

        if pd.to_datetime(request_date).date() <= date <= horizon:
            cash_events.append({
                "date": date,
                "event_id": event["event_id"] or "confirmed_income",
                "amount": event["amount"],
                "type": "confirmed_income"
            })

    for event in state.future_confirmed_expenses:
        date = pd.to_datetime(event["event_date"]).date()

        if pd.to_datetime(request_date).date() <= date <= horizon:
            cash_events.append({
                "date": date,
                "event_id": event["event_id"],
                "amount": -event["amount"],
                "type": "confirmed_expense"
            })

    for event in state.one_time_events:
        date = pd.to_datetime(event["event_date"]).date()

        if pd.to_datetime(request_date).date() <= date <= horizon:
            cash_events.append({
                "date": date,
                "event_id": event["event_id"],
                "amount": event_cash_effect(event),
                "type": "one_time"
            })

    return cash_events


def apply_payment(
    cash_events,
    payment_date,
    amount,
    payment_id="request_payment"
):
    cash_events.append({
        "date": pd.to_datetime(payment_date).date(),
        "event_id": payment_id,
        "amount": -Decimal(str(amount)),
        "type": "request_payment"
    })


def simulate(
    state,
    request_date,
    base_cash_events,
    payment_plan=None
):
    cash_events = [dict(event) for event in base_cash_events]

    if payment_plan:
        for payment in payment_plan:
            apply_payment(
                cash_events,
                payment["date"],
                payment["amount"],
                payment.get("payment_id", "request_payment")
            )

    cash_events.sort(
        key=lambda x: (x["date"], x["event_id"])
    )

    balance = state.current_balance
    minimum = state.minimum_balance

    timeline = [{
        "date": pd.to_datetime(request_date).date(),
        "event_id": "starting_balance",
        "amount": Decimal("0"),
        "balance": balance,
        "type": "starting_balance"
    }]

    minimum_balance_seen = balance
    safe = balance > minimum

    for event in cash_events:
        balance += event["amount"]

        minimum_balance_seen = min(
            minimum_balance_seen,
            balance
        )

        timeline.append({
            "date": event["date"],
            "event_id": event["event_id"],
            "amount": event["amount"],
            "balance": balance,
            "type": event["type"]
        })

        if balance <= minimum:
            safe = False

    return {
        "safe": safe,
        "minimum_balance_seen": minimum_balance_seen,
        "ending_balance": balance,
        "timeline": timeline
    }


if __name__ == "__main__":
    from data_loader import load_data
    from context_builder import build_context
    from evidence_resolver import resolve_evidence
    from evidence_normalizer import normalize_evidence
    from normalizer import normalize_events
    from event_resolver import resolve_events
    from financial_state import build_financial_state

    data = load_data()

    request_id = "request_26"

    context = build_context(request_id, data)

    facts = resolve_evidence(context)

    facts = normalize_evidence(
        facts,
        context["profile"],
        data["exchange_rates"]
    )

    normalized_events = normalize_events(
        context["events"],
        data["profiles"],
        data["exchange_rates"]
    )

    resolved_events = resolve_events(normalized_events)

    state = build_financial_state(
        context,
        resolved_events,
        facts
    )

    horizon = get_horizon(
        context["request"],
        context["payment_options"],
        state.max_installment_months
    )

    cash_events = build_cash_events(
        state,
        context["request"]["request_date"],
        horizon
    )

    result = simulate(
        state,
        context["request"]["request_date"],
        cash_events
    )

    print("EVIDENCE:")
    for fact in facts:
        print(fact)

    print("\nHORIZON:", horizon)
    print("SAFE:", result["safe"])
    print("MIN:", result["minimum_balance_seen"])
    print("END:", result["ending_balance"])

    print("\nFUTURE INCOME:")
    for event in state.future_confirmed_income:
        print(event)