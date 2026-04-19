# /// zerodep
# version = "0.4.0"
# deps = []
# tier = "simple"
# category = "data"
# note = "Install/update via: https://zerodep.readthedocs.io/en/latest/guide/cli/"
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

# ── Sentinel types for comparison keys ───────────────────────────────


class _InfinityType:
    """Compares greater than any other object (except itself)."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "Infinity"

    def __hash__(self) -> int:
        return hash(repr(self))

    def __lt__(self, other: object) -> bool:
        return False

    def __le__(self, other: object) -> bool:
        return isinstance(other, _InfinityType)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _InfinityType)

    def __gt__(self, other: object) -> bool:
        return not isinstance(other, _InfinityType)

    def __ge__(self, other: object) -> bool:
        return True


class _NegativeInfinityType:
    """Compares less than any other object (except itself)."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "-Infinity"

    def __hash__(self) -> int:
        return hash(repr(self))

    def __lt__(self, other: object) -> bool:
        return not isinstance(other, _NegativeInfinityType)

    def __le__(self, other: object) -> bool:
        return True

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _NegativeInfinityType)

    def __gt__(self, other: object) -> bool:
        return False

    def __ge__(self, other: object) -> bool:
        return isinstance(other, _NegativeInfinityType)


_Infinity = _InfinityType()
_NegativeInfinity = _NegativeInfinityType()

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

# ── Letter normalisation ────────────────────────────────────────────

_PRE_NORMALIZE: dict[str, str] = {
    "alpha": "a",
    "beta": "b",
    "c": "rc",
    "pre": "rc",
    "preview": "rc",
}

_POST_NORMALIZE: dict[str, str] = {
    "rev": "post",
    "r": "post",
}

# ── Helpers ──────────────────────────────────────────────────────────


def _parse_letter_version(
    letter: str | None,
    number: str | int | None,
) -> tuple[str, int] | None:
    if letter:
        letter = letter.lower()
        letter = _PRE_NORMALIZE.get(letter, letter)
        letter = _POST_NORMALIZE.get(letter, letter)
        number = int(number) if number else 0
        return (letter, number)
    if number is not None:
        # Implicit post release (e.g. ``1.0-1``)
        letter = "post"
        number = int(number)
        return (letter, number)
    return None


def _parse_local_version(local: str | None) -> tuple[int | str, ...] | None:
    if local is None:
        return None
    return tuple(
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"[-_.]", local)
    )


def _cmpkey(
    epoch: int,
    release: tuple[int, ...],
    pre: tuple[str, int] | None,
    post: tuple[str, int] | None,
    dev: tuple[str, int] | None,
    local: tuple[int | str, ...] | None,
) -> tuple:
    # Strip trailing zeros from release for comparison.
    _release = release
    while len(_release) > 1 and _release[-1] == 0:
        _release = _release[:-1]

    # Pre-release versions: dev-only < pre-release < final
    if pre is None and post is None and dev is not None:
        _pre: _InfinityType | _NegativeInfinityType | tuple[str, int] = (
            _NegativeInfinity
        )
    elif pre is None:
        _pre = _Infinity
    else:
        _pre = pre

    # Post-release: absent sorts before any post
    _post: _InfinityType | _NegativeInfinityType | tuple[str, int] = (
        _NegativeInfinity if post is None else post
    )

    # Dev release: absent sorts after any dev
    _dev: _InfinityType | _NegativeInfinityType | tuple[str, int] = (
        _Infinity if dev is None else dev
    )

    # Local version: absent sorts before any local
    if local is None:
        _local: (
            _NegativeInfinityType
            | tuple[tuple[int, str] | tuple[_NegativeInfinityType, str], ...]
        ) = _NegativeInfinity
    else:
        _local = tuple(
            (i, "") if isinstance(i, int) else (_NegativeInfinity, i) for i in local
        )

    return (epoch, _release, _pre, _post, _dev, _local)


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

    __slots__ = ("_epoch", "_release", "_pre", "_post", "_dev", "_local", "_key")

    def __init__(self, version: str) -> None:
        match = _VERSION_RE.fullmatch(version)
        if not match:
            raise InvalidVersion(f"Invalid version: {version!r}")

        self._epoch: int = int(match.group("epoch") or 0)
        self._release: tuple[int, ...] = tuple(
            int(x) for x in match.group("release").split(".")
        )
        self._pre = _parse_letter_version(match.group("pre_l"), match.group("pre_n"))

        post_n = match.group("post_n1") or match.group("post_n2")
        self._post = _parse_letter_version(match.group("post_l"), post_n)

        self._dev = _parse_letter_version(match.group("dev_l"), match.group("dev_n"))
        self._local = _parse_local_version(match.group("local"))

        self._key = _cmpkey(
            self._epoch,
            self._release,
            self._pre,
            self._post,
            self._dev,
            self._local,
        )

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
        parts: list[str] = []
        if self._epoch != 0:
            parts.append(f"{self._epoch}!")
        parts.append(".".join(str(x) for x in self._release))
        if self._pre is not None:
            parts.append(f"{self._pre[0]}{self._pre[1]}")
        if self._post is not None:
            parts.append(f".post{self._post[1]}")
        if self._dev is not None:
            parts.append(f".dev{self._dev[1]}")
        if self._local is not None:
            parts.append(f"+{self.local}")
        return "".join(parts)

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
        return self.dev is not None or self.pre is not None

    @property
    def is_devrelease(self) -> bool:
        """``True`` if this is a dev-release version."""
        return self.dev is not None

    @property
    def is_postrelease(self) -> bool:
        """``True`` if this is a post-release version."""
        return self.post is not None

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
