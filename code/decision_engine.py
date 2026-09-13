from decimal import Decimal
import pandas as pd
from forecast import simulate
from planner import make_full_payment_plan

def money(value):
    return Decimal(str(value))

def request_allows_partial(request):
    text = str(request.get("request_text", "")).lower()

    phrases = [
        "partial payment",
        "partial payments",
        "pay partially",
        "pay part",
        "partial",
        "part of the amount"
    ]

    return any(phrase in text for phrase in phrases)

def safe_amount_now(state, request_date, base_cash_events, requested_amount):
    requested_amount = money(requested_amount)

    if requested_amount <= 0:
        return Decimal("0")

    result = simulate(
        state,
        request_date,
        base_cash_events,
        make_full_payment_plan(
            request_date,
            requested_amount
        )
    )

    if result["safe"]:
        return requested_amount

    low = Decimal("0")
    high = requested_amount

    for _ in range(80):
        mid = (low + high) / Decimal("2")

        result = simulate(
            state,
            request_date,
            base_cash_events,
            make_full_payment_plan(
                request_date,
                mid
            )
        )

        if result["safe"]:
            low = mid
        else:
            high = mid

    return low.quantize(Decimal("0.01"))

def candidate_dates(
    request_date,
    horizon,
    base_cash_events
):
    request_date = pd.to_datetime(
        request_date
    ).date()

    horizon = pd.to_datetime(
        horizon
    ).date()

    dates = {request_date}

    for event in base_cash_events:
        date = pd.to_datetime(
            event["date"]
        ).date()

        if request_date <= date <= horizon:
            dates.add(date)

    return sorted(dates)

def earliest_full_payment_date(
    state,
    request_date,
    horizon,
    base_cash_events,
    requested_amount
):
    requested_amount = money(requested_amount)

    for date in candidate_dates(
        request_date,
        horizon,
        base_cash_events
    ):
        plan = make_full_payment_plan(
            date,
            requested_amount
        )

        result = simulate(
            state,
            request_date,
            base_cash_events,
            plan
        )

        if result["safe"]:
            return date

    return None

def make_partial_payment_plan(
    request_date,
    safe_amount,
    requested_amount,
    full_payment_date
):
    remainder = (
        money(requested_amount)
        - money(safe_amount)
    )

    return [
        {
            "date": pd.to_datetime(
                request_date
            ).date(),
            "amount": money(safe_amount),
            "payment_id": "request_payment_1"
        },
        {
            "date": pd.to_datetime(
                full_payment_date
            ).date(),
            "amount": remainder,
            "payment_id": "request_payment_2"
        }
    ]

def choose_best_candidate(candidates):
    if not candidates:
        return None

    def rank(candidate):
        end_date = pd.to_datetime(
            candidate["end_date"]
        )

        changes = candidate.get(
            "spending_changes_needed",
            []
        )

        total_paid = money(
            candidate.get("total_paid", 0)
        )

        start_date = min(
            pd.to_datetime(
                payment["date"]
            )
            for payment in candidate["payment_plan"]
        )

        payment_count = len(
            candidate["payment_plan"]
        )

        option_id = candidate.get(
            "payment_option_id"
        )

        return (
            end_date,
            len(changes),
            total_paid,
            start_date,
            payment_count,
            option_id
            if option_id is not None
            else 10**9
        )

    return sorted(
        candidates,
        key=rank
    )[0]

def decide(
    context,
    state,
    horizon,
    base_cash_events,
    valid_candidates
):
    request = context["request"]

    request_date = pd.to_datetime(
        request["request_date"]
    ).date()

    desired_date = pd.to_datetime(
        request["desired_completion_date"]
    ).date()

    requested_amount = money(
        request["requested_amount"]
    )

    safe_now = safe_amount_now(
        state,
        request_date,
        base_cash_events,
        requested_amount
    )

    earliest_date = earliest_full_payment_date(
        state,
        request_date,
        horizon,
        base_cash_events,
        requested_amount
    )

    best = choose_best_candidate(
        valid_candidates
    )

    if best is not None:
        method = best["method"]
        plan = best["payment_plan"]
        end_date = pd.to_datetime(
            best["end_date"]
        ).date()

        if method == "full_payment":
            status = "affordable_now"
        elif end_date <= desired_date:
            status = "affordable_with_plan"
        else:
            status = "affordable_later"

        return {
            "amount_safe_to_pay": safe_now,
            "affordability_status": status,
            "recommended_payment_method": method,
            "payment_plan": plan,
            "earliest_date_for_full_payment": earliest_date,
            "spending_changes_needed": best.get(
                "spending_changes_needed",
                []
            ),
            "validation": best
        }

    if (
        request_allows_partial(request)
        and safe_now > Decimal("0")
        and safe_now < requested_amount
        and earliest_date is not None
        and earliest_date <= desired_date
    ):
        plan = make_partial_payment_plan(
            request_date,
            safe_now,
            requested_amount,
            earliest_date
        )

        return {
            "amount_safe_to_pay": safe_now,
            "affordability_status": "affordable_with_plan",
            "recommended_payment_method": "partial_payment",
            "payment_plan": plan,
            "earliest_date_for_full_payment": earliest_date,
            "spending_changes_needed": [],
            "validation": None
        }

    if (
        earliest_date is not None
        and earliest_date > request_date
    ):
        return {
            "amount_safe_to_pay": safe_now,
            "affordability_status": "affordable_later",
            "recommended_payment_method": "wait",
            "payment_plan": [],
            "earliest_date_for_full_payment": earliest_date,
            "spending_changes_needed": [],
            "validation": None
        }

    return {
        "amount_safe_to_pay": safe_now,
        "affordability_status": "not_affordable",
        "recommended_payment_method": "not_recommended",
        "payment_plan": [],
        "earliest_date_for_full_payment": None,
        "spending_changes_needed": [],
        "validation": None
    }