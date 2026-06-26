"""E2E test: verify argo-proxy conversion pipeline via agentabi.

Tests cross-format and same-format conversion paths by running real
agent CLIs against a local argo-proxy instance.  Covers all available
upstream models to detect regressions in the ConversionPipeline.

Prerequisites:
    - argo-proxy running locally (default: http://127.0.0.1:44497)
    - agentabi installed (``pip install agentabi``)
    - codex / opencode CLI tools installed

Usage:
    # Default: test all models via codex
    python tests/integration/test_agentabi.py

    # Override proxy URL
    ARGO_PROXY_URL=http://host:port python tests/integration/test_agentabi.py

    # Quick mode: only cross-format models (skip OpenAI pass-through)
    ARGO_TEST_QUICK=1 python tests/integration/test_agentabi.py
"""

import os
import sys

from agentabi import run_sync

PROXY_URL = os.environ.get("ARGO_PROXY_URL", "http://127.0.0.1:44497")
API_KEY = os.environ.get("ARGO_API_KEY", "pding")
QUICK_MODE = os.environ.get("ARGO_TEST_QUICK", "")

OPENAI_ENV = {
    "OPENAI_BASE_URL": f"{PROXY_URL}/v1",
    "OPENAI_API_KEY": API_KEY,
    "CODEX_PROVIDER": "openai",
}

# ---------------------------------------------------------------------------
# Model inventory — all unique chat models from argo upstream
# Organized by provider family and conversion path
# ---------------------------------------------------------------------------

# Cross-format: OpenAI Chat → Anthropic Messages
ANTHROPIC_MODELS = [
    "argo:claude-haiku-4.5",
    "argo:claude-sonnet-4.5",
    "argo:claude-sonnet-4.6",
    "argo:claude-opus-4.1",
    "argo:claude-opus-4.5",
    "argo:claude-opus-4.6",
    "argo:claude-opus-4.7",
    "argo:claude-opus-4.8",
]

# Cross-format: OpenAI Chat → Google GenAI
GOOGLE_MODELS = [
    "argo:gemini-2.5-flash",
    "argo:gemini-2.5-pro",
    "argo:gemini-3.5-flash",
    "argo:gemini-3.1-flash-lite",
]

# Same-format pass-through: OpenAI Chat → OpenAI Chat
OPENAI_MODELS = [
    "argo:gpt-4o",
    "argo:gpt-4.1",
    "argo:gpt-4.1-mini",
    "argo:gpt-4.1-nano",
    "argo:gpt-5",
    "argo:gpt-5-mini",
    "argo:gpt-5-nano",
    "argo:gpt-5.1",
    "argo:gpt-5.2",
    "argo:gpt-5.4",
    "argo:gpt-5.4-mini",
    "argo:gpt-5.4-nano",
    "argo:gpt-5.5",
]

# Same-format pass-through: OpenAI Chat → OpenAI Chat (reasoning models)
OPENAI_REASONING_MODELS = [
    "argo:o1",
    "argo:o3",
    "argo:o3-mini",
    "argo:o4-mini",
]

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

AGENTS = [
    ("codex", OPENAI_ENV),
]

if QUICK_MODE:
    ALL_MODELS = ANTHROPIC_MODELS + GOOGLE_MODELS
    print("=== QUICK MODE: cross-format models only ===\n")
else:
    ALL_MODELS = (
        ANTHROPIC_MODELS
        + GOOGLE_MODELS
        + OPENAI_MODELS
        + OPENAI_REASONING_MODELS
    )
    print(f"=== FULL MODE: {len(ALL_MODELS)} models ===\n")

counter = [0]


def make_prompt():
    counter[0] += 1
    a, b = counter[0] * 11, counter[0] * 7
    return f"What is {a}+{b}? Reply with just the number."


passed = failed = 0
results = []

for agent, env in AGENTS:
    for model in ALL_MODELS:
        prompt = make_prompt()
        label = f"{agent}/{model}"
        print(f"\n--- {label} ---")
        print(f"  prompt: {prompt}")
        try:
            result = run_sync(
                prompt,
                agent=agent,
                model=model,
                env=env,
                max_turns=1,
                timeout=90,
            )
            status = result.get("status", "unknown")
            text = (result.get("result_text") or "")[:80]
            print(f"  status: {status}")
            print(f"  result: {text}")
            ok = status in ("success", "completed")
            passed += ok
            failed += not ok
            results.append((agent, model, "✅" if ok else "❌", text[:30]))
        except Exception as e:
            failed += 1
            print(f"  ERROR: {e}")
            results.append((agent, model, "❌", str(e)[:30]))

print(f"\n{'=' * 80}")
print(f"{'Agent':<10} {'Model':<30} {'St':<4} {'Output'}")
print(f"{'-' * 80}")
for a, m, s, t in results:
    print(f"{a:<10} {m:<30} {s:<4} {t}")
print(f"\n=== {passed}/{passed + failed} passed ===")
sys.exit(1 if failed else 0)
