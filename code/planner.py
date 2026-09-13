from decimal import Decimal
import pandas as pd
from forecast import simulate, option_is_eligible
from spending_optimizer import optimize_spending_changes, format_spending_changes

def make_full_payment_plan(request_date, amount):
    return [{
        "date": pd.to_datetime(request_date).date(),
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
                first_date + pd.Timedelta(days=frequency * i)
            ).date(),
            "amount": amount,
            "payment_id": f"request_payment_{i + 1}"
        }
        for i in range(number_of_payments)
    ]

def plan_end_date(plan):
    return max(payment["date"] for payment in plan)

def plan_total(plan):
    return sum(
        (Decimal(str(payment["amount"])) for payment in plan),
        Decimal("0")
    )

def candidate_plans(context, state, base_cash_events):
    request = context["request"]
    options = context["payment_options"]

    request_date = pd.to_datetime(
        request["request_date"]
    ).date()

    desired_date = pd.to_datetime(
        request["desired_completion_date"]
    ).date()

    amount = Decimal(str(request["requested_amount"]))

    candidates = []

    if "full_payment" in state.payment_methods:
        plan = make_full_payment_plan(
            request_date,
            amount
        )

        candidates.append({
            "method": "full_payment",
            "payment_plan": plan,
            "spending_changes_needed": [],
            "spending_changes": [],
            "total_paid": amount,
            "end_date": request_date,
            "payment_option_id": None
        })

    if "installments" in state.payment_methods:
        for _, option in options.iterrows():
            if str(option["payment_method"]).lower() != "installments":
                continue

            if not option_is_eligible(
                option,
                state.max_installment_months
            ):
                continue

            required = [
                "first_payment_date",
                "payment_frequency_days",
                "number_of_payments",
                "payment_amount"
            ]

            if any(pd.isna(option[x]) for x in required):
                continue

            plan = make_installment_plan(option)
            end_date = plan_end_date(plan)

            if end_date > desired_date:
                continue

            candidates.append({
                "method": "installments",
                "payment_plan": plan,
                "spending_changes_needed": [],
                "spending_changes": [],
                "total_paid": plan_total(plan),
                "end_date": end_date,
                "payment_option_id": int(option["payment_option_id"])
            })

    return candidates

def validate_candidates(
    candidates,
    state,
    request_date,
    base_cash_events
):
    validated = []

    for candidate in candidates:
        result = simulate(
            state,
            request_date,
            base_cash_events,
            candidate["payment_plan"]
        )

        if result["safe"]:
            valid = dict(candidate)
            valid["minimum_balance_seen"] = result[
                "minimum_balance_seen"
            ]
            valid["ending_balance"] = result[
                "ending_balance"
            ]
            validated.append(valid)
            continue

        spending_results = optimize_spending_changes(
            state,
            request_date,
            base_cash_events,
            candidate["payment_plan"]
        )

        for spending_result in spending_results:
            changes = spending_result["changes"]

            valid = dict(candidate)

            valid["spending_changes"] = changes
            valid["spending_changes_needed"] = (
                format_spending_changes(changes)
            )
            valid["minimum_balance_seen"] = (
                spending_result["minimum_balance_seen"]
            )
            valid["ending_balance"] = (
                spending_result["ending_balance"]
            )

            validated.append(valid)

    return validated