from data_loader import load_data
from context_builder import build_context
from normalizer import normalize_events
from event_resolver import resolve_events
from financial_state import build_financial_state
from recurrence_resolver import resolve_recurrence

data = load_data()

context = build_context("request_26", data)

events = normalize_events(
    context["events"],
    data["profiles"],
    data["exchange_rates"]
)

resolved = resolve_events(events)

historical = []

for _, event in resolved.iterrows():
    if event["include"] and not event["amount_home"] is None:
        if event["direction"] in {"credit", "debit"}:
            historical.append({
                "event_id": event["event_id"],
                "category": event["category"],
                "direction": event["direction"],
                "description": event["description"],
                "amount": event["amount_home"],
                "event_date": event["event_date"]
            })

patterns = resolve_recurrence(historical)

for i, pattern in enumerate(patterns, 1):
    print(f"\nPATTERN {i}")
    print("CATEGORY:", pattern["category"])
    print("DIRECTION:", pattern["direction"])
    print("FREQUENCY:", pattern["frequency_type"])
    print("FREQUENCY DAYS:", pattern["frequency_days"])
    print("REGULARITY:", pattern["regularity"])
    print("TYPICAL AMOUNT:", pattern["typical_amount"])
    print("EVENTS:")

    for event in pattern["events"]:
        print(
            event["event_id"],
            event["event_date"],
            event["amount"],
            event["description"]
        )