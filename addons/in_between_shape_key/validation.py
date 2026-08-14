from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from bpy.app.translations import pgettext_iface

from .metadata import is_basis_block, parse_target_name


def _message(source: str, **values) -> str:
    return pgettext_iface(source).format(**values)


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_shape_keys(key) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    groups = defaultdict(list)

    for index, block in enumerate(key.key_blocks):
        if is_basis_block(key, block):
            continue
        name = block.name
        spec = parse_target_name(name)
        if spec is None:
            continue
        if not 0.0 <= spec.position <= 1.0:
            errors.append(_message("Position must be between 0 and 1: {name}", name=name))
            continue
        groups[spec.channel].append((index, spec.position, name))

    for channel, entries in groups.items():
        positions = [position for _index, position, _name in entries]
        if len(positions) != len(set(positions)):
            errors.append(_message("Duplicate in-between position in {channel}", channel=channel))
    return ValidationResult(tuple(errors), tuple(warnings))


def validate_all_meshes(bpy_data) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    seen_keys = set()
    for obj in bpy_data.objects:
        if obj.type != "MESH" or obj.data.shape_keys is None:
            continue
        key = obj.data.shape_keys
        if key.session_uid in seen_keys:
            continue
        seen_keys.add(key.session_uid)
        result = validate_shape_keys(key)
        errors.extend(f"{obj.name}: {message}" for message in result.errors)
        warnings.extend(f"{obj.name}: {message}" for message in result.warnings)
    return ValidationResult(tuple(errors), tuple(warnings))
