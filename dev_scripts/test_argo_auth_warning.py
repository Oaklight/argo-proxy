#!/usr/bin/env python3
"""Test ARGO authentication warning detection.

Uses localhost:44500 (argo-proxy --username-passthrough, tunneled to
pding-docker-build) as a real upstream.  When a request is sent with an
invalid API key, the upstream ARGO returns a response containing the
AUTHENTICATION NOTICE warning.  Our detection code should catch it.

Usage:
    conda run -n argo python dev_scripts/test_argo_auth_warning.py
"""

import asyncio
import json
import sys
import time

import aiohttp

UPSTREAM = "http://localhost:44500"
VALID_USER = "pding"
FAKE_USER = f"bogus_{int(time.time())}"

# -----------------------------------------------------------------------
# 1. Unit tests — pure function tests (no network)
# -----------------------------------------------------------------------


def test_unit():
    from argoproxy.utils.misc import (
        check_response_for_argo_warning,
        contains_argo_auth_warning,
        extract_text_from_response,
    )

    print("=== Unit Tests ===")

    # contains_argo_auth_warning
    assert contains_argo_auth_warning(
        "⚠️ **IMPORTANT AUTHENTICATION NOTICE FROM ARGO** ⚠️"
    )
    assert contains_argo_auth_warning("some text AUTHENTICATION NOTICE FROM ARGO end")
    assert not contains_argo_auth_warning("Hello world")
    assert not contains_argo_auth_warning("")
    print("  [PASS] contains_argo_auth_warning")

    # extract_text_from_response
    assert (
        extract_text_from_response(
            {"choices": [{"message": {"content": "hi"}}]}, "openai"
        )
        == "hi"
    )
    assert (
        extract_text_from_response(
            {"choices": [{"delta": {"content": "hi"}}]}, "openai"
        )
        == "hi"
    )
    assert (
        extract_text_from_response({"content": [{"text": "hi"}]}, "anthropic") == "hi"
    )
    assert extract_text_from_response({"response": "hi"}, "legacy") == "hi"
    assert extract_text_from_response({}, "openai") == ""
    assert extract_text_from_response({"choices": []}, "openai") == ""
    print("  [PASS] extract_text_from_response")

    # check_response_for_argo_warning
    warn_data = {
        "choices": [
            {
                "message": {
                    "content": "⚠️ AUTHENTICATION NOTICE FROM ARGO ⚠️ blah"
                }
            }
        ]
    }
    assert check_response_for_argo_warning(warn_data, "openai")
    assert not check_response_for_argo_warning(
        {"choices": [{"message": {"content": "ok"}}]}, "openai"
    )
    print("  [PASS] check_response_for_argo_warning")

    print("  All unit tests passed!\n")


# -----------------------------------------------------------------------
# 2. Upstream validation test (validate_user_async)
# -----------------------------------------------------------------------


async def test_validate_user():
    from argoproxy.utils.transports import validate_user_async

    chat_url = f"{UPSTREAM}/v1/chat/completions"
    print("=== Upstream User Validation ===")

    # Valid user
    try:
        result = await validate_user_async(chat_url, VALID_USER, timeout=15)
        status = "PASS" if result else "FAIL (returned False for valid user)"
        print(f"  [{status}] validate_user_async('{VALID_USER}')")
    except Exception as e:
        print(f"  [FAIL] validate_user_async('{VALID_USER}'): {e}")

    # Invalid user
    try:
        result = await validate_user_async(chat_url, FAKE_USER, timeout=15)
        status = "PASS" if not result else "FAIL (returned True for fake user)"
        print(f"  [{status}] validate_user_async('{FAKE_USER}')")
    except Exception as e:
        print(f"  [FAIL] validate_user_async('{FAKE_USER}'): {e}")

    print()


# -----------------------------------------------------------------------
# 3. Runtime detection — non-streaming
# -----------------------------------------------------------------------


async def test_runtime_non_streaming():
    from argoproxy.utils.misc import contains_argo_auth_warning

    print("=== Runtime Detection (Non-Streaming) ===")

    # Send request with valid user — should succeed
    payload = {
        "model": "gpt4olatest",
        "messages": [{"role": "user", "content": "say ok"}],
        "max_tokens": 5,
    }

    async with aiohttp.ClientSession() as session:
        # Valid user via bearer
        try:
            async with session.post(
                f"{UPSTREAM}/v1/chat/completions",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {VALID_USER}",
                },
            ) as resp:
                data = await resp.json()
                text = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                has_warning = contains_argo_auth_warning(text)
                print(
                    f"  [{'FAIL' if has_warning else 'PASS'}] Valid user non-stream: "
                    f"status={resp.status}, warning={has_warning}, text={text[:80]}"
                )
        except Exception as e:
            print(f"  [FAIL] Valid user non-stream: {e}")

        # Invalid user via bearer — should trigger warning in upstream response
        try:
            async with session.post(
                f"{UPSTREAM}/v1/chat/completions",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {FAKE_USER}",
                },
            ) as resp:
                data = await resp.json()
                text = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                has_warning = contains_argo_auth_warning(text)
                print(
                    f"  [{'PASS' if has_warning else 'FAIL'}] Fake user non-stream: "
                    f"status={resp.status}, warning={has_warning}, text={text[:80]}"
                )
        except Exception as e:
            print(f"  [FAIL] Fake user non-stream: {e}")

    print()


# -----------------------------------------------------------------------
# 4. Runtime detection — streaming
# -----------------------------------------------------------------------


async def test_runtime_streaming():
    from argoproxy.utils.misc import contains_argo_auth_warning

    print("=== Runtime Detection (Streaming) ===")

    payload = {
        "model": "gpt4olatest",
        "messages": [{"role": "user", "content": "say ok"}],
        "max_tokens": 5,
        "stream": True,
    }

    async with aiohttp.ClientSession() as session:
        # Valid user streaming
        try:
            async with session.post(
                f"{UPSTREAM}/v1/chat/completions",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {VALID_USER}",
                },
            ) as resp:
                body = await resp.read()
                text = body.decode("utf-8", errors="replace")
                has_warning = contains_argo_auth_warning(text)
                print(
                    f"  [{'FAIL' if has_warning else 'PASS'}] Valid user stream: "
                    f"status={resp.status}, warning={has_warning}"
                )
        except Exception as e:
            print(f"  [FAIL] Valid user stream: {e}")

        # Invalid user streaming
        try:
            async with session.post(
                f"{UPSTREAM}/v1/chat/completions",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {FAKE_USER}",
                },
            ) as resp:
                body = await resp.read()
                text = body.decode("utf-8", errors="replace")
                has_warning = contains_argo_auth_warning(text)
                print(
                    f"  [{'PASS' if has_warning else 'FAIL'}] Fake user stream: "
                    f"status={resp.status}, warning={has_warning}"
                )
        except Exception as e:
            print(f"  [FAIL] Fake user stream: {e}")

    print()


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------


async def main():
    test_unit()

    # Check upstream availability
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{UPSTREAM}/health", timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    print(f"Upstream {UPSTREAM} not healthy (status {resp.status})")
                    sys.exit(1)
    except Exception as e:
        print(f"Cannot reach upstream {UPSTREAM}: {e}")
        print("Make sure SSH tunnel to pding-docker-build is active.")
        sys.exit(1)

    print(f"Upstream {UPSTREAM} is healthy.")
    print(f"Using valid user: {VALID_USER}")
    print(f"Using fake user:  {FAKE_USER}\n")

    await test_validate_user()
    await test_runtime_non_streaming()
    await test_runtime_streaming()

    print("=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
