"""Banner and version display utilities for Argo Proxy CLI."""

import asyncio
import os

from packaging import version

from ..__init__ import __version__
from ..endpoints.extras import get_pypi_versions
from ..utils.logging import log_info, log_warning

# ReadTheDocs changelog URL
CHANGELOG_URL = "https://argo-proxy.readthedocs.io/en/latest/changelog/"


def get_ascii_banner() -> str:
    """Generate ASCII banner for Argo Proxy."""
    return """
 \u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557  \u2588\u2588\u2588\u2588\u2588\u2588\u2557     \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557  \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2557  \u2588\u2588\u2557\u2588\u2588\u2557   \u2588\u2588\u2557
\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2550\u2550\u255d \u2588\u2588\u2554\u2550\u2550\u2550\u2588\u2588\u2557    \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2550\u2588\u2588\u2557\u255a\u2588\u2588\u2557\u2588\u2588\u2554\u255d\u255a\u2588\u2588\u2557 \u2588\u2588\u2554\u255d
\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2551  \u2588\u2588\u2588\u2557\u2588\u2588\u2551   \u2588\u2588\u2551    \u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2551   \u2588\u2588\u2551 \u255a\u2588\u2588\u2588\u2554\u255d  \u255a\u2588\u2588\u2588\u2588\u2554\u255d
\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2551   \u2588\u2588\u2551    \u2588\u2588\u2554\u2550\u2550\u2550\u255d \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2551   \u2588\u2588\u2551 \u2588\u2588\u2554\u2588\u2588\u2557   \u255a\u2588\u2588\u2554\u255d
\u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2551  \u2588\u2588\u2551\u255a\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u255a\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d    \u2588\u2588\u2551     \u2588\u2588\u2551  \u2588\u2588\u2551\u255a\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2554\u255d \u2588\u2588\u2557   \u2588\u2588\u2551
\u255a\u2550\u255d  \u255a\u2550\u255d\u255a\u2550\u255d  \u255a\u2550\u255d \u255a\u2550\u2550\u2550\u2550\u2550\u255d  \u255a\u2550\u2550\u2550\u2550\u2550\u255d     \u255a\u2550\u255d     \u255a\u2550\u255d  \u255a\u2550\u255d \u255a\u2550\u2550\u2550\u2550\u2550\u255d \u255a\u2550\u255d  \u255a\u2550\u255d   \u255a\u2550\u255d
"""


def _pick_relevant_latest(
    versions: dict[str, str | None],
) -> str | None:
    """Pick the version to compare against based on installed version.

    If the installed version is a pre-release, compare against the latest
    pre-release (or stable if no pre-release is newer). Otherwise compare
    against stable only.
    """
    cur = version.parse(__version__)
    stable = versions.get("stable")
    pre = versions.get("pre")

    if cur.is_prerelease or cur.is_devrelease:
        # Compare against whichever is newer: stable or pre-release
        candidates = []
        if stable:
            candidates.append(version.parse(stable))
        if pre:
            candidates.append(version.parse(pre))
        if candidates:
            best = max(candidates)
            return str(best)
        return None
    return stable


def version_check() -> str:
    """Check installed version against latest PyPI release.

    Returns:
        A multi-line string with version info and upgrade hint if available.
    """
    ver_content = [__version__]
    versions = asyncio.run(get_pypi_versions())
    latest = _pick_relevant_latest(versions)

    if latest:
        if version.parse(latest) > version.parse(__version__):
            is_pre = version.parse(latest).is_prerelease
            pre_flag = " --pre" if is_pre else ""
            pip_flag = " --pre" if is_pre else ""
            ver_content.extend(
                [
                    f"New version available: {latest}",
                    f"Update with `argo-proxy update install{pre_flag}`",
                    f"  or: `pip install --upgrade{pip_flag} argo-proxy`",
                    f"Changelog: {CHANGELOG_URL}",
                ]
            )

    return "\n".join(ver_content)


def display_startup_banner(no_banner: bool = False):
    """Display startup banner with version and mode information.

    Args:
        no_banner: If True, suppress the ASCII art banner.
    """
    if not no_banner:
        banner = get_ascii_banner()
        print(banner)

    versions = asyncio.run(get_pypi_versions())
    latest = _pick_relevant_latest(versions)

    log_info("=" * 80, context="cli")
    if latest and version.parse(latest) > version.parse(__version__):
        is_pre = version.parse(latest).is_prerelease
        pip_flag = " --pre" if is_pre else ""
        log_warning(f"\U0001f680 ARGO PROXY v{__version__}", context="cli")
        log_warning(f"\U0001f195 UPDATE AVAILABLE: v{latest}", context="cli")
        pre_flag = " --pre" if is_pre else ""
        log_info(
            f"   \u251c\u2500 Run: argo-proxy update install{pre_flag}",
            context="cli",
        )
        log_info(
            f"   \u251c\u2500 Or:  pip install --upgrade{pip_flag} argo-proxy",
            context="cli",
        )
        log_info(f"   \u2514\u2500 Changelog: {CHANGELOG_URL}", context="cli")
    else:
        log_warning(f"\U0001f680 ARGO PROXY v{__version__} (Latest)", context="cli")

    from ..utils.misc import str_to_bool

    dev_mode = str_to_bool(os.environ.get("DEV_MODE", "false"))

    if str_to_bool(os.environ.get("USE_LEGACY_ARGO", "false")):
        log_warning("\u2699\ufe0f  MODE: Legacy ARGO Gateway", context="cli")
    elif dev_mode:
        log_warning(
            "\u2699\ufe0f  MODE: Transparent Proxy (no conversion)", context="cli"
        )
    else:
        log_info("\u2699\ufe0f  MODE: Universal (llm-rosetta)", context="cli")
    log_info("=" * 80, context="cli")
