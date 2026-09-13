from decimal import Decimal
import pandas as pd


FIXED_CATEGORIES = {
    "rent",
    "utilities",
    "cloud_storage",
    "streaming",
    "insurance",
    "debt",
    "education"
}

VARIABLE_CATEGORIES = {
    "groceries",
    "transport",
    "shopping",
    "dining",
    "entertainment"
}

IRREGULAR_INCOME_WORDS = {
    "freelance",
    "project",
    "contract",
    "milestone",
    "independent work"
}


def recurrence_pattern(events):
    if len(events) < 4:
        return None

    dates = sorted(
        pd.to_datetime(e["event_date"])
        for e in events
    )

    gaps = [
        (dates[i] - dates[i - 1]).days
        for i in range(1, len(dates))
    ]

    if not gaps:
        return None

    median_gap = int(round(pd.Series(gaps).median()))

    if median_gap < 5 or median_gap > 95:
        return None

    tolerance = max(
        3,
        int(round(median_gap * 0.2))
    )

    regularity = sum(
        abs(gap - median_gap) <= tolerance
        for gap in gaps
    ) / len(gaps)

    if regularity < 0.6:
        return None

    if 27 <= median_gap <= 32:
        frequency_type = "monthly"
    elif 6 <= median_gap <= 8:
        frequency_type = "weekly"
    else:
        frequency_type = "days"

    return {
        "frequency_type": frequency_type,
        "frequency_days": median_gap,
        "regularity": regularity
    }


def amount_similar(amount, reference, tolerance=0.2):
    if reference == 0:
        return amount == 0

    return (
        abs(amount - reference) / abs(reference)
        <= tolerance
    )


def description_similarity(a, b):
    a_words = set(str(a).lower().split())
    b_words = set(str(b).lower().split())

    if not a_words or not b_words:
        return 0

    return len(a_words & b_words) / len(a_words | b_words)


def same_transaction_family(event, cluster):
    description = str(event["description"]).lower()

    for existing in cluster:
        existing_description = str(
            existing["description"]
        ).lower()

        similarity = description_similarity(
            description,
            existing_description
        )

        if similarity >= 0.25:
            return True

    return False


def cluster_events(events):
    if not events:
        return []

    events = sorted(
        events,
        key=lambda e: pd.to_datetime(e["event_date"])
    )

    clusters = []

    for event in events:
        amount = Decimal(str(event["amount"]))
        placed = False

        for cluster in clusters:
            amounts = [
                Decimal(str(e["amount"]))
                for e in cluster
            ]

            median_amount = sorted(amounts)[
                len(amounts) // 2
            ]

            if not amount_similar(
                amount,
                median_amount
            ):
                continue

            if not same_transaction_family(
                event,
                cluster
            ):
                continue

            cluster.append(event)
            placed = True
            break

        if not placed:
            clusters.append([event])

    return clusters


def classify_pattern(pattern):
    category = str(
        pattern["category"]
    ).lower()

    direction = str(
        pattern["direction"]
    ).lower()

    descriptions = " ".join(
        str(e["description"]).lower()
        for e in pattern["events"]
    )

    if direction == "credit":

        if any(
            word in descriptions
            for word in IRREGULAR_INCOME_WORDS
        ):
            return "irregular_income"

        if (
            pattern["regularity"] >= 0.8
            and len(pattern["events"]) >= 4
        ):
            return "reliable_recurring"

        return "irregular_income"

    if direction == "debit":

        if category in FIXED_CATEGORIES:
            if (
                pattern["regularity"] >= 0.8
                and len(pattern["events"]) >= 4
            ):
                return "reliable_recurring"

        if category in VARIABLE_CATEGORIES:
            return "variable_spending"

        if (
            pattern["regularity"] >= 0.8
            and len(pattern["events"]) >= 5
        ):
            return "reliable_recurring"

        return "variable_spending"

    return "unclassified"


def resolve_recurrence(events):
    grouped = {}

    for event in events:
        key = (
            str(event["category"]),
            str(event["direction"])
        )

        grouped.setdefault(key, []).append(event)

    patterns = []

    for key, group in grouped.items():

        clusters = cluster_events(group)

        for cluster in clusters:

            pattern = recurrence_pattern(cluster)

            if pattern is None:
                continue

            cluster = sorted(
                cluster,
                key=lambda e: pd.to_datetime(
                    e["event_date"]
                )
            )

            amounts = [
                Decimal(str(e["amount"]))
                for e in cluster
            ]

            typical_amount = sorted(amounts)[
                len(amounts) // 2
            ]

            result = {
                "category": key[0],
                "direction": key[1],
                "events": cluster,
                "frequency_type": pattern[
                    "frequency_type"
                ],
                "frequency_days": pattern[
                    "frequency_days"
                ],
                "regularity": pattern[
                    "regularity"
                ],
                "typical_amount": typical_amount,
                "last_event": cluster[-1]
            }

            result["classification"] = classify_pattern(
                result
            )

            patterns.append(result)

    return patterns