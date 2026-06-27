"""E2E test: verify argo-proxy with Anthropic, Google, and OpenAI Responses
as *starting* formats — not just OpenAI Chat.

Each entry point is tested against cross-format and same-format upstream
models to ensure the ConversionPipeline handles all input→output paths.

Prerequisites:
    - argo-proxy running locally (default: http://127.0.0.1:44497)
    - anthropic, google-genai, openai SDKs installed

Usage:
    python tests/integration/test_multi_entry.py
"""

import os
import sys
import traceback

PROXY_URL = os.environ.get("ARGO_PROXY_URL", "http://127.0.0.1:44497")
API_KEY = os.environ.get("ARGO_API_KEY", "pding")

PROMPT = "What is 17+24? Reply with just the number."

results: list[tuple[str, str, str, str]] = []
passed = failed = 0


def record(entry: str, model: str, ok: bool, detail: str):
    global passed, failed
    tag = "✅" if ok else "❌"
    passed += ok
    failed += not ok
    results.append((entry, model, tag, detail[:50]))
    print(f"  {'OK' if ok else 'FAIL'}: {detail[:80]}")


# ---------------------------------------------------------------------------
# 1. Anthropic Messages entry (/v1/messages)
# ---------------------------------------------------------------------------


def test_anthropic_entry():
    import anthropic

    # Anthropic SDK appends /v1/messages itself, so base_url is the root
    client = anthropic.Anthropic(
        base_url=PROXY_URL,
        api_key=API_KEY,
    )

    models = [
        # same-format: Anthropic → Anthropic
        "argo:claude-haiku-4.5",
        # cross-format: Anthropic → OpenAI
        "argo:gpt-4.1-mini",
        # cross-format: Anthropic → Google
        "argo:gemini-2.5-flash",
    ]

    for model in models:
        label = f"anthropic→{model}"
        print(f"\n--- {label} ---")
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=64,
                messages=[{"role": "user", "content": PROMPT}],
            )
            block = resp.content[0] if resp.content else None
            text = str(getattr(block, "text", "")) if block else ""
            record("anthropic", model, bool(text), text)
        except Exception as e:
            record("anthropic", model, False, str(e))
            traceback.print_exc()


# ---------------------------------------------------------------------------
# 2. Google GenAI entry (/v1beta/models/{model}:generateContent)
# ---------------------------------------------------------------------------


def test_google_entry():
    from google import genai

    # Google SDK appends /v1beta/models/... itself, so base_url is the root
    client = genai.Client(
        api_key=API_KEY,
        http_options={"base_url": PROXY_URL},
    )

    models = [
        # same-format: Google → Google
        "argo:gemini-2.5-flash",
        # cross-format: Google → OpenAI
        "argo:gpt-4.1-mini",
        # cross-format: Google → Anthropic
        "argo:claude-haiku-4.5",
    ]

    for model in models:
        label = f"google→{model}"
        print(f"\n--- {label} ---")
        try:
            resp = client.models.generate_content(
                model=model,
                contents=PROMPT,
            )
            text = resp.text or ""
            record("google", model, bool(text), text)
        except Exception as e:
            record("google", model, False, str(e))
            traceback.print_exc()


# ---------------------------------------------------------------------------
# 3. OpenAI Responses entry (/v1/responses)
# ---------------------------------------------------------------------------


def test_openai_responses_entry():
    from openai import OpenAI

    client = OpenAI(
        base_url=f"{PROXY_URL}/v1",
        api_key=API_KEY,
    )

    models = [
        # same-format: OpenAI Responses → OpenAI
        "argo:gpt-4.1-mini",
        # cross-format: OpenAI Responses → Anthropic
        "argo:claude-haiku-4.5",
        # cross-format: OpenAI Responses → Google
        "argo:gemini-2.5-flash",
    ]

    for model in models:
        label = f"openai_responses→{model}"
        print(f"\n--- {label} ---")
        try:
            resp = client.responses.create(
                model=model,
                input=PROMPT,
            )
            text = resp.output_text or ""
            record("openai_resp", model, bool(text), text)
        except Exception as e:
            record("openai_resp", model, False, str(e))
            traceback.print_exc()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"=== Multi-entry E2E test against {PROXY_URL} ===\n")

    test_anthropic_entry()
    test_google_entry()
    test_openai_responses_entry()

    print(f"\n{'=' * 80}")
    print(f"{'Entry':<14} {'Model':<30} {'St':<4} {'Output'}")
    print(f"{'-' * 80}")
    for e, m, s, t in results:
        print(f"{e:<14} {m:<30} {s:<4} {t}")
    print(f"\n=== {passed}/{passed + failed} passed ===")
    sys.exit(1 if failed else 0)
