"""Banner and version display utilities for Argo Proxy CLI."""

import asyncio
import importlib.metadata
import os

from .._vendor.semver import version_parse

from ..__init__ import __version__
from ..endpoints.extras import get_pypi_versions
from ..utils.logging import log_info, log_warning

# ReadTheDocs changelog URL
CHANGELOG_URL = "https://argo-proxy.readthedocs.io/en/latest/changelog/"

# Changelog URLs for critical dependencies
_DEP_CHANGELOG_URLS: dict[str, str] = {
    "llm-rosetta": "https://llm-rosetta.readthedocs.io/en/latest/changelog/",
}

# Critical dependencies whose PyPI versions are checked alongside argo-proxy
_CRITICAL_DEPS = ["llm-rosetta"]


def get_ascii_banner() -> str:
    """Generate ASCII banner for Argo Proxy."""
    return """
 █████╗ ██████╗ ██████╗  ██████╗     ██████╗ ██████╗  ██████╗ ██╗  ██╗██╗   ██╗
██╔══██╗██╔══██╗██╔════╝ ██╔═══██╗    ██╔══██╗██╔══██╗██╔═══██╗╚██╗██╔╝╚██╗ ██╔╝
███████║██████╔╝██║  ███╗██║   ██║    ██████╔╝██████╔╝██║   ██║ ╚███╔╝  ╚████╔╝
██╔══██║██╔══██╗██║   ██║██║   ██║    ██╔═══╝ ██╔══██╗██║   ██║ ██╔██╗   ╚██╔╝
██║  ██║██║  ██║╚██████╔╝╚██████╔╝    ██║     ██║  ██║╚██████╔╝██╔╝ ██╗   ██║
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝     ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝
"""


def _get_installed_version(pkg: str) -> str | None:
    """Get the installed version of a package via importlib.metadata.

    Returns:
        Version string or None if the package is not installed.
    """
    try:
        return importlib.metadata.version(pkg)
    except importlib.metadata.PackageNotFoundError:
        return None


def _pick_relevant_latest(
    installed: str,
    versions: dict[str, str | None],
) -> str | None:
    """Pick the version to compare against based on installed version.

    If the installed version is a pre-release, compare against the latest
    pre-release (or stable if no pre-release is newer). Otherwise compare
    against stable only.
    """
    cur = version_parse(installed)
    stable = versions.get("stable")
    pre = versions.get("pre")

    if cur.is_prerelease or cur.is_devrelease:
        candidates = []
        if stable:
            candidates.append(version_parse(stable))
        if pre:
            candidates.append(version_parse(pre))
        if candidates:
            best = max(candidates)
            return str(best)
        return None
    return stable


def _get_dep_update_info() -> list[dict]:
    """Check critical dependencies for available updates.

    Returns:
        List of dicts with keys: name, installed, stable, pre, has_update.
    """
    results = []
    for pkg in _CRITICAL_DEPS:
        installed = _get_installed_version(pkg)
        if installed is None:
            continue
        versions = asyncio.run(get_pypi_versions(pkg))
        stable = versions.get("stable")
        pre = versions.get("pre")

        has_update = False
        cur = version_parse(installed)
        if stable:
            try:
                has_update = version_parse(stable) > cur
            except Exception:
                pass
        if not has_update and pre:
            try:
                has_update = version_parse(pre) > cur
            except Exception:
                pass

        results.append(
            {
                "name": pkg,
                "installed": installed,
                "stable": stable,
                "pre": pre,
                "has_update": has_update,
            }
        )
    return results


def version_check() -> str:
    """Check installed version against latest PyPI release.

    Returns:
        A multi-line string with version info and upgrade hint if available.
    """
    ver_content = [__version__]
    versions = asyncio.run(get_pypi_versions())
    latest = _pick_relevant_latest(__version__, versions)

    if latest:
        if version_parse(latest) > version_parse(__version__):
            is_pre = version_parse(latest).is_prerelease
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

    # Check critical dependencies
    dep_updates = _get_dep_update_info()
    outdated = [d for d in dep_updates if d["has_update"]]
    if outdated:
        ver_content.append("Dependencies:")
        for dep in outdated:
            target = dep["stable"] or dep["pre"]
            ver_content.append(
                f"  {dep['name']} {dep['installed']} \u2192 {target} available"
            )
            ver_content.append(f"    pip install --upgrade {dep['name']}")

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
    latest = _pick_relevant_latest(__version__, versions)

    log_info("=" * 80, context="cli")
    if latest and version_parse(latest) > version_parse(__version__):
        is_pre = version_parse(latest).is_prerelease
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

    # Check critical dependencies for updates
    dep_updates = _get_dep_update_info()
    for dep in dep_updates:
        if dep["has_update"]:
            target = dep["stable"] or dep["pre"]
            log_warning(
                f"\u26a0\ufe0f  {dep['name']} v{dep['installed']} \u2192 v{target} "
                f"available: pip install --upgrade {dep['name']}",
                context="cli",
            )

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
