# LLM Usage Report

## Final full-dataset run

The final run processed the complete evaluation dataset of 250 requests.

| Metric | Value |
|---|---:|
| Requests processed | 250 |
| Total LLM calls | 209 |
| Input tokens | 86,107 |
| Output tokens | 43,711 |
| Total tokens | 129,818 |
| Average total tokens/request | 519.27 |

## Models

### Text evidence extraction

- Provider: Groq
- Model: `openai/gpt-oss-20b`
- Purpose: extraction of financial evidence from relevant messages

### Image evidence extraction

- Provider: Groq
- Model: `qwen/qwen3.6-27b`
- Purpose: extraction of financial evidence from relevant images

The implementation caches repeated message and image evidence within a full run so the same evidence is not unnecessarily sent to the model multiple times.

## Token accounting

The final runner recorded aggregate token usage for the complete 250-request run:

- Input tokens: 86,107
- Output tokens: 43,711
- Total tokens: 129,818

The final terminal run did not persist a per-model token breakdown separately, so per-model token values are not fabricated.

## Estimated cost

Using the Groq model prices applicable to the final run:

- `openai/gpt-oss-20b`: $0.075 per million input tokens and $0.30 per million output tokens
- `qwen/qwen3.6-27b`: $0.60 per million input tokens and $3.00 per million output tokens

Because the final run retained aggregate rather than per-model token usage, an exact mixed-model cost cannot be reconstructed without another full run.

Using the aggregate token totals, the theoretical cost range is approximately:

- Minimum: $0.0196
- Maximum: $0.1828
- Approximate range per request: $0.000078–$0.000731

These figures are provided as an estimate/range rather than as fabricated exact per-model costs.

## Decision architecture

The LLMs are used only for evidence extraction from unstructured text and images.

The financial decision itself is deterministic:

1. Build request context.
2. Resolve relevant text and image evidence.
3. Normalize currencies and evidence.
4. Resolve event lifecycle and duplicate/linked events.
5. Build the financial state.
6. Forecast the user's balance over a dynamic safety horizon.
7. Generate candidate payment plans.
8. Validate candidate plans deterministically.
9. Select the best valid plan.
10. Generate the final explanation from the resulting decision.

This separation ensures that the LLM extracts evidence while deterministic code makes the affordability decision.

## Final run result

The complete dataset run successfully generated predictions for all 250 requests.

Output status counts:

- `affordable_now`: 57
- `affordable_with_plan`: 64
- `affordable_later`: 63
- `not_affordable`: 66

Total: 250 requests.
