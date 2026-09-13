import pandas as pd

def resolve_events(events):
    events = events.copy()

    events["include"] = True
    events["cash_effect"] = "none"
    events["resolution"] = "standalone"

    for i, event in events.iterrows():
        event_type = str(event["event_type"]).lower()
        status = str(event["status"]).lower()
        direction = str(event["direction"]).lower()

        if event_type == "investment_valuation":
            events.at[i, "include"] = False
            events.at[i, "cash_effect"] = "non_cash"
            events.at[i, "resolution"] = "unrealized_valuation"
            continue

        if status in {"failed", "cancelled"}:
            events.at[i, "include"] = False
            events.at[i, "cash_effect"] = "none"
            events.at[i, "resolution"] = "failed_or_cancelled"
            continue

        if status == "pending":
            events.at[i, "include"] = False
            events.at[i, "cash_effect"] = "none"
            events.at[i, "resolution"] = "pending"
            continue

        if direction == "debit":
            events.at[i, "cash_effect"] = "expense"

        elif direction == "credit":
            if event_type == "refund":
                events.at[i, "cash_effect"] = "refund"
            elif event_type == "investment_sale":
                events.at[i, "cash_effect"] = "income"
            else:
                events.at[i, "cash_effect"] = "income"

        elif direction == "non_cash":
            events.at[i, "include"] = False
            events.at[i, "cash_effect"] = "non_cash"

    for i, event in events.iterrows():
        linked_id = event["linked_event_id"]

        if pd.isna(linked_id):
            continue

        linked = events[events["event_id"] == linked_id]

        if linked.empty:
            continue

        linked = linked.iloc[0]

        if (
            event["status"] == "settled"
            and str(linked["status"]).lower() in {"pending", "cancelled"}
        ):
            events.at[i, "resolution"] = "settled_replacement"
            events.at[linked.name, "include"] = False
            events.at[linked.name, "cash_effect"] = "none"
            events.at[linked.name, "resolution"] = "replaced_by_settled"

    return events

if __name__ == "__main__":
    from data_loader import load_data
    from normalizer import normalize_events

    data = load_data()

    events = normalize_events(
        data["events"],
        data["profiles"],
        data["exchange_rates"]
    )

    resolved = resolve_events(events)

    print(
    resolved[
        [
            "event_id",
            "event_type",
            "status",
            "linked_event_id",
            "direction",
            "amount_home",
            "include",
            "cash_effect",
            "resolution"
        ]
    ].head(30).to_string(index=False)
)