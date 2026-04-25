# /// zerodep
# version = "0.4.1"
# deps = []
# tier = "simple"
# category = "data"
# note = "Install/update via `zerodep add semver`"
# ///

"""PEP 440 version parser and comparator -- zero dependencies, stdlib only.

Part of zerodep: https://github.com/Oaklight/zerodep
Copyright (c) 2026 Peng Ding. MIT License.

Drop-in replacement for the core functionality of ``packaging.version``.
Parses version strings according to :pep:`440`, normalises them to their
canonical form, and supports the full set of comparison operators so that
version objects sort correctly.

Usage::

    from semver import Version, version_parse

    v1 = version_parse("1.0a5")
    v2 = Version("1.0")
    assert v1 < v2
    assert v1.is_prerelease
    assert not v2.is_prerelease
    assert str(v1) == "1.0a5"

Requirements:
    Python >= 3.10, no third-party packages.
"""

from __future__ import annotations

import functools
import re

__all__ = [
    # Exceptions
    "InvalidVersion",
    # Classes
    "Version",
    # Functions
    "version_parse",
]

# ── PEP 440 regex (non-possessive, Python 3.10 compatible) ──────────

_VERSION_PATTERN = r"""
    v?
    (?:
        (?:(?P<epoch>[0-9]+)!)?                           # epoch
        (?P<release>[0-9]+(?:\.[0-9]+)*)                  # release
        (?P<pre>                                          # pre-release
            [-_.]?
            (?P<pre_l>alpha|a|beta|b|preview|pre|c|rc)
            [-_.]?
            (?P<pre_n>[0-9]+)?
        )?
        (?P<post>                                         # post release
            (?:-(?P<post_n1>[0-9]+))
            |
            (?:
                [-_.]?
                (?P<post_l>post|rev|r)
                [-_.]?
                (?P<post_n2>[0-9]+)?
            )
        )?
        (?P<dev>                                          # dev release
            [-_.]?
            (?P<dev_l>dev)
            [-_.]?
            (?P<dev_n>[0-9]+)?
        )?
    )
    (?:\+(?P<local>[a-z0-9]+(?:[-_.][a-z0-9]+)*))?        # local version
"""

_VERSION_RE = re.compile(
    r"^\s*" + _VERSION_PATTERN + r"\s*$",
    re.VERBOSE | re.IGNORECASE,
)

# ── Pre-compiled regex for splitting local version segments ─────────

_LOCAL_SPLIT_RE = re.compile(r"[-_.]")

# ── Letter normalisation (merged lookup tables) ─────────────────────

# Maps any PEP 440 pre-release letter to its canonical form.
_PRE_NORMALIZE: dict[str, str] = {
    "alpha": "a",
    "a": "a",
    "beta": "b",
    "b": "b",
    "c": "rc",
    "pre": "rc",
    "preview": "rc",
    "rc": "rc",
}

# Maps canonical pre-release letter to an integer for fast comparison.
_PRE_LETTER_INT: dict[str, int] = {"a": 0, "b": 1, "rc": 2}

# Maps post-release synonyms to "post".
_POST_NORMALIZE: dict[str, str] = {
    "rev": "post",
    "r": "post",
    "post": "post",
}

# ── Integer sentinels for comparison keys ───────────────────────────
# Using plain ints/tuples instead of custom objects avoids method
# dispatch overhead during tuple comparison.

_PRE_SENTINEL_NEG = (-1, 0)  # dev-only: sorts before any pre tag (a=0)
_PRE_SENTINEL_INF = (3, 0)  # no pre: sorts after rc=2
_POST_SENTINEL_NEG = (-1, 0)  # no post: sorts before any post (0, N)
_DEV_SENTINEL_INF = (1, 0)  # no dev: sorts after any dev (0, N)
_LOCAL_SENTINEL_NEG = ((-1,),)  # no local: sorts before any local part


# ── Exceptions ──────────────────────────────────────────────────────


class InvalidVersion(ValueError):
    """Raised when a version string does not conform to PEP 440."""


# ── Version class ───────────────────────────────────────────────────


