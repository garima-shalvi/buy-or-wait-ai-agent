from pathlib import Path
import base64
import json
import os
import re

import pandas as pd
from groq import Groq


EVIDENCE_TYPES = {
    "income",
    "expense",
    "expense_change",
    "refund",
    "transfer",
    "payment_status",
    "commitment",
    "investment",
    "other"
}

BASES = {
    "actual",
    "confirmed",
    "scheduled",
    "pending",
    "estimated",
    "forecast",
    "unknown"
}

FINANCIAL_EFFECTS = {
    "income",
    "expense",
    "refund",
    "transfer",
    "investment",
    "none"
}

TEXT_MODEL = "openai/gpt-oss-20b"
VISION_MODEL = "qwen/qwen3.6-27b"

client = Groq(api_key=os.environ["GROQ_API_KEY"])

IMAGE_DIR = (
    Path(__file__).resolve().parent.parent
    / "dataset"
    / "media"
    / "images"
)

USAGE = {
    "calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "models": {}
}


def _record_usage(response, model):
    USAGE["calls"] += 1

    usage = getattr(response, "usage", None)

    if usage is None:
        return

    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(
        getattr(usage, "completion_tokens", 0) or 0
    )
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0)

    USAGE["prompt_tokens"] += prompt_tokens
    USAGE["completion_tokens"] += completion_tokens
    USAGE["total_tokens"] += total_tokens

    if model not in USAGE["models"]:
        USAGE["models"][model] = {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }

    USAGE["models"][model]["calls"] += 1
    USAGE["models"][model]["prompt_tokens"] += prompt_tokens
    USAGE["models"][model]["completion_tokens"] += completion_tokens
    USAGE["models"][model]["total_tokens"] += total_tokens


def get_usage():
    return {
        "calls": USAGE["calls"],
        "prompt_tokens": USAGE["prompt_tokens"],
        "completion_tokens": USAGE["completion_tokens"],
        "total_tokens": USAGE["total_tokens"],
        "models": {
            model: values.copy()
            for model, values in USAGE["models"].items()
        }
    }


def empty_fact():
    return {
        "evidence_type": "other",
        "event_id": None,
        "amount": None,
        "currency": None,
        "amount_basis": "unknown",
        "financial_effect": "none",
        "effective_date": None,
        "as_of_date": None,
        "source_timestamp": None,
        "confidence": 0.0,
        "applies_to_type": None,
        "applies_to_key": None,
        "summary": ""
    }


def clean_fact(fact):
    result = empty_fact()

    if not isinstance(fact, dict):
        return result

    for key in result:
        if key in fact:
            result[key] = fact[key]

    evidence_type = str(
        result["evidence_type"]
    ).lower().strip()

    if evidence_type not in EVIDENCE_TYPES:
        evidence_type = "other"

    result["evidence_type"] = evidence_type

    basis = str(
        result["amount_basis"]
    ).lower().strip()

    if basis not in BASES:
        basis = "unknown"

    result["amount_basis"] = basis

    effect = str(
        result["financial_effect"]
    ).lower().strip()

    if effect not in FINANCIAL_EFFECTS:
        effect = "none"

    result["financial_effect"] = effect

    if result["amount"] is not None:
        try:
            result["amount"] = float(result["amount"])
        except (TypeError, ValueError):
            result["amount"] = None

    try:
        result["confidence"] = float(result["confidence"])
        result["confidence"] = max(
            0.0,
            min(1.0, result["confidence"])
        )
    except (TypeError, ValueError):
        result["confidence"] = 0.0

    if result["currency"] is not None:
        result["currency"] = str(
            result["currency"]
        ).upper().strip()

    result["summary"] = str(
        result["summary"] or ""
    ).strip()

    return result


