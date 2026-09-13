from data_loader import load_data
from context_builder import build_context
from evidence_resolver import resolve_evidence
from evidence_normalizer import normalize_evidence
from normalizer import normalize_events
from event_resolver import resolve_events
from financial_state import build_financial_state
from forecast import get_horizon, build_cash_events
from planner import candidate_plans, validate_candidates


data = load_data()

request_id = "request_26"

context = build_context(request_id, data)

evidence = resolve_evidence(context)
evidence = normalize_evidence(
    evidence,
    context["profile"],
    data["exchange_rates"]
)

events = normalize_events(
    context["events"],
    data["profiles"],
    data["exchange_rates"]
)

resolved_events = resolve_events(events)

state = build_financial_state(
    context,
    resolved_events,
    evidence
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

print("REQUEST:", request_id)
print("REQUESTED AMOUNT:", context["request"]["requested_amount"])
print("HORIZON:", horizon)
print()

print("CANDIDATES:", len(candidates))

for candidate in candidates:
    print("\nMETHOD:", candidate["method"])
    print("PAYMENT PLAN:", candidate["payment_plan"])
    print("TOTAL PAID:", candidate["total_paid"])
    print("END DATE:", candidate["end_date"])
    print("SPENDING CHANGES:", candidate["spending_changes_needed"])

print()
print("VALID CANDIDATES:", len(valid_candidates))

for candidate in valid_candidates:
    print("\nVALID METHOD:", candidate["method"])
    print("PAYMENT PLAN:", candidate["payment_plan"])
    print("MINIMUM BALANCE:", candidate["minimum_balance_seen"])
    print("ENDING BALANCE:", candidate["ending_balance"])