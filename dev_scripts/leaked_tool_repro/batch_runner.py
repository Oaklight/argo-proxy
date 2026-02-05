#!/usr/bin/env python3
"""
Batch runner for leaked tool call reproduction tests.

This script runs all reproduction cases (1-5) multiple times across multiple
Claude models and collects statistics on how often malformed/leaked tool calls
occur in the responses.

Usage:
    python batch_runner.py [--runs N] [--output-dir DIR]

Models tested:
    - claudeopus45
    - claudeopus41
    - claudeopus4
    - claudehaiku45
    - claudesonnet45
    - claudesonnet4
    - claudesonnet37
    - claudesonnet35v2
"""

import argparse
import json
import os
import re
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

# Configuration
ARGO_API_URL = os.getenv(
    "ARGO_API_URL", "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/"
)

# Models to test
MODELS = [
    "claudeopus45",
    "claudeopus41",
    "claudeopus4",
    "claudehaiku45",
    "claudehaiku35",
    "claudesonnet45",
    "claudesonnet4",
    "claudesonnet37",
    "claudesonnet35v2",
]

# Test cases (log files)
CASE_FILES = {
    1: "leaked_tool_20260128_171422_165810.json",
    2: "leaked_tool_20260128_171653_513513.json",
    3: "leaked_tool_20260131_114729_223329.json",
    4: "leaked_tool_20260131_114941_897350.json",
    5: "leaked_tool_20260131_115028_795330.json",
}

# Patterns to detect leaked tool calls in text content
LEAKED_TOOL_PATTERNS = [
    # Dict-like tool call pattern
    r"\{'id':\s*'toolu_",
    # Tool use type indicator
    r"'type':\s*'tool_use'",
    # Tool name pattern
    r"'name':\s*'(bash|read|write|edit|glob|grep|webfetch|task|question|todowrite|todoread|skill)'",
    # XML-style tool tags (some models might output these)
    r"<tool_use>",
    r"</tool_use>",
    # Function call patterns
    r"<function_call>",
    r"</function_call>",
]


def load_request_body(case_num: int, model: str) -> dict:
    """Load the request body from a case file and override the model."""
    script_dir = Path(__file__).parent
    log_file = script_dir / CASE_FILES[case_num]

    with open(log_file, "r", encoding="utf-8") as f:
        log_data = json.load(f)

    request = log_data["request"]
    request["model"] = model
    return request


