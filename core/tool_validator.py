"""
J.A.R.V.I.S -- Startup Tool Validator

Runs on JARVIS startup to detect drift between:
  - TOOL_SCHEMAS (the single source of truth)
  - Executor handler registry
  - Orchestrator _build_tool_args

Logs warnings for any mismatches so they get caught immediately
instead of causing silent failures at runtime.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.executor import Executor

logger = logging.getLogger("jarvis.tool_validator")


def validate_tool_registry(executor: Executor) -> dict:
    """
    Validate that TOOL_SCHEMAS, executor handlers, and arg extractors
    are all in sync.

    Returns a dict summarizing the validation:
        {
            "total_schemas": int,
            "total_handlers": int,
            "missing_handlers": [str],
            "extra_handlers": [str],
            "warnings": [str],
        }
    """
    from core.tool_schemas import TOOL_SCHEMAS, get_schemas_by_layer

    result = {
        "total_schemas": len(TOOL_SCHEMAS),
        "total_handlers": len(executor._tools),
        "missing_handlers": [],
        "extra_handlers": [],
        "warnings": [],
    }

    # 1. Check each Python-layer schema has a handler
    python_schemas = get_schemas_by_layer("python")
    schema_names = {s["name"] for s in python_schemas}
    handler_names = set(executor._tools.keys())

    missing = schema_names - handler_names
    extra = handler_names - schema_names

    result["missing_handlers"] = sorted(missing)
    result["extra_handlers"] = sorted(extra)

    for name in missing:
        logger.warning(
            "Tool '%s' has schema but NO executor handler -- will fail at runtime",
            name,
        )

    for name in extra:
        # Extra handlers are less critical -- they work but have no schema
        logger.info(
            "Tool '%s' has executor handler but no schema -- "
            "won't appear in Gemini voice or capability registry",
            name,
        )

    # 2. Check for alias collisions
    from core.tool_schemas import get_all_names_and_aliases
    all_names = get_all_names_and_aliases()
    seen_aliases: dict[str, str] = {}
    for name_or_alias, canonical in all_names.items():
        if name_or_alias in seen_aliases and seen_aliases[name_or_alias] != canonical:
            warning = (
                f"Alias '{name_or_alias}' maps to both "
                f"'{seen_aliases[name_or_alias]}' and '{canonical}'"
            )
            result["warnings"].append(warning)
            logger.warning(warning)
        seen_aliases[name_or_alias] = canonical

    # 3. Check required args are extractable
    for schema in python_schemas:
        name = schema["name"]
        required = schema.get("input_schema", {}).get("required", [])
        if not required:
            continue  # No-arg tool, always extractable

        # Check if the tool has specific arg extraction in orchestrator
        # (we can't easily introspect _build_tool_args, but we can check
        #  that the schema has enough property metadata for the generic extractor)
        props = schema.get("input_schema", {}).get("properties", {})
        for arg_name in required:
            if arg_name not in props:
                warning = (
                    f"Tool '{name}' requires arg '{arg_name}' "
                    f"but it's not in input_schema.properties"
                )
                result["warnings"].append(warning)
                logger.warning(warning)

    # Summary log
    total_issues = len(result["missing_handlers"]) + len(result["warnings"])
    if total_issues == 0:
        logger.info(
            "Tool validation passed: %d schemas, %d handlers, 0 issues",
            result["total_schemas"],
            result["total_handlers"],
        )
    else:
        logger.warning(
            "Tool validation: %d schemas, %d handlers, "
            "%d missing handlers, %d warnings",
            result["total_schemas"],
            result["total_handlers"],
            len(result["missing_handlers"]),
            len(result["warnings"]),
        )

    return result
