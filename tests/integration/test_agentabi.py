"""E2E test: verify argo-proxy conversion pipeline via agentabi.

Tests all 4 inbound API formats (OpenAI Chat via codex, OpenAI Chat via
opencode, Anthropic Messages via claude_code, Google GenAI via gemini_cli)
against all available upstream models.  Each combination exercises a
different conversion path through the pipeline.

Prerequisites:
    - argo-proxy running locally (default: http://127.0.0.1:44497)
    - agentabi installed (``pip install agentabi``)
    - Agent CLIs: codex, opencode, claude, gemini

Usage:
    # Default: all agents × all models
    python tests/integration/test_agentabi.py

    # Override proxy URL
    ARGO_PROXY_URL=http://host:port python tests/integration/test_agentabi.py

    # Quick mode: 1 model per family, all agents
    ARGO_TEST_QUICK=1 python tests/integration/test_agentabi.py

    # Single agent only
    ARGO_TEST_AGENTS=codex python tests/integration/test_agentabi.py
"""

import os
import sys

from agentabi import run_sync

PROXY_URL = os.environ.get("ARGO_PROXY_URL", "http://127.0.0.1:44497")
API_KEY = os.environ.get("ARGO_API_KEY", "pding")
QUICK_MODE = os.environ.get("ARGO_TEST_QUICK", "")
AGENT_FILTER = os.environ.get("ARGO_TEST_AGENTS", "")

# ---------------------------------------------------------------------------
# Per-agent env configs — each agent hits a different inbound API format
# ---------------------------------------------------------------------------

OPENAI_ENV = {
    "OPENAI_BASE_URL": f"{PROXY_URL}/v1",
    "OPENAI_API_KEY": API_KEY,
    "CODEX_PROVIDER": "openai",
}

ANTHROPIC_ENV = {
    "ANTHROPIC_BASE_URL": PROXY_URL,
    "ANTHROPIC_API_KEY": API_KEY,
}

GOOGLE_ENV = {
    "GEMINI_API_KEY": API_KEY,
    "GOOGLE_API_KEY": API_KEY,
    "GEMINI_BASE_URL": PROXY_URL,
}

ALL_AGENTS = [
    ("codex", OPENAI_ENV),  # inbound: OpenAI Chat
    ("opencode", OPENAI_ENV),  # inbound: OpenAI Chat
    ("claude_code", ANTHROPIC_ENV),  # inbound: Anthropic Messages
    ("gemini_cli", GOOGLE_ENV),  # inbound: Google GenAI
]

# ---------------------------------------------------------------------------
# Model inventory by provider family
# ---------------------------------------------------------------------------

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

GOOGLE_MODELS = [
    "argo:gemini-2.5-flash",
    "argo:gemini-2.5-pro",
    "argo:gemini-3.5-flash",
    "argo:gemini-3.1-flash-lite",
]

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

OPENAI_REASONING_MODELS = [
    "argo:o1",
    "argo:o3",
    "argo:o3-mini",
    "argo:o4-mini",
]

# Quick mode: 1 representative per family
QUICK_MODELS = [
    "argo:gpt-5.4-nano",
    "argo:o4-mini",
    "argo:claude-haiku-4.5",
    "argo:gemini-3.5-flash",
]

# ---------------------------------------------------------------------------
# Build test matrix
# ---------------------------------------------------------------------------

if QUICK_MODE:
    ALL_MODELS = QUICK_MODELS
    print(f"=== QUICK MODE: {len(ALL_MODELS)} models ===\n")
else:
    ALL_MODELS = (
        ANTHROPIC_MODELS + GOOGLE_MODELS + OPENAI_MODELS + OPENAI_REASONING_MODELS
    )
    print(f"=== FULL MODE: {len(ALL_MODELS)} models ===\n")

if AGENT_FILTER:
    agents = [
        (name, env) for name, env in ALL_AGENTS if name in AGENT_FILTER.split(",")
    ]
else:
    agents = ALL_AGENTS

total = len(agents) * len(ALL_MODELS)
print(f"Agents: {', '.join(a for a, _ in agents)}")
print(f"Models: {len(ALL_MODELS)}")
print(f"Total combinations: {total}\n")

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

counter = [0]


def make_prompt():
    counter[0] += 1
    a, b = counter[0] * 11, counter[0] * 7
    return f"What is {a}+{b}? Reply with just the number."


passed = failed = 0
results = []

for agent, env in agents:
    for model in ALL_MODELS:
        prompt = make_prompt()
        label = f"{agent}/{model}"
        print(f"\n--- [{passed + failed + 1}/{total}] {label} ---")
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

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'=' * 80}")
print(f"{'Agent':<14} {'Model':<30} {'St':<4} {'Output'}")
print(f"{'-' * 80}")
for a, m, s, t in results:
    print(f"{a:<14} {m:<30} {s:<4} {t}")
print(f"\n=== {passed}/{passed + failed} passed ===")
sys.exit(1 if failed else 0)
