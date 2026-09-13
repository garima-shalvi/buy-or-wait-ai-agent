from decimal import Decimal
import pandas as pd
from forecast import simulate, option_is_eligible


def make_full_payment_plan(request_date, amount):
    return [{
        "date": pd.Timestamp(request_date).date(),
        "amount": Decimal(str(amount)),
        "payment_id": "request_payment_1"
    }]


def make_installment_plan(option):
    first_date = pd.to_datetime(option["first_payment_date"])
    frequency = int(option["payment_frequency_days"])
    number_of_payments = int(option["number_of_payments"])
    amount = Decimal(str(option["payment_amount"]))

    return [
        {
            "date": (
                first_date +
                pd.Timedelta(days=frequency * i)
            ).date(),
            "amount": amount,
            "payment_id": f"request_payment_{i + 1}"
        }
        for i in range(number_of_payments)
    ]


def plan_end_date(plan):
    return max(payment["date"] for payment in plan)


def run_simulation(
    state,
    request_date,
    base_cash_events,
    payment_plan
):
    result = simulate(
        state,
        request_date,
        base_cash_events,
        payment_plan
    )

    return (
        result["safe"],
        result["minimum_balance_seen"],
        result["ending_balance"]
    )


def calculate_safe_amount(
    state,
    request_date,
    base_cash_events,
    requested_amount
):
    requested_amount = Decimal(str(requested_amount))

    if requested_amount <= 0:
        return Decimal("0")

    full_plan = make_full_payment_plan(
        request_date,
        requested_amount
    )

    safe, _, _ = run_simulation(
        state,
        request_date,
        base_cash_events,
        full_plan
    )

    if safe:
        return requested_amount

    low = Decimal("0")
    high = requested_amount

    for _ in range(60):
        mid = (low + high) / Decimal("2")

        test_plan = make_full_payment_plan(
            request_date,
            mid
        )

        safe, _, _ = run_simulation(
            state,
            request_date,
            base_cash_events,
            test_plan
        )

        if safe:
            low = mid
        else:
            high = mid

    return low


def candidate_plans(context, state, base_cash_events):
    request = context["request"]

    request_date = pd.to_datetime(
        request["request_date"]
    ).date()

    desired_date = pd.to_datetime(
        request["desired_completion_date"]
    ).date()

    requested_amount = Decimal(
        str(request["requested_amount"])
    )

    methods = {
        str(x).strip().lower()
        for x in state.payment_methods
    }

    candidates = []

    if "full_payment" in methods:
        plan = make_full_payment_plan(
            request_date,
            requested_amount
        )

        candidates.append({
            "method": "full_payment",
            "payment_plan": plan,
            "spending_changes_needed": [],
            "total_paid": requested_amount,
            "end_date": request_date
        })

    if "installments" in methods:
        options = context["payment_options"]

        for _, option in options.iterrows():
            if str(option["payment_method"]).lower() != "installments":
                continue

            required_fields = [
                "first_payment_date",
                "payment_frequency_days",
                "number_of_payments",
                "payment_amount",
                "total_payable_amount"
            ]

            if any(pd.isna(option[field]) for field in required_fields):
                continue

            if not option_is_eligible(
                option,
                state.max_installment_months
            ):
                continue

            plan = make_installment_plan(option)
            end_date = plan_end_date(plan)

            if end_date > desired_date:
                continue

            candidates.append({
                "method": "installments",
                "payment_plan": plan,
                "spending_changes_needed": [],
                "total_paid": Decimal(
                    str(option["total_payable_amount"])
                ),
                "end_date": end_date,
                "payment_option_id": int(
                    option["payment_option_id"]
                )
            })

    return candidates


def validate_candidates(
    candidates,
    state,
    request_date,
    base_cash_events
):
    valid = []

    for candidate in candidates:
        safe, minimum_seen, ending_balance = run_simulation(
            state,
            request_date,
            base_cash_events,
            candidate["payment_plan"]
        )

        if not safe:
            continue

        result = dict(candidate)
        result["minimum_balance_seen"] = minimum_seen
        result["ending_balance"] = ending_balance

        valid.append(result)

    return valid