"""What fontconfig, which Pango draws text with, knows about a font family.

    installed("Inter")          is the family itself there, not a substitute?
    missing("Inter", "A ∩ B")   the characters the font that would draw it lacks

Both ask ``fc-match``, which picks the font Pango would use for the family
(a substitute when the family is not installed). Without fontconfig
(not Linux) nothing can be known: every family counts as installed and no
character as missing.
"""

import shutil
import subprocess
from functools import cache


@cache
def installed(family: str) -> bool:
    """Does fontconfig have ``family`` itself rather than a substitute?"""
    found = _match(family, "%{family}")
    if found is None:
        return True
    return family.lower() in (name.strip().lower() for name in found.split(","))


def missing(family: str, text: str) -> list[str]:
    """The characters of ``text`` (spaces aside) the font drawn for ``family`` has no glyph for."""
    ranges = _charset(family)
    if ranges is None:
        return []
    absent: list[str] = []
    for char in dict.fromkeys(text):
        code = ord(char)
        if char.isspace() or any(low <= code <= high for low, high in ranges):
            continue
        absent.append(char)
    return absent


@cache
def _charset(family: str) -> tuple[tuple[int, int], ...] | None:
    """The code point ranges the matched font covers, e.g. ``20-7e a0-ac`` -> ((32, 126), ...)."""
    found = _match(family, "%{charset}")
    if found is None:
        return None
    ranges: list[tuple[int, int]] = []
    for part in found.split():
        low, _, high = part.partition("-")
        ranges.append((int(low, 16), int(high or low, 16)))
    return tuple(ranges)


def _match(family: str, pattern: str) -> str | None:
    if shutil.which("fc-match") is None:
        return None
    return subprocess.run(
        ["fc-match", "-f", pattern, family], capture_output=True, text=True, check=False
    ).stdout
