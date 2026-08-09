from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .metadata import has_at_sign, parse_target_name


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
        name = block.name
        if has_at_sign(name):
            spec = parse_target_name(name)
            if spec is None:
                errors.append(f"Invalid shape key name at index {index}: {name}")
                continue
            if not 0.0 <= spec.weight <= 100.0:
                errors.append(f"Weight must be between 0 and 100: {name}")
                continue
            groups[spec.channel].append((index, spec.weight, name))

    for channel, entries in groups.items():
        weights = [weight for _index, weight, _name in entries]
        if len(weights) != len(set(weights)):
            errors.append(f"Duplicate in-between weight in {channel}")
        if weights != sorted(weights):
            warnings.append(f"Targets in {channel} will be sorted by weight on export")

    return ValidationResult(tuple(errors), tuple(warnings))


def validate_all_meshes(bpy_data) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    seen_keys = set()
    for obj in bpy_data.objects:
        if obj.type != "MESH" or obj.data.shape_keys is None:
            continue
        key = obj.data.shape_keys
        if key.as_pointer() in seen_keys:
            continue
        seen_keys.add(key.as_pointer())
        result = validate_shape_keys(key)
        errors.extend(f"{obj.name}: {message}" for message in result.errors)
        warnings.extend(f"{obj.name}: {message}" for message in result.warnings)
    return ValidationResult(tuple(errors), tuple(warnings))