def send_request(request_body: dict, timeout: float = 180.0) -> dict:
    """Send the request and return the response."""
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.post(
            ARGO_API_URL,
            json=request_body,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()


def detect_leaked_tool_call(response: dict) -> dict[str, Any]:
    """
    Detect if the response contains leaked tool calls in text content.

    ARGO API format: {"response": {"content": "...", "tool_calls": [...]}}

    Returns a dict with detection results:
    - leaked: bool - whether a leak was detected
    - patterns_matched: list of patterns that matched
    - text_content: the text content that was analyzed
    - tool_calls_count: number of proper tool_calls in the response
    """
    result = {
        "leaked": False,
        "patterns_matched": [],
        "text_content": "",
        "tool_calls_count": 0,
    }

    # ARGO API format: {"response": {"content": "...", "tool_calls": [...]}}
    if "response" not in response:
        return result

    resp = response["response"]
    content = resp.get("content", "")
    tool_calls = resp.get("tool_calls", [])

    # Handle None content
    if content is None:
        content = ""

    result["text_content"] = content
    result["tool_calls_count"] = len(tool_calls) if tool_calls else 0

    # Check for leaked patterns in text content
    for pattern in LEAKED_TOOL_PATTERNS:
        if re.search(pattern, content):
            result["leaked"] = True
            result["patterns_matched"].append(pattern)

    return result


def run_single_test(
    case_num: int, model: str, run_num: int, output_dir: Path
) -> dict[str, Any]:
    """
    Run a single test case and return the result.

    Returns a dict with:
    - case: int
    - model: str
    - run: int
    - success: bool
    - leaked: bool
    - error: str or None
    - response_file: str (path to saved response)
    """
    result = {
        "case": case_num,
        "model": model,
        "run": run_num,
        "success": False,
        "leaked": False,
        "error": None,
        "response_file": None,
        "patterns_matched": [],
        "tool_calls_count": 0,
    }

    try:
        # Load and send request
        request_body = load_request_body(case_num, model)
        response = send_request(request_body)

        # Detect leaked tool calls
        detection = detect_leaked_tool_call(response)
        result["success"] = True
        result["leaked"] = detection["leaked"]
        result["patterns_matched"] = detection["patterns_matched"]
        result["tool_calls_count"] = detection["tool_calls_count"]

        # Save response to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"case{case_num}_{model}_run{run_num}_{timestamp}.json"
        response_file = output_dir / filename

        with open(response_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "case": case_num,
                    "model": model,
                    "run": run_num,
                    "timestamp": datetime.now().isoformat(),
                    "request": request_body,
                    "response": response,
                    "detection": detection,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        result["response_file"] = str(response_file)

    except httpx.HTTPStatusError as e:
        result["error"] = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except httpx.RequestError as e:
        result["error"] = f"Request error: {str(e)}"
    except FileNotFoundError as e:
        result["error"] = f"File not found: {str(e)}"
    except json.JSONDecodeError as e:
        result["error"] = f"JSON decode error: {str(e)}"
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"

    return result


def print_progress(case_num: int, model: str, run_num: int, total_runs: int) -> None:
    """Print progress indicator."""
    print(f"  Case {case_num} | {model:20s} | Run {run_num}/{total_runs}", end="")
    sys.stdout.flush()


def print_result(result: dict) -> None:
    """Print result of a single test."""
    if result["success"]:
        if result["leaked"]:
            print(f" | ⚠️  LEAKED (patterns: {len(result['patterns_matched'])})")
        else:
            print(f" | ✓ OK (tool_calls: {result['tool_calls_count']})")
    else:
        print(f" | ✗ ERROR: {result['error'][:50]}")


def generate_statistics(results: list[dict]) -> dict:
    """Generate statistics from all test results."""
    stats = {
        "total_runs": len(results),
        "successful_runs": 0,
        "failed_runs": 0,
        "leaked_count": 0,
        "by_model": {},
        "by_case": {},
        "by_model_and_case": {},
    }

    for result in results:
        model = result["model"]
        case = result["case"]
        key = f"{model}_case{case}"

        # Initialize model stats
        if model not in stats["by_model"]:
            stats["by_model"][model] = {
                "total": 0,
                "success": 0,
                "failed": 0,
                "leaked": 0,
            }

        # Initialize case stats
        if case not in stats["by_case"]:
            stats["by_case"][case] = {
                "total": 0,
                "success": 0,
                "failed": 0,
                "leaked": 0,
            }

        # Initialize model+case stats
        if key not in stats["by_model_and_case"]:
            stats["by_model_and_case"][key] = {
                "model": model,
                "case": case,
                "total": 0,
                "success": 0,
                "failed": 0,
                "leaked": 0,
            }

        # Update counts
        stats["by_model"][model]["total"] += 1
        stats["by_case"][case]["total"] += 1
        stats["by_model_and_case"][key]["total"] += 1

        if result["success"]:
            stats["successful_runs"] += 1
            stats["by_model"][model]["success"] += 1
            stats["by_case"][case]["success"] += 1
            stats["by_model_and_case"][key]["success"] += 1

            if result["leaked"]:
                stats["leaked_count"] += 1
                stats["by_model"][model]["leaked"] += 1
                stats["by_case"][case]["leaked"] += 1
                stats["by_model_and_case"][key]["leaked"] += 1
        else:
            stats["failed_runs"] += 1
            stats["by_model"][model]["failed"] += 1
            stats["by_case"][case]["failed"] += 1
            stats["by_model_and_case"][key]["failed"] += 1

    return stats


def print_statistics(stats: dict) -> None:
    """Print formatted statistics."""
    print("\n" + "=" * 80)
    print("STATISTICS SUMMARY")
    print("=" * 80)

    print(f"\nTotal runs: {stats['total_runs']}")
    print(f"Successful: {stats['successful_runs']}")
    print(f"Failed: {stats['failed_runs']}")
    print(f"Leaked tool calls detected: {stats['leaked_count']}")

    if stats["successful_runs"] > 0:
        leak_rate = stats["leaked_count"] / stats["successful_runs"] * 100
        print(f"Overall leak rate: {leak_rate:.1f}%")

    # By model
    print("\n" + "-" * 80)
    print("BY MODEL")
    print("-" * 80)
    print(
        f"{'Model':<20} {'Total':>8} {'Success':>8} {'Failed':>8} {'Leaked':>8} {'Rate':>8}"
    )
    print("-" * 80)

    for model in MODELS:
        if model in stats["by_model"]:
            m = stats["by_model"][model]
            rate = m["leaked"] / m["success"] * 100 if m["success"] > 0 else 0
            print(
                f"{model:<20} {m['total']:>8} {m['success']:>8} {m['failed']:>8} {m['leaked']:>8} {rate:>7.1f}%"
            )

    # By case
    print("\n" + "-" * 80)
    print("BY CASE")
    print("-" * 80)
    print(
        f"{'Case':<20} {'Total':>8} {'Success':>8} {'Failed':>8} {'Leaked':>8} {'Rate':>8}"
    )
    print("-" * 80)

    for case in sorted(stats["by_case"].keys()):
        c = stats["by_case"][case]
        rate = c["leaked"] / c["success"] * 100 if c["success"] > 0 else 0
        print(
            f"Case {case:<15} {c['total']:>8} {c['success']:>8} {c['failed']:>8} {c['leaked']:>8} {rate:>7.1f}%"
        )

    # Detailed by model and case
    print("\n" + "-" * 80)
    print("BY MODEL AND CASE (Leak Rate)")
    print("-" * 80)

    # Header
    header = f"{'Model':<20}"
    for case in sorted(CASE_FILES.keys()):
        header += f" {'Case ' + str(case):>10}"
    print(header)
    print("-" * 80)

    for model in MODELS:
        row = f"{model:<20}"
        for case in sorted(CASE_FILES.keys()):
            key = f"{model}_case{case}"
            if key in stats["by_model_and_case"]:
                mc = stats["by_model_and_case"][key]
                if mc["success"] > 0:
                    rate = mc["leaked"] / mc["success"] * 100
                    row += f" {mc['leaked']}/{mc['success']} ({rate:.0f}%)"
                else:
                    row += f" {'N/A':>10}"
            else:
                row += f" {'-':>10}"
        print(row)


def compress_logs(logs_dir: Path, output_file: Path | None = None) -> Path:
    """
    Compress a logs directory into a tar.gz file.

    Args:
        logs_dir: Path to the logs directory to compress
        output_file: Optional output file path. If not provided, creates
                     {logs_dir}.tar.gz in the same parent directory.

    Returns:
        Path to the created tar.gz file
    """
    if not logs_dir.exists():
        raise FileNotFoundError(f"Logs directory not found: {logs_dir}")

    if not logs_dir.is_dir():
        raise ValueError(f"Not a directory: {logs_dir}")

    if output_file is None:
        output_file = logs_dir.parent / f"{logs_dir.name}.tar.gz"

    print(f"Compressing {logs_dir} -> {output_file}")

    with tarfile.open(output_file, "w:gz") as tar:
        tar.add(logs_dir, arcname=logs_dir.name)

    # Get file size
    size_bytes = output_file.stat().st_size
    if size_bytes < 1024:
        size_str = f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        size_str = f"{size_bytes / 1024:.1f} KB"
    else:
        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

    print(f"✓ Created {output_file} ({size_str})")
    return output_file


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Batch runner for leaked tool call reproduction tests"
    )
    parser.add_argument(
        "--runs",
        "-n",
        type=int,
        default=5,
        help="Number of runs per case per model (default: 5)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default=None,
        help="Output directory for logs (default: logs_YYYYMMDD_HHMMSS)",
    )
    parser.add_argument(
        "--models",
        "-m",
        type=str,
        nargs="+",
        default=None,
        help="Specific models to test (default: all)",
    )
    parser.add_argument(
        "--cases",
        "-c",
        type=int,
        nargs="+",
        default=None,
        help="Specific cases to test (default: all 1-5)",
    )
    parser.add_argument(
        "--all-models",
        "-a",
        action="store_true",
        help="Test all available models (equivalent to not specifying --models)",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List all available models and exit",
    )
    parser.add_argument(
        "--compress",
        action="store_true",
        help="Compress the output directory to tar.gz after running tests",
    )
    parser.add_argument(
        "--compress-only",
        type=str,
        metavar="LOGS_DIR",
        help="Only compress an existing logs directory (no tests run)",
    )

    args = parser.parse_args()

    # Handle --compress-only
    if args.compress_only:
        logs_dir = Path(args.compress_only)
        try:
            compress_logs(logs_dir)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}")
            sys.exit(1)
        sys.exit(0)

    # Handle --list-models
    if args.list_models:
        print("Available models:")
        for model in MODELS:
            print(f"  - {model}")
        sys.exit(0)

    # Setup output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(__file__).parent / f"logs_{timestamp}"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine models and cases to test
    if args.all_models:
        models = MODELS
    elif args.models:
        models = args.models
    else:
        models = MODELS
    cases = args.cases if args.cases else list(CASE_FILES.keys())

    # Validate cases
    for case in cases:
        if case not in CASE_FILES:
            print(
                f"Error: Invalid case number {case}. Valid cases: {list(CASE_FILES.keys())}"
            )
            sys.exit(1)

    print("=" * 80)
    print("LEAKED TOOL CALL BATCH RUNNER")
    print("=" * 80)
    print(f"API URL: {ARGO_API_URL}")
    print(f"Output directory: {output_dir}")
    print(f"Models: {', '.join(models)}")
    print(f"Cases: {cases}")
    print(f"Runs per case per model: {args.runs}")
    print(f"Total tests: {len(models) * len(cases) * args.runs}")
    print("=" * 80)

    # Run all tests
    all_results = []

    for case_num in cases:
        print(f"\n--- Case {case_num} ---")
        for model in models:
            for run_num in range(1, args.runs + 1):
                print_progress(case_num, model, run_num, args.runs)
                result = run_single_test(case_num, model, run_num, output_dir)
                all_results.append(result)
                print_result(result)

    # Generate and print statistics
    stats = generate_statistics(all_results)
    print_statistics(stats)

    # Save summary
    summary_file = output_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "config": {
                    "api_url": ARGO_API_URL,
                    "models": models,
                    "cases": cases,
                    "runs_per_case": args.runs,
                },
                "statistics": stats,
                "results": all_results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\n✓ Summary saved to: {summary_file}")
    print(f"✓ Individual responses saved to: {output_dir}")

    # Compress if requested
    if args.compress:
        compress_logs(output_dir)


if __name__ == "__main__":
    main()
