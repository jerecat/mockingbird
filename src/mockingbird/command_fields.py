"""Shared validation for literal external command fields."""
from .validation import positive_seconds


def mapping(value, field, allowed):
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{field} has unknown keys: {sorted(unknown)}")
    return value


def argv(value, field, *, empty=False):
    if not isinstance(value, list) or (not empty and not value) or any(
        not isinstance(item, str) or "\0" in item for item in value
    ):
        raise ValueError(f"{field} must be a {'possibly empty' if empty else 'non-empty'} list of strings")
    if not empty and not value[0]:
        raise ValueError(f"{field} executable must not be empty")
    return list(value)


def timeout(value, field):
    if value is None:
        raise ValueError(f"{field} is required")
    return positive_seconds(value, field)


