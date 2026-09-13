from pathlib import Path
import pandas as pd

from data_loader import load_data
from context_builder import build_context
from evidence_resolver import resolve_evidence, get_usage
from evidence_normalizer import normalize_evidence, apply_evidence_to_events
from normalizer import normalize_events
from event_resolver import resolve_events
from financial_state import build_financial_state
from forecast import get_horizon, build_cash_events
from planner import candidate_plans, validate_candidates
from decision_engine import decide


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "output.csv"


def format_amount(value):
    if value is None:
        return ""

    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return ""


def format_payment_plan(plan):
    if not plan:
        return "none"

    return "|".join(
        f"{payment['date']}:{format_amount(payment['amount'])}"
        for payment in sorted(
            plan,
            key=lambda x: x["date"]
        )
    )


def format_spending_changes(changes):
    if not changes:
        return "none"

    return "|".join(str(change) for change in changes[:3])


def make_explanation(
    request,
    decision,
    state
):
    requested = float(request["requested_amount"])
    safe = float(decision["amount_safe_to_pay"])

    status = decision["affordability_status"]
    method = decision["recommended_payment_method"]

    if status == "affordable_now":
        return (
            f"{state.home_currency} {safe:.2f} of "
            f"{state.home_currency} {requested:.2f} is safe to pay now "
            f"while keeping the minimum balance protected."
        )

    if status == "affordable_with_plan":
        if method == "partial_payment":
            return (
                f"{state.home_currency} {safe:.2f} is safe initially; "
                f"the remaining amount can be completed by the planned date "
                f"without breaching the minimum balance."
            )

        if method == "installments":
            return (
                f"The full {state.home_currency} {requested:.2f} can be "
                f"completed through the selected installment plan while "
                f"protecting the minimum balance."
            )

        return (
            f"The full {state.home_currency} {requested:.2f} can be completed "
            f"with the required spending changes while protecting essentials "
            f"and the minimum balance."
        )

    if status == "affordable_later":
        date = decision.get(
            "earliest_date_for_full_payment"
        )

        if date:
            return (
                f"The full {state.home_currency} {requested:.2f} is not safe "
                f"now but is expected to be safe from {date} while protecting "
                f"the minimum balance."
            )

        return (
            f"The full {state.home_currency} {requested:.2f} is not safe now "
            f"but may become affordable later."
        )

    if safe > 0:
        return (
            f"Only {state.home_currency} {safe:.2f} is currently safe, "
            f"so the requested {state.home_currency} {requested:.2f} should "
            f"not proceed."
        )

    return (
        f"The requested {state.home_currency} {requested:.2f} cannot be "
        f"completed safely while protecting the minimum balance."
    )


def process_request(request_id, data):
    context = build_context(
        request_id,
        data
    )

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

    normalized_events = apply_evidence_to_events(
        normalized_events,
        facts,
        data["exchange_rates"]
    )

    unresolved = normalized_events[
        normalized_events["amount_home"].isna()
    ]

    if not unresolved.empty:
        ids = unresolved["event_id"].astype(str).tolist()
        raise ValueError(
            f"Unresolved financial event amounts: {ids[:10]}"
        )

    resolved_events = resolve_events(
        normalized_events
    )

    state = build_financial_state(
        context,
        resolved_events,
        facts,
        data["exchange_rates"]
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

    candidates = candidate_plans(
        context,
        state,
        cash_events
    )

    valid_candidates = validate_candidates(
        candidates,
        state,
        context["request"]["request_date"],
        cash_events
    )

    decision = decide(
        context,
        state,
        horizon,
        cash_events,
        valid_candidates
    )

    return {
        "request_id": request_id,
        "amount_safe_to_pay": format_amount(
            decision["amount_safe_to_pay"]
        ),
        "affordability_status": decision[
            "affordability_status"
        ],
        "recommended_payment_method": decision[
            "recommended_payment_method"
        ],
        "payment_plan": format_payment_plan(
            decision["payment_plan"]
        ),
        "earliest_date_for_full_payment": (
            str(decision["earliest_date_for_full_payment"])
            if decision["earliest_date_for_full_payment"]
            else ""
        ),
        "spending_changes_needed": format_spending_changes(
            decision["spending_changes_needed"]
        ),
        "decision_explanation": make_explanation(
            context["request"],
            decision,
            state
        )
    }


def main():
    data = load_data()

    request_ids = (
        data["requests"]["request_id"]
        .astype(str)
        .tolist()
    )

    results = []

    print(f"Processing {len(request_ids)} requests...")

    for number, request_id in enumerate(
        request_ids,
        start=1
    ):
        print(
            f"[{number}/{len(request_ids)}] {request_id}"
        )

        try:
            result = process_request(
                request_id,
                data
            )
            results.append(result)

        except Exception as error:
            print(
                f"ERROR {request_id}: {error}"
            )

            results.append({
                "request_id": request_id,
                "amount_safe_to_pay": "0.00",
                "affordability_status": "not_affordable",
                "recommended_payment_method": "not_recommended",
                "payment_plan": "none",
                "earliest_date_for_full_payment": "",
                "spending_changes_needed": "none",
                "decision_explanation": (
                    f"Unable to safely resolve the financial state: "
                    f"{error}"
                )
            })

    columns = [
        "request_id",
        "amount_safe_to_pay",
        "affordability_status",
        "recommended_payment_method",
        "payment_plan",
        "earliest_date_for_full_payment",
        "spending_changes_needed",
        "decision_explanation"
    ]

    output = pd.DataFrame(
        results,
        columns=columns
    )

    output.to_csv(
        OUTPUT_PATH,
        index=False
    )

    usage = get_usage()

    print()
    print("Finished.")
    print(f"Rows: {len(output)}")
    print(f"Output: {OUTPUT_PATH}")
    print(f"LLM calls: {usage['calls']}")
    print(f"Input tokens: {usage['prompt_tokens']}")
    print(f"Output tokens: {usage['completion_tokens']}")
    print(f"Total tokens: {usage['total_tokens']}")


if __name__ == "__main__":
    main()