# Phase 0a probe findings — ARGO native endpoints

Probe run: lambda5, prod env (`https://apps.inside.anl.gov/argoapi`), 17 models × variants, 204 cells total. Raw evidence in `argo_probe_raw.jsonl`.

## PDF claims that the probe contradicts

### Anthropic family

| PDF claim | Probe reality |
|---|---|
| opus47 uses `output_config` (with `thinking` schema) | Real schema: `thinking.type: adaptive` (no budget_tokens) + optional `output_config.effort ∈ {low, medium, high, xhigh, max}`. Server's own 400 message volunteered this enum. |
| opus47 silently drops temperature/top_p | Returns HTTP 400 with `` "`temperature` is deprecated for this model." `` — must strip preemptively or upstream errors |
| No other Claude model supports thinking | **opus46 and sonnet46 both accept `thinking.type: adaptive`** (200). Adaptive without budget_tokens. |
| opus41/45/sonnet45/haiku45 don't support output_config | **All of them accept `output_config.effort`** (low/med/high/none/minimal) standalone. They reject `thinking + output_config` *combined* though. |
| sonnet/haiku 45/46 enforce temperature-XOR-top_p | **Confirmed**: each alone → 200, both → 400. Applies to opus46, opus45, sonnet46, sonnet45, haiku45 (every non-opus47 model that accepts sampling). |
| opus41 enforces sampling XOR | **Probe says opus41 accepted T+P together** (HTTP 200), only opus41 in the family. Worth re-confirming. |

### OpenAI family

| PDF claim | Probe reality |
|---|---|
| gpto-series (o1/o3/o3mini/o4mini) reject temperature/top_p/max_tokens | **All accepted** by gpto3/gpto3mini/gpto4mini. argo-proxy's current `_strip_temperature_for_reasoning_models` is unnecessary for ARGO upstream. |
| gpt5-series rejects max_tokens | **gpt5/gpt5mini/gpt55 all accepted `max_tokens=64`** standalone (HTTP 200). Either ARGO transparently renames or the gateway tolerates legacy. |
| Only gpt55 has temperature locked to 1 | **gpt5, gpt5mini, AND gpt55 all reject temperature ≠ 1** with `"Only the default (1) value is supported"`. Also all three reject `top_p`. |
| gpt4o/gpt41 accept everything | **Confirmed**: all variants return 200. |

### Google family

| PDF claim | Probe reality |
|---|---|
| gemini25pro/flash work via OpenAI-compat | **Confirmed**, but the integration is fragile: `'NoneType' object is not iterable` 500s on `both_token_limits` (gemini25pro), `temperature=1` (gemini25pro), `temperature=2` (gemini25flash). Likely ARGO-side bugs, not client constraints. |

## Confirmed-correct PDF claims

- All Anthropic models require `max_tokens` (no_max_tokens → 400 across the board)
- gpt5 family rejects `top_p` (no `Only top_p X` constraint, just unsupported)
- `max_completion_tokens` universally accepted on OpenAI endpoint
- opus47 sampling fully unavailable (T/P/T+P all 400)

## Capability table draft (probe-derived)

### Anthropic models (POST `/v1/messages`)

| internal_id | thinking_param | thinking_type | output_config.effort | accepts T | accepts P | sampling_xor | max_tokens |
|---|---|---|---|---|---|---|---|
| claudeopus47 | thinking + output_config | adaptive only | low/med/high/xhigh/max | no (400) | no (400) | n/a | required |
| claudeopus46 | thinking + output_config | adaptive (opt) | low/med/high/none/minimal | yes | yes | yes (T+P → 400) | required |
| claudeopus45 | output_config only | (no adaptive) | low/med/high/none/minimal | yes | yes | yes | required |
| claudeopus41 | output_config only | (no adaptive) | low/med/high/none/minimal | yes | yes | **none (T+P → 200)** | required |
| claudesonnet46 | thinking + output_config | adaptive (opt) | low/med/high/none/minimal | yes | yes | yes | required |
| claudesonnet45 | output_config only | (no adaptive) | low/med/high/none/minimal | yes | yes | yes | required |
| claudehaiku45 | output_config only | (no adaptive) | low/med/high/none/minimal | yes | yes | yes | required |

Notes:
- "thinking + output_config" means both `thinking.type:adaptive` (alone, no budget) AND `output_config.effort:*` are accepted standalone, but **combining them** is rejected on opus45/41/sonnet45/haiku45 — only opus46 + opus47 + sonnet46 allow the combo.
- `thinking.type:enabled` is universally rejected. Adaptive is the only thinking type.
- `thinking.adaptive.budget_tokens` is universally rejected.

### OpenAI / Google models (POST `/v1/chat/completions`)

| internal_id | T allowed | T locked to | P allowed | max_tokens | max_completion_tokens |
|---|---|---|---|---|---|
| gpt4o | yes (any) | — | yes | yes | yes |
| gpto3mini | yes (any) | — | yes | yes | yes |
| gpto3 | yes (any) | — | yes | yes | yes |
| gpto4mini | yes (any) | — | yes | yes | yes |
| gpt41 | yes (any) | — | yes | yes | yes |
| gpt41mini | yes (any) | — | yes | yes | yes |
| gpt5 | only T=1 | 1 | no | yes | yes |
| gpt5mini | only T=1 | 1 | no | yes | yes |
| gpt55 | only T=1 | 1 | no | yes | yes |
| gemini25pro | yes (≠1?) | — | yes | yes | yes (no combo) |
| gemini25flash | yes (≠2?) | — | yes | yes | yes |

Gemini caveat: the 500s look like ARGO-side bugs. Worth a second probe pass or upstream report; current dispatch should not assume those parameter values are forbidden.

## Implications for the shim layer

- `argo_anthropic`:
    - Rewrite `_normalize_thinking` to:
        - drop `thinking.type:enabled` → coerce to `adaptive` (no budget), OR pop entirely if model rejects standalone thinking
        - for opus47 specifically, also translate any client-side `budget_tokens` → bucketed `output_config.effort`
        - drop any `output_config + thinking` combo when model is in {opus45, opus41, sonnet45, haiku45}
    - Add `_enforce_sampling_xor` for opus46, sonnet46, sonnet45, haiku45 (drop top_p if both present)
    - Add `_strip_unsupported_sampling` for opus47 only (the others actually accept sampling)
- `argo_openai_chat`:
    - `_strip_reasoning_params` is **not needed** for gpto-series against ARGO. Remove the dispatch.py helper entirely.
    - `_upgrade_max_tokens` is **not needed** for gpt5-series against ARGO either — upstream accepts max_tokens. Removing the helper is correct unless we want to be defensive for non-ARGO openai-compat backends.
    - **Add `_clamp_temperature` for entire gpt5 family** (gpt5, gpt5mini, gpt55), and `_strip_top_p` for the same set.
- No transform needed for Gemini yet; flag the 500s upstream.

## Suggested next steps

1. Commit `tools/probe_argo.py` + `tools/argo_probe_out/argo_capability_matrix.md` + `argo_probe_raw.jsonl` (raw is small at 8.9KB initially, full ~150KB).
2. Mirror the matrix to `docs_{en,zh}/docs/argo_capability_matrix.md` as the user-facing reference.
3. Re-run probe for `claudeopus41 / temperature_and_top_p` and the gemini 500s to rule out transient errors.
4. Move to Phase 0b: encode this table as `capabilities.yaml` in llm-rosetta.
