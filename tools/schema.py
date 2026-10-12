"""Build JSON schemas for tools from their Python signatures.

The schemas feed two consumers: native OpenAI-compatible tool calling
(`tools=[...]` in the request) and the text `<action>` protocol prompt used
as a fallback for endpoints that do not support tools.
"""

from __future__ import annotations

import inspect
import json
import types
import typing
from collections.abc import Callable, Iterable
from typing import Any, Literal, Union

_PRIMITIVES: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    dict: "object",
    list: "array",
}


def _is_union(tp: Any) -> bool:
    origin = typing.get_origin(tp)
    return origin is Union or origin is types.UnionType


def type_to_schema(tp: Any) -> dict[str, Any]:
    if tp is inspect.Parameter.empty or tp is Any:
        return {}

    if _is_union(tp):
        members = [arg for arg in typing.get_args(tp) if arg is not type(None)]
        if len(members) == 1:
            return type_to_schema(members[0])
        return {"anyOf": [type_to_schema(member) for member in members]}

    origin = typing.get_origin(tp)
    if origin is Literal:
        values = list(typing.get_args(tp))
        schema: dict[str, Any] = {"enum": values}
        if all(isinstance(value, str) for value in values):
            schema["type"] = "string"
        return schema

    if origin in (list, tuple, set, frozenset):
        args = typing.get_args(tp)
        items = type_to_schema(args[0]) if args else {}
        return {"type": "array", "items": items} if items else {"type": "array"}

    if origin is dict:
        return {"type": "object"}

    if tp in _PRIMITIVES:
        return {"type": _PRIMITIVES[tp]}

    return {}


def function_to_schema(fn: Callable[..., Any], param_docs: dict[str, str] | None = None) -> dict[str, Any]:
    """Derive an object schema from a function's signature and type hints."""
    param_docs = param_docs or {}
    signature = inspect.signature(fn)
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in signature.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        schema = dict(type_to_schema(hints.get(name, param.annotation)))
        if name in param_docs:
            schema["description"] = param_docs[name]
        if param.default is inspect.Parameter.empty:
            required.append(name)
        elif param.default is not None and _json_safe(param.default):
            schema["default"] = param.default
        properties[name] = schema

    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        result["required"] = required
    return result


def _json_safe(value: Any) -> bool:
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False


def validate_args(schema: dict[str, Any], args: dict[str, Any]) -> str | None:
    """Return a readable error when args don't fit the schema's keys, else None."""
    properties = schema.get("properties", {})
    accepted = ", ".join(properties) or "(none)"

    unknown = [key for key in args if key not in properties]
    if unknown and schema.get("additionalProperties") is False:
        return f"unknown argument(s) {', '.join(sorted(unknown))}. Accepted arguments: {accepted}."

    missing = [key for key in schema.get("required", []) if key not in args]
    if missing:
        return f"missing required argument(s) {', '.join(missing)}. Accepted arguments: {accepted}."

    return None


def _schema_type_label(schema: dict[str, Any]) -> str:
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(_schema_type_label(member) for member in schema["anyOf"])
    kind = schema.get("type", "any")
    if kind == "array" and schema.get("items"):
        return f"list[{_schema_type_label(schema['items'])}]"
    return {"string": "str", "integer": "int", "number": "float", "boolean": "bool", "object": "dict", "array": "list"}.get(kind, kind)


def render_signature(name: str, schema: dict[str, Any]) -> str:
    required = set(schema.get("required", []))
    parts = []
    for param, spec in schema.get("properties", {}).items():
        label = f"{param}: {_schema_type_label(spec)}"
        if param not in required:
            default = spec.get("default")
            label += f" = {json.dumps(default)}" if default is not None else " = null"
        parts.append(label)
    return f"{name}({', '.join(parts)})"


def render_tool_list(entries: Iterable[tuple[str, str, str, dict[str, Any]]]) -> str:
    """Render `(name, description, permission, schema)` tuples as numbered signatures."""
    lines = []
    for index, (name, description, permission, schema) in enumerate(entries, start=1):
        lines.append(f"{index}. {render_signature(name, schema)} - {description} Permission: {permission}.")
        for param, spec in schema.get("properties", {}).items():
            if spec.get("description"):
                lines.append(f"   - {param}: {spec['description']}")
    return "\n".join(lines)


__all__ = [
    "function_to_schema",
    "render_signature",
    "render_tool_list",
    "type_to_schema",
    "validate_args",
]