def extract_json_text(content):
    if not content:
        raise ValueError("LLM returned an empty response")

    content = str(content).strip()

    content = re.sub(
        r"<think>.*?</think>",
        "",
        content,
        flags=re.DOTALL | re.IGNORECASE
    ).strip()

    if re.search(
        r"<think>",
        content,
        flags=re.IGNORECASE
    ):
        raise ValueError(
            "Model response was truncated inside a reasoning block"
        )

    content = re.sub(
        r"</think>",
        "",
        content,
        flags=re.IGNORECASE
    ).strip()

    fenced = re.search(
        r"```(?:json)?\s*(.*?)\s*```",
        content,
        flags=re.DOTALL | re.IGNORECASE
    )

    if fenced:
        content = fenced.group(1).strip()

    try:
        json.loads(content)
        return content
    except json.JSONDecodeError:
        pass

    object_match = re.search(
        r"\{.*\}",
        content,
        flags=re.DOTALL
    )

    if object_match:
        candidate = object_match.group(0)

        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    array_match = re.search(
        r"\[.*\]",
        content,
        flags=re.DOTALL
    )

    if array_match:
        candidate = array_match.group(0)

        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    raise ValueError(
        "Could not find valid JSON in model response"
    )


def parse_json_response(content):
    json_text = extract_json_text(content)
    data = json.loads(json_text)

    if isinstance(data, dict):
        facts = data.get("facts", [])
    elif isinstance(data, list):
        facts = data
    else:
        raise ValueError(
            "JSON response must contain a facts list"
        )

    if not isinstance(facts, list):
        raise ValueError("'facts' must be a list")

    return [
        clean_fact(fact)
        for fact in facts
    ]


def text_prompt(message_text):
    return f"""
Extract financial evidence from the following message.

Return ONLY valid JSON.
The response MUST contain exactly:
{{"facts":[{{"evidence_type":"income|expense|expense_change|refund|transfer|payment_status|commitment|investment|other","event_id":null,"amount":null,"currency":null,"amount_basis":"actual|confirmed|scheduled|pending|estimated|forecast|unknown","financial_effect":"income|expense|refund|transfer|investment|none","effective_date":null,"as_of_date":null,"source_timestamp":null,"confidence":0.0,"applies_to_type":null,"applies_to_key":null,"summary":""}}]}}

Extract only facts supported by the message.
Do not invent amounts, dates, currencies, event IDs, or certainty.
Do not use transaction references as event_id.
Use null when information is missing.
Amounts must be numeric without currency symbols.
Dates must use YYYY-MM-DD when possible.
Confidence must be between 0 and 1.
Keep each summary under 15 words.

Message:
{message_text}
""".strip()


def image_prompt(image_id):
    return f"""
Extract the PRIMARY financial transaction represented by this image.

Return ONLY valid JSON.
The response MUST contain exactly:
{{"facts":[{{"evidence_type":"income|expense|expense_change|refund|transfer|payment_status|commitment|investment|other","event_id":null,"amount":null,"currency":null,"amount_basis":"actual|confirmed|scheduled|pending|estimated|forecast|unknown","financial_effect":"income|expense|refund|transfer|investment|none","effective_date":null,"as_of_date":null,"source_timestamp":null,"confidence":0.0,"applies_to_type":null,"applies_to_key":null,"summary":""}}]}}

IMPORTANT:
- Return ONE primary financial fact only.
- For an invoice or bill, use the final transaction amount, total payable amount, or outstanding balance that represents the actual financial transaction.
- Do NOT return taxable value, subtotal, CGST, SGST, VAT, discounts, fees, or other component amounts as separate facts.
- For a receipt showing total and amount paid, use the amount that represents the relevant financial transaction.
- For income documents, use the actual net/received income when clearly shown.
- If the image contains multiple monetary values for the same transaction, choose the single amount that best represents the actual financial effect.
- Do not invent information.
- Do not invent event IDs.
- Dates must use YYYY-MM-DD when possible.
- Confidence must be between 0 and 1.
- Keep the summary under 15 words.

Image ID:
{image_id}
""".strip()


def extract_text_evidence(message_text, attempt=0):
    max_tokens = 700 if attempt == 0 else 900

    try:
        response = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": text_prompt(message_text)
                }
            ],
            temperature=0,
            max_tokens=max_tokens,
            reasoning_effort="low",
            reasoning_format="hidden"
        )

        _record_usage(response, TEXT_MODEL)

        return parse_json_response(
            response.choices[0].message.content
        )

    except Exception as error:
        if attempt == 0:
            return extract_text_evidence(
                message_text,
                attempt=1
            )

        fallback = empty_fact()
        fallback["summary"] = (
            f"extraction failed: {error}"
        )
        return [fallback]


