"""Test config migration produces output matching fresh init format.

The migrated config should be identical to what save_config() produces
when creating a fresh config via the init flow — i.e., only persistable
fields, formatted with _format_config_yaml() section grouping.
"""

import shutil
import tempfile
from pathlib import Path

from argoproxy._vendor import yaml

from argoproxy.config.io import _format_config_yaml, load_config

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "configs"


def _load_and_roundtrip(fixture_name: str) -> tuple[dict, str, str]:
    """Load a fixture, roundtrip through ArgoConfig, and return comparison data.

    Returns:
        (original_raw_dict, migrated_yaml_str, expected_yaml_str)
    """
    fixture_path = FIXTURES_DIR / fixture_name
    with open(fixture_path) as f:
        raw = yaml.load(f.read())

    # Load through the normal pipeline (applies _migrate_config + from_dict)
    config, _ = load_config(str(fixture_path), env_override=False, verbose=False)
    assert config is not None, f"Failed to load {fixture_name}"

    # What save_config would produce (the "expected" format)
    persistent = config.to_persistent_dict()
    expected_yaml = _format_config_yaml(persistent)

    # What the current CLI migrate produces (raw dict manipulation)
    from argoproxy.cli.handlers import _migrate_config as cli_migrate

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_file = Path(tmpdir) / "config.yaml"
        shutil.copy2(fixture_path, tmp_file)
        cli_migrate(str(tmp_file))
        migrated_yaml = tmp_file.read_text()

    return raw, migrated_yaml, expected_yaml


def _print_comparison(name: str, raw: dict, migrated: str, expected: str):
    """Print side-by-side comparison."""
    print(f"\n{'=' * 70}")
    print(f"FIXTURE: {name}")
    print(f"{'=' * 70}")

    print("\n--- Original raw dict ---")
    print(yaml.dump(raw, default_flow_style=False, sort_keys=True).strip())

    print("\n--- CLI migrate output (ACTUAL) ---")
    print(migrated.strip())

    print("\n--- save_config output (EXPECTED) ---")
    print(expected.strip())

    match = migrated.strip() == expected.strip()
    print(f"\n>>> MATCH: {'YES' if match else 'NO'}")
    if not match:
        # Show differences
        import difflib

        diff = difflib.unified_diff(
            expected.strip().splitlines(),
            migrated.strip().splitlines(),
            fromfile="expected (save_config)",
            tofile="actual (cli migrate)",
            lineterm="",
        )
        print("\n--- DIFF ---")
        print("\n".join(diff))

    return match


def main():
    fixtures = [
        "v1_individual_urls.yaml",
        "v1_no_version.yaml",
        "v1_mixed_bases.yaml",
        "v2_with_base_url.yaml",
        "v2_with_deprecated.yaml",
        "v3_already_migrated.yaml",
    ]

    results = {}
    for name in fixtures:
        try:
            raw, migrated, expected = _load_and_roundtrip(name)
            match = _print_comparison(name, raw, migrated, expected)
            results[name] = match
        except Exception as e:
            print(f"\n{'=' * 70}")
            print(f"FIXTURE: {name} — ERROR: {e}")
            print(f"{'=' * 70}")
            results[name] = False

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    for name, match in results.items():
        status = "PASS" if match else "FAIL"
        print(f"  [{status}] {name}")

    total = len(results)
    passed = sum(results.values())
    print(f"\n  {passed}/{total} passed")


if __name__ == "__main__":
    main()
