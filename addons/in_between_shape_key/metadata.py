from __future__ import annotations

import re
from dataclasses import dataclass

_NAME_RE = re.compile(r"^(?P<channel>.+)@(?P<weight>[0-9]+(?:\.[0-9]+)?)$")


@dataclass(frozen=True)
class TargetSpec:
    channel: str
    weight: float


def parse_target_name(name: str) -> TargetSpec | None:
    """Parse the add-on's Name@Weight convention.

    Names without an at-sign are ordinary shape keys. Names containing an
    at-sign but not matching the grammar are invalid and are reported by
    validate_shape_keys.
    """
    match = _NAME_RE.fullmatch(name)
    if match is None:
        return None
    channel = match.group("channel").strip()
    if not channel:
        return None
    return TargetSpec(channel=channel, weight=float(match.group("weight")))


def has_at_sign(name: str) -> bool:
    return "@" in name


def format_weight(weight: float) -> str:
    if float(weight).is_integer():
        return str(int(weight))
    return f"{weight:.6f}".rstrip("0").rstrip(".")


def format_target_name(channel: str, weight: float) -> str:
    return f"{channel}@{format_weight(weight)}"
