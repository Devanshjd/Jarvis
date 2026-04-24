"""
J.A.R.V.I.S -- Tool Schema Exporter

Converts the canonical TOOL_SCHEMAS into formats needed by other layers:
  - Gemini functionDeclarations (for JarvisGeminiLive.ts)
  - Flat alias map (for quick lookup)

Usage:
    python -m core.tool_export              # writes JSON to desktop/src/renderer/src/services/
    python -m core.tool_export --stdout      # prints to stdout
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from core.tool_schemas import TOOL_SCHEMAS, get_schemas_by_layer


# Gemini uses UPPERCASE type names
_TYPE_MAP = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "object": "OBJECT",
    "array": "ARRAY",
}


def _convert_property(prop: dict) -> dict:
    """Convert a single property from Claude format to Gemini format."""
    gemini_prop: dict[str, Any] = {}

    raw_type = prop.get("type", "string")
    gemini_prop["type"] = _TYPE_MAP.get(raw_type, "STRING")

    if "description" in prop:
        gemini_prop["description"] = prop["description"]

    if "enum" in prop:
        gemini_prop["enum"] = prop["enum"]

    if "items" in prop:
        gemini_prop["items"] = _convert_property(prop["items"])

    if raw_type == "object" and "properties" in prop:
        gemini_prop["properties"] = {
            k: _convert_property(v) for k, v in prop["properties"].items()
        }

    return gemini_prop


def _convert_schema(schema: dict) -> dict:
    """Convert a single TOOL_SCHEMA entry to Gemini functionDeclaration."""
    input_schema = schema.get("input_schema", {})
    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    gemini_params: dict[str, Any] = {
        "type": "OBJECT",
        "properties": {
            k: _convert_property(v) for k, v in properties.items()
        },
    }

    if required:
        gemini_params["required"] = required

    result: dict[str, Any] = {
        "name": schema["name"],
        "description": schema.get("description", ""),
        "parameters": gemini_params,
    }

    return result


def export_gemini_declarations(
    include_layers: tuple[str, ...] = ("python", "electron", "both"),
) -> list[dict]:
    """
    Export all tool schemas as Gemini-format functionDeclarations.

    Args:
        include_layers: Which layers to include.  Default exports everything.

    Returns:
        List of Gemini functionDeclaration dicts.
    """
    declarations = []
    seen_names: set[str] = set()

    for schema in TOOL_SCHEMAS:
        layer = schema.get("layer", "python")
        if layer not in include_layers and "both" not in include_layers:
            continue

        name = schema["name"]
        if name in seen_names:
            continue
        seen_names.add(name)

        declarations.append(_convert_schema(schema))

    return declarations


def export_alias_map() -> dict[str, str]:
    """Export {alias: canonical_name} mapping for the frontend."""
    alias_map: dict[str, str] = {}
    for schema in TOOL_SCHEMAS:
        canonical = schema["name"]
        for alias in schema.get("aliases", []):
            alias_map[alias] = canonical
    return alias_map


def write_generated_files(output_dir: str | None = None) -> list[str]:
    """
    Write auto-generated JSON files for the desktop shell.

    Returns list of files written.
    """
    if output_dir is None:
        # Default: desktop/src/renderer/src/services/
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(
            base, "desktop", "src", "renderer", "src", "services",
        )

    os.makedirs(output_dir, exist_ok=True)
    written: list[str] = []

    # 1. Gemini functionDeclarations
    declarations = export_gemini_declarations()
    decl_path = os.path.join(output_dir, "generatedToolDeclarations.json")
    with open(decl_path, "w", encoding="utf-8") as f:
        json.dump(declarations, f, indent=2, ensure_ascii=False)
    written.append(decl_path)

    # 2. Alias map
    alias_map = export_alias_map()
    alias_path = os.path.join(output_dir, "generatedToolAliases.json")
    with open(alias_path, "w", encoding="utf-8") as f:
        json.dump(alias_map, f, indent=2, ensure_ascii=False)
    written.append(alias_path)

    return written


# ── CLI entry point ──────────────────────────────────────────────
if __name__ == "__main__":
    if "--stdout" in sys.argv:
        declarations = export_gemini_declarations()
        print(json.dumps(declarations, indent=2, ensure_ascii=False))
    else:
        files = write_generated_files()
        for f in files:
            print(f"  Written: {f}")
        print(f"\n  {len(files)} files generated with {len(export_gemini_declarations())} tool declarations.")
