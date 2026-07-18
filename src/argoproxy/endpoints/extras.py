"""Extra utility functions (PyPI version checking, etc.)."""

from __future__ import annotations


async def get_pypi_versions(pkg: str = "argo-proxy") -> dict[str, str | None]:
    """Query PyPI for the latest stable and pre-release versions of a package."""
    from llm_rosetta._vendor.httpclient import AsyncClient

    from .._vendor.semver import version_parse

    result: dict[str, str | None] = {"stable": None, "pre": None}
    try:
        client = AsyncClient(timeout=5)
        try:
            response = await client.get(
                f"https://pypi.org/pypi/{pkg}/json",
                headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
            )
        finally:
            await client.aclose()

        if response.status_code != 200:
            return result
        data = response.json()  # type: ignore[union-attr]
    except Exception:
        return result

    result["stable"] = data.get("info", {}).get("version")

    pre_versions = []
    for v in data.get("releases", {}).keys():
        try:
            pv = version_parse(v)
            if pv.is_prerelease or pv.is_devrelease:
                pre_versions.append(pv)
        except Exception:
            continue

    if pre_versions:
        latest_pre = max(pre_versions)
        if result["stable"]:
            try:
                if latest_pre > version_parse(result["stable"]):
                    result["pre"] = str(latest_pre)
            except Exception:
                result["pre"] = str(latest_pre)
        else:
            result["pre"] = str(latest_pre)

    return result
