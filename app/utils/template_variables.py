"""Utilities for safe, provider-independent RCS template personalization."""

import re
from copy import deepcopy


VARIABLE_PATTERN = re.compile(r"\{\{\s*([A-Za-z][A-Za-z0-9_]*)\s*\}\}")
RESERVED_VARIABLES = {"mobile"}


def extract_template_variables(value):
    """Return sorted placeholder names found anywhere in a JSON-like payload."""
    found = set()

    def visit(item):
        if isinstance(item, str):
            found.update(name.lower() for name in VARIABLE_PATTERN.findall(item))
        elif isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return sorted(found)


def normalize_variable_name(value):
    name = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "").strip()).strip("_").lower()
    return name


def normalize_variables(values):
    return {
        normalize_variable_name(key): "" if value is None else str(value).strip()
        for key, value in (values or {}).items()
        if normalize_variable_name(key) and normalize_variable_name(key) not in RESERVED_VARIABLES
    }


def missing_template_variables(required, values):
    normalized = normalize_variables(values)
    return sorted(name for name in required or [] if not normalized.get(name))


def render_template_payload(payload, values, *, strict=True):
    """Deep-copy and render placeholders in all string fields of an RCS payload."""
    variables = normalize_variables(values)
    missing = set()

    def render(item):
        if isinstance(item, str):
            def replace(match):
                name = match.group(1).lower()
                if name not in variables or variables[name] == "":
                    missing.add(name)
                    return match.group(0)
                return variables[name]

            return VARIABLE_PATTERN.sub(replace, item)
        if isinstance(item, dict):
            return {key: render(value) for key, value in item.items()}
        if isinstance(item, list):
            return [render(value) for value in item]
        return deepcopy(item)

    rendered = render(payload)
    if strict and missing:
        raise ValueError(f"Missing template variables: {', '.join(sorted(missing))}")
    return rendered