def extract_image_evidence(image_id, attempt=0):
    image_path = IMAGE_DIR / f"{image_id}.png"

    if not image_path.exists():
        fallback = empty_fact()
        fallback["summary"] = (
            f"image file not found: {image_id}"
        )
        return [fallback]

    max_tokens = 700 if attempt == 0 else 900

    try:
        image_bytes = image_path.read_bytes()
        image_data = base64.b64encode(
            image_bytes
        ).decode("utf-8")

        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": image_prompt(image_id)
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    "data:image/png;base64,"
                                    + image_data
                                )
                            }
                        }
                    ]
                }
            ],
            temperature=0,
            max_tokens=max_tokens,
            reasoning_effort="none",
            reasoning_format="hidden"
        )

        _record_usage(response, VISION_MODEL)

        return parse_json_response(
            response.choices[0].message.content
        )

    except Exception as error:
        if attempt == 0:
            return extract_image_evidence(
                image_id,
                attempt=1
            )

        fallback = empty_fact()
        fallback["summary"] = (
            f"extraction failed: {error}"
        )
        return [fallback]


def resolve_text_evidence(context):
    facts = []

    valid_event_ids = {
        str(event_id)
        for event_id in context["events"]["event_id"]
    }

    for _, message in context["messages"].iterrows():
        message_text = str(
            message.get("message_text", "")
        )

        if not message_text.strip():
            continue

        extracted = extract_text_evidence(
            message_text
        )

        related_event_id = None

        if pd_value(
            message.get("related_event_id")
        ):
            candidate = str(
                message["related_event_id"]
            )

            if candidate in valid_event_ids:
                related_event_id = candidate

        for index, fact in enumerate(extracted):
            fact = clean_fact(fact)

            fact["source"] = "messages"
            fact["source_ref"] = str(
                message["message_id"]
            )
            fact["fact_id"] = (
                f"{message['message_id']}_fact_{index}"
            )

            fact["event_id"] = related_event_id

            if pd_value(message.get("request_id")):
                fact["applies_to_type"] = "request"
                fact["applies_to_key"] = str(
                    message["request_id"]
                )

            if pd_value(
                message.get("effective_date")
            ):
                fact["effective_date"] = str(
                    message["effective_date"]
                )

            if pd_value(message.get("sent_at")):
                fact["source_timestamp"] = str(
                    message["sent_at"]
                )

            facts.append(fact)

    return facts


def resolve_image_evidence(context):
    facts = []

    valid_event_ids = {
        str(event_id)
        for event_id in context["events"]["event_id"]
    }

    for _, image in context["images"].iterrows():
        image_id = str(image["image_id"])

        extracted = extract_image_evidence(
            image_id
        )

        related_event_id = None

        if pd_value(
            image.get("related_event_id")
        ):
            candidate = str(
                image["related_event_id"]
            )

            if candidate in valid_event_ids:
                related_event_id = candidate

        if len(extracted) > 1:
            extracted = [
                fact for fact in extracted
                if fact.get("amount") is not None
            ][:1]

        for index, fact in enumerate(extracted):
            fact = clean_fact(fact)

            fact["source"] = "images"
            fact["source_ref"] = image_id
            fact["fact_id"] = (
                f"{image_id}_fact_{index}"
            )

            fact["event_id"] = related_event_id

            if pd_value(image.get("request_id")):
                fact["applies_to_type"] = "request"
                fact["applies_to_key"] = str(
                    image["request_id"]
                )

            facts.append(fact)

    return facts


def pd_value(value):
    if value is None:
        return False

    try:
        return not pd.isna(value)
    except (TypeError, ValueError):
        return True


def resolve_evidence(context):
    text_facts = resolve_text_evidence(context)
    image_facts = resolve_image_evidence(context)

    return text_facts + image_facts