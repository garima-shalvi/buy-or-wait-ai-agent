from data_loader import load_data
from context_builder import build_context
from evidence_resolver import resolve_evidence
from evidence_normalizer import normalize_evidence
from normalizer import normalize_events
from event_resolver import resolve_events
from financial_state import build_financial_state
from forecast import get_horizon, build_cash_events
from planner import candidate_plans, validate_candidates
from decision_engine import decide

data = load_data()

request_id = "request_26"

context = build_context(request_id, data)

resolved_events = resolve_events(context["events"])

evidence_facts = resolve_evidence(context)

evidence_facts = normalize_evidence(
    evidence_facts,
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
    evidence_facts,
    data["exchange_rates"]
)

horizon = get_horizon(
    context["request"],
    context["payment_options"],
    state.max_installment_months
)

base_cash_events = build_cash_events(
    state,
    context["request"]["request_date"],
    horizon
)

candidates = candidate_plans(
    context,
    state,
    base_cash_events
)

valid_candidates = validate_candidates(
    candidates,
    state,
    context["request"]["request_date"],
    base_cash_events
)

decision = decide(
    context,
    state,
    horizon,
    base_cash_events,
    valid_candidates
)

print("REQUEST:", request_id)
print("SAFE AMOUNT:", decision["amount_safe_to_pay"])
print("STATUS:", decision["affordability_status"])
print("METHOD:", decision["recommended_payment_method"])
print("PAYMENT PLAN:", decision["payment_plan"])
print("EARLIEST FULL PAYMENT:", decision["earliest_date_for_full_payment"])
print("SPENDING CHANGES:", decision["spending_changes_needed"])
print("CANDIDATES:", len(candidates))
print("VALID CANDIDATES:", len(valid_candidates))