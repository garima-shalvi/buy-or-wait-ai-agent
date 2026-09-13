from decimal import Decimal
from itertools import combinations
from forecast import simulate

def event_matches_change(event_id, change_event_id):
    event_id = str(event_id)
    change_event_id = str(change_event_id)
    return (
        event_id == change_event_id or
        event_id.startswith(f"forecast:{change_event_id}:")
    )

def apply_spending_changes(base_cash_events, changes):
    adjusted = []

    for event in base_cash_events:
        updated = dict(event)
        matched = None

        for change in changes:
            if event_matches_change(updated["event_id"], change["event_id"]):
                matched = change
                break

        if matched is None:
            adjusted.append(updated)
            continue

        if matched["action"] == "stop":
            continue

        if matched["action"] == "reduce_to":
            updated["amount"] = -abs(Decimal(str(matched["amount"])))
            adjusted.append(updated)

    return adjusted

def generate_spending_changes(state):
    changes = []

    for expense in state.stoppable_expenses:
        changes.append({
            "action": "stop",
            "event_id": expense["event_id"],
            "amount": Decimal("0")
        })

    for expense in state.reducible_expenses:
        minimum = expense.get("minimum_allowed_amount")
        if minimum is None:
            minimum = Decimal("0")

        current = Decimal(str(expense["amount"]))

        if minimum < current:
            changes.append({
                "action": "reduce_to",
                "event_id": expense["event_id"],
                "amount": minimum
            })

    unique = {}

    for change in changes:
        key = (
            change["action"],
            change["event_id"],
            str(change["amount"])
        )
        unique[key] = change

    return list(unique.values())

def optimize_spending_changes(state, request_date, base_cash_events, payment_plan):
    possible_changes = generate_spending_changes(state)

    if not possible_changes:
        return []

    valid = []

    for size in range(1, min(3, len(possible_changes)) + 1):
        for combo in combinations(possible_changes, size):
            event_ids = [x["event_id"] for x in combo]

            if len(set(event_ids)) != len(event_ids):
                continue

            actions = [x["action"] for x in combo]

            if "stop" in actions and "reduce_to" in actions:
                continue

            adjusted_events = apply_spending_changes(
                base_cash_events,
                combo
            )

            result = simulate(
                state,
                request_date,
                adjusted_events,
                payment_plan
            )

            if result["safe"]:
                valid.append({
                    "changes": list(combo),
                    "minimum_balance_seen": result["minimum_balance_seen"],
                    "ending_balance": result["ending_balance"]
                })

    valid.sort(
        key=lambda x: (
            len(x["changes"]),
            sum(
                (
                    Decimal(str(change["amount"]))
                    for change in x["changes"]
                    if change["action"] == "reduce_to"
                ),
                Decimal("0")
            )
        )
    )

    return valid

def format_spending_changes(changes):
    if not changes:
        return []

    result = []

    for change in changes:
        if change["action"] == "stop":
            result.append(f"stop:{change['event_id']}")
        else:
            result.append(
                f"reduce_to:{change['event_id']}:{change['amount']}"
            )

    return result[:3]