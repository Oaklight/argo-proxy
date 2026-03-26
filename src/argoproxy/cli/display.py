"""Banner and version display utilities for Argo Proxy CLI."""

import asyncio
import os

from packaging import version

from ..__init__ import __version__
from ..endpoints.extras import get_latest_pypi_version
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


def version_check() -> str:
    """Check installed version against latest PyPI release.

    Returns:
        A multi-line string with version info and upgrade hint if available.
    """
    ver_content = [__version__]
    latest = asyncio.run(get_latest_pypi_version())

    if latest:
        if version.parse(latest) > version.parse(__version__):
            ver_content.extend(
                [
                    f"New version available: {latest}",
                    "Update with `pip install --upgrade argo-proxy`",
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

    latest = asyncio.run(get_latest_pypi_version())

    log_info("=" * 80, context="cli")
    if latest and version.parse(latest) > version.parse(__version__):
        log_warning(f"\U0001f680 ARGO PROXY v{__version__}", context="cli")
        log_warning(f"\U0001f195 UPDATE AVAILABLE: v{latest}", context="cli")
        log_info("   \u251c\u2500 Run: pip install --upgrade argo-proxy", context="cli")
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