@functools.total_ordering
class Version:
    """A PEP 440 version.

    Args:
        version: A PEP 440 compliant version string.

    Raises:
        InvalidVersion: If *version* does not conform to PEP 440.

    Example::

        >>> v = Version("1.2.3rc1")
        >>> v.is_prerelease
        True
        >>> str(v)
        '1.2.3rc1'
    """

    __slots__ = (
        "_epoch",
        "_release",
        "_pre",
        "_post",
        "_dev",
        "_local",
        "_key",
        "_str",
    )

    def __init__(self, version: str) -> None:
        match = _VERSION_RE.match(version)
        if not match:
            raise InvalidVersion(f"Invalid version: {version!r}")

        # Extract all groups at once via positional tuple (fastest).
        # Index map: 0=epoch, 1=release, 2=pre, 3=pre_l, 4=pre_n,
        #   5=post, 6=post_n1, 7=post_l, 8=post_n2, 9=dev, 10=dev_l,
        #   11=dev_n, 12=local
        (
            g_epoch,
            g_release,
            _,
            g_pre_l,
            g_pre_n,
            _,
            g_post_n1,
            g_post_l,
            g_post_n2,
            _,
            g_dev_l,
            g_dev_n,
            g_local,
        ) = match.groups()

        # ── Parse components ────────────────────────────────────────
        epoch = int(g_epoch) if g_epoch else 0
        release = tuple(map(int, g_release.split(".")))

        # Pre-release
        if g_pre_l:
            pre_letter = _PRE_NORMALIZE[g_pre_l.lower()]
            pre_num = int(g_pre_n) if g_pre_n else 0
            pre: tuple[str, int] | None = (pre_letter, pre_num)
        else:
            pre = None

        # Post-release
        if g_post_l:
            post_num = int(g_post_n2) if g_post_n2 else 0
            post: tuple[str, int] | None = ("post", post_num)
        elif g_post_n1 is not None:
            post = ("post", int(g_post_n1))
        else:
            post = None

        # Dev-release
        if g_dev_l:
            dev_num = int(g_dev_n) if g_dev_n else 0
            dev: tuple[str, int] | None = ("dev", dev_num)
        else:
            dev = None

        # Local version
        if g_local is not None:
            local: tuple[int | str, ...] | None = tuple(
                int(p) if p.isdigit() else p.lower()
                for p in _LOCAL_SPLIT_RE.split(g_local)
            )
        else:
            local = None

        self._epoch = epoch
        self._release = release
        self._pre = pre
        self._post = post
        self._dev = dev
        self._local = local

        # ── Build comparison key (inlined _cmpkey) ──────────────────
        # Strip trailing zeros from release for comparison.
        cmp_release = release
        i = len(release) - 1
        while i > 0 and release[i] == 0:
            i -= 1
        if i < len(release) - 1:
            cmp_release = release[: i + 1]

        # Pre-release key: dev-only < pre-release < final
        if pre is None and post is None and dev is not None:
            cmp_pre = _PRE_SENTINEL_NEG
        elif pre is not None:
            cmp_pre = (_PRE_LETTER_INT[pre[0]], pre[1])
        else:
            cmp_pre = _PRE_SENTINEL_INF

        # Post-release key: absent sorts before any post
        cmp_post = (0, post[1]) if post is not None else _POST_SENTINEL_NEG

        # Dev-release key: absent sorts after any dev
        cmp_dev = (0, dev[1]) if dev is not None else _DEV_SENTINEL_INF

        # Local version key: absent sorts before any local
        if local is None:
            cmp_local: tuple[tuple[int, ...] | tuple[int, str], ...] = (
                _LOCAL_SENTINEL_NEG
            )
        else:
            cmp_local = tuple((p, "") if isinstance(p, int) else (-1, p) for p in local)

        self._key = (epoch, cmp_release, cmp_pre, cmp_post, cmp_dev, cmp_local)
        self._str: str | None = None  # lazy-cached canonical string

    # ── Comparison ───────────────────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key == other._key

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key < other._key

    def __hash__(self) -> int:
        return hash(self._key)

    # ── String representations ───────────────────────────────────────

    def __repr__(self) -> str:
        return f"<Version('{self}')>"

    def __str__(self) -> str:
        cached = self._str
        if cached is not None:
            return cached
        parts: list[str] = []
        if self._epoch != 0:
            parts.append(f"{self._epoch}!")
        parts.append(".".join(map(str, self._release)))
        if self._pre is not None:
            parts.append(f"{self._pre[0]}{self._pre[1]}")
        if self._post is not None:
            parts.append(f".post{self._post[1]}")
        if self._dev is not None:
            parts.append(f".dev{self._dev[1]}")
        if self._local is not None:
            parts.append("+")
            parts.append(".".join(str(x) for x in self._local))
        result = "".join(parts)
        self._str = result
        return result

    # ── Public properties ────────────────────────────────────────────

    @property
    def epoch(self) -> int:
        """The epoch segment of the version (``0`` when absent)."""
        return self._epoch

    @property
    def release(self) -> tuple[int, ...]:
        """The release segment as a tuple of integers."""
        return self._release

    @property
    def pre(self) -> tuple[str, int] | None:
        """The pre-release tag as ``(letter, number)`` or ``None``."""
        return self._pre

    @property
    def post(self) -> int | None:
        """The post-release number, or ``None``."""
        return self._post[1] if self._post else None

    @property
    def dev(self) -> int | None:
        """The dev-release number, or ``None``."""
        return self._dev[1] if self._dev else None

    @property
    def local(self) -> str | None:
        """The local version label, or ``None``."""
        if self._local is None:
            return None
        return ".".join(str(x) for x in self._local)

    @property
    def is_prerelease(self) -> bool:
        """``True`` if this is a pre-release or dev-release version."""
        return self._dev is not None or self._pre is not None

    @property
    def is_devrelease(self) -> bool:
        """``True`` if this is a dev-release version."""
        return self._dev is not None

    @property
    def is_postrelease(self) -> bool:
        """``True`` if this is a post-release version."""
        return self._post is not None

    @property
    def major(self) -> int:
        """The first component of the release segment."""
        return self._release[0]

    @property
    def minor(self) -> int:
        """The second component (``0`` if absent)."""
        return self._release[1] if len(self._release) > 1 else 0

    @property
    def micro(self) -> int:
        """The third component (``0`` if absent)."""
        return self._release[2] if len(self._release) > 2 else 0

    @property
    def base_version(self) -> str:
        """The version without pre/post/dev/local suffixes."""
        parts: list[str] = []
        if self._epoch != 0:
            parts.append(f"{self._epoch}!")
        parts.append(".".join(str(x) for x in self._release))
        return "".join(parts)

    @property
    def public(self) -> str:
        """The version without the local segment."""
        return str(self).split("+", 1)[0]


# ── Convenience function ─────────────────────────────────────────────


def version_parse(version: str) -> Version:
    """Parse a PEP 440 version string.

    Args:
        version: A PEP 440 compliant version string.

    Returns:
        A :class:`Version` object.

    Raises:
        InvalidVersion: If *version* does not conform to PEP 440.
    """
    return Version(version)
