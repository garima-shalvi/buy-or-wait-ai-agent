import pandas as pd


def resolve_events(events):
    events = events.copy()

    events["include"] = True
    events["cash_effect"] = "none"
    events["resolution"] = "standalone"

    event_lookup = {
        str(row["event_id"]): index
        for index, row in events.iterrows()
    }

    for index, event in events.iterrows():
        event_type = str(
            event["event_type"]
        ).lower().strip()

        status = str(
            event["status"]
        ).lower().strip()

        direction = str(
            event["direction"]
        ).lower().strip()

        if event_type == "investment_valuation":
            events.at[index, "include"] = False
            events.at[index, "cash_effect"] = "non_cash"
            events.at[index, "resolution"] = "unrealized_valuation"
            continue

        if status in {"failed", "cancelled"}:
            events.at[index, "include"] = False
            events.at[index, "cash_effect"] = "none"
            events.at[index, "resolution"] = "failed_or_cancelled"
            continue

        if status == "pending":
            events.at[index, "include"] = False
            events.at[index, "cash_effect"] = "none"
            events.at[index, "resolution"] = "pending"
            continue

        if direction == "debit":
            events.at[index, "cash_effect"] = "expense"

        elif direction == "credit":
            if event_type == "refund":
                events.at[index, "cash_effect"] = "refund"
            else:
                events.at[index, "cash_effect"] = "income"

        elif direction == "non_cash":
            events.at[index, "include"] = False
            events.at[index, "cash_effect"] = "non_cash"

        else:
            events.at[index, "include"] = False
            events.at[index, "cash_effect"] = "none"
            events.at[index, "resolution"] = "unknown_direction"

    for index, event in events.iterrows():
        linked_id = event["linked_event_id"]

        if pd.isna(linked_id):
            continue

        linked_id = str(linked_id)

        if linked_id not in event_lookup:
            continue

        linked_index = event_lookup[linked_id]
        linked = events.loc[linked_index]

        event_status = str(
            event["status"]
        ).lower().strip()

        linked_status = str(
            linked["status"]
        ).lower().strip()

        if event_status == "settled" and linked_status in {
            "pending",
            "cancelled"
        }:
            events.at[index, "resolution"] = "settled_replacement"
            events.at[linked_index, "include"] = False
            events.at[linked_index, "cash_effect"] = "none"
            events.at[linked_index, "resolution"] = "replaced_by_settled"

    return events