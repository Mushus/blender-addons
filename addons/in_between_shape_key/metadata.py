from __future__ import annotations

import math
import re
from dataclasses import dataclass

from bpy.app.translations import pgettext_iface

_NAME_RE = re.compile(r"^(?P<channel>.+)@(?P<position>[0-9]+(?:\.[0-9]+)?)$")
POSITION_DECIMALS = 3


@dataclass(frozen=True)
class TargetSpec:
    channel: str
    position: float


def is_basis_block(key, block) -> bool:
    """Return whether block is Blender's basis Shape Key."""
    return len(key.key_blocks) > 0 and key.key_blocks[0] == block


def parse_target_name(name: str) -> TargetSpec | None:
    """Parse the add-on's Name@Position convention.

    Any name that does not match the complete convention is an ordinary
    shape key. This includes names containing an at-sign with a non-numeric
    suffix, such as ``Thickness@Thin``.
    """
    match = _NAME_RE.fullmatch(name)
    if match is None:
        return None
    channel = match.group("channel").strip()
    if not channel:
        return None
    position_text = match.group("position")
    position = float(position_text)
    if position_text != format_position(position):
        return None
    return TargetSpec(channel=channel, position=position)


def format_position(position: float) -> str:
    value = float(position)
    if not math.isfinite(value):
        raise ValueError(pgettext_iface("Shape Key target position must be finite"))
    rounded = round(value, POSITION_DECIMALS)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.{POSITION_DECIMALS}f}".rstrip("0")


def format_target_name(channel: str, position: float) -> str:
    return f"{channel}@{format_position(normalize_position(position))}"


def normalize_position(position: float) -> float:
    value = float(position)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(pgettext_iface("In-Between position must be between 0.000 and 1.000"))
    return round(value, POSITION_DECIMALS)
