"""Small canonical ingredient registry: stable IDs and categories for downstream systems."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ingredient_pipeline import canonicalize_ingredient_name

_REGISTRY_PATH = Path(__file__).resolve().parent / "registry.json"


@lru_cache(maxsize=1)
def _load_registry_rows() -> list[dict[str, Any]]:
    if not _REGISTRY_PATH.is_file():
        return []
    data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


@lru_cache(maxsize=1)
def _alias_to_entry() -> dict[str, dict[str, Any]]:
    """Map normalized surface form -> registry row."""
    m: dict[str, dict[str, Any]] = {}
    for entry in _load_registry_rows():
        if not isinstance(entry, dict):
            continue
        cid = entry.get("id")
        cname = entry.get("canonical_name")
        if not cid or not cname:
            continue
        keys = {canonicalize_ingredient_name(str(cname))}
        for a in entry.get("aliases") or []:
            if isinstance(a, str) and a.strip():
                keys.add(canonicalize_ingredient_name(a.strip()))
        for k in keys:
            if k:
                m[k] = entry
    return m


def lookup_ingredient_identity(surface_name: str) -> dict[str, Any] | None:
    """Return registry row if surface name matches canonical_name or any alias (after pipeline normalization)."""
    key = canonicalize_ingredient_name(surface_name)
    if not key:
        return None
    return _alias_to_entry().get(key)


def enrich_ingredients_with_registry(ingredients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach ingredient_id + category (+ registry canonical_name) when matched."""
    out: list[dict[str, Any]] = []
    for row in ingredients:
        if not isinstance(row, dict):
            continue
        r = dict(row)
        hit = lookup_ingredient_identity(str(r.get("name", "")))
        if hit:
            r["ingredient_id"] = hit["id"]
            r["category"] = hit.get("category") or "unknown"
            r["registry_canonical_name"] = hit.get("canonical_name") or r.get("name")
        else:
            r["ingredient_id"] = None
            r["category"] = "unknown"
            r["registry_canonical_name"] = None
        out.append(r)
    return out
