"""Deterministic post-processing: canonicalize ingredient names, fuzzy aliases, merge duplicates."""

from __future__ import annotations

import re
import unicodedata
from difflib import get_close_matches
from typing import Any

# Synonym / typo / plural surface forms -> canonical shopping name (stable lowercase).
CANONICAL_MAP: dict[str, str] = {
    "cilantro": "coriander leaves",
    "coriander leaves": "coriander leaves",
    "fresh cilantro": "coriander leaves",
    "green onion": "spring onion",
    "green onions": "spring onion",
    "scallion": "spring onion",
    "scallions": "spring onion",
    "spring onions": "spring onion",
    "ginger garlic paste": "ginger-garlic paste",
    "ginger-garlic paste": "ginger-garlic paste",
    "garlic ginger paste": "ginger-garlic paste",
    "onions": "onion",
    "white onions": "white onion",
    "white onion": "white onion",
    "coriander leaf": "coriander leaves",
    "tomatoes": "tomato",
    "cloves": "clove",
    "potatoes": "potato",
    "carrots": "carrot",
    "eggs": "egg",
    "lemons": "lemon",
    "limes": "lime",
    "bell peppers": "bell pepper",
    "jalapenos": "jalapeno",
    "chiles": "chile",
    "chilies": "chile",
    "peppers": "pepper",
}

# Display form for units (merge key).
UNIT_NORMALIZE: dict[str, str] = {
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tbsp": "tbsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tsp": "tsp",
    "gram": "g",
    "grams": "g",
    "g": "g",
    "kilogram": "kg",
    "kilograms": "kg",
    "kg": "kg",
    "milliliter": "ml",
    "milliliters": "ml",
    "ml": "ml",
    "liter": "l",
    "liters": "l",
    "l": "l",
    "ounce": "oz",
    "ounces": "oz",
    "oz": "oz",
    "pound": "lb",
    "pounds": "lb",
    "lb": "lb",
    "cup": "cup",
    "cups": "cup",
    "piece": "piece",
    "pieces": "piece",
    "clove": "clove",
    "bunch": "bunch",
    "pinch": "pinch",
    "slice": "slice",
    "slices": "slice",
    "sheet": "sheet",
    "sheets": "sheet",
    "leaf": "leaf",
    "leaves": "leaf",
    "fl oz": "fl_oz",
    "floz": "fl_oz",
    "fl_oz": "fl_oz",
    "whole": "whole",
    "to taste": "to_taste",
    "to_taste": "to_taste",
}

_IRREGULAR: dict[str, str] = {
    "leaves": "leaf",
    "tomatoes": "tomato",
    "potatoes": "potato",
    "cherries": "cherry",
    "berries": "berry",
}


def _strip_punct(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = re.sub(r"[^\w\s\-]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _singularize_token(token: str) -> str:
    t = token.strip().lower()
    if not t:
        return t
    if t in _IRREGULAR:
        return _IRREGULAR[t]
    if len(t) <= 2:
        return t
    if t.endswith("ies") and len(t) > 3 and not t.endswith("cies"):
        return t[:-3] + "y"
    if t.endswith("oes") and len(t) > 3:
        return t[:-2]
    if t.endswith("ses") and len(t) > 3:
        return t[:-2]
    if t.endswith("es") and len(t) > 3 and t[-3] in "sxzh":
        return t[:-2]
    if t.endswith("s") and not t.endswith("ss") and not t.endswith("us"):
        return t[:-1]
    return t


def _singularize_phrase(phrase: str) -> str:
    parts = phrase.split()
    if not parts:
        return phrase
    return " ".join(_singularize_token(p) for p in parts)


def _fuzzy_canonical_key(normalized: str) -> str | None:
    keys = sorted(CANONICAL_MAP.keys())
    m = get_close_matches(normalized, keys, n=1, cutoff=0.88)
    return m[0] if m else None


def canonicalize_ingredient_name(raw: str) -> str:
    """Lowercase, strip punctuation, singularize, fuzzy + explicit map."""
    s = _strip_punct(raw)
    if not s:
        return raw.strip().lower()
    s = _singularize_phrase(s)
    if s in CANONICAL_MAP:
        return CANONICAL_MAP[s]
    fuzzy_key = _fuzzy_canonical_key(s)
    if fuzzy_key is not None:
        return CANONICAL_MAP[fuzzy_key]
    values = sorted({v for v in CANONICAL_MAP.values()})
    vm = get_close_matches(s, values, n=1, cutoff=0.92)
    if vm:
        return vm[0]
    return s


def normalize_unit(unit: str | None) -> str:
    if unit is None:
        return ""
    u = _strip_punct(str(unit)).replace(" ", "_")
    return UNIT_NORMALIZE.get(u, u)


def _parse_quantity(q: Any) -> float | None:
    if q is None:
        return None
    s = str(q).strip()
    if not s:
        return None
    if "/" in s and s.count("/") == 1:
        a, b = s.split("/", 1)
        try:
            return float(a.strip()) / float(b.strip())
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _format_quantity(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text else "0"


def merge_duplicate_ingredients(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge rows that share the same canonical name + normalized unit.
    Sums numeric quantities; collects optional `use` tags into `uses`.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    order: list[tuple[str, str]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name", "")
        unit = normalize_unit(row.get("unit"))
        cname = canonicalize_ingredient_name(str(name))
        key = (cname, unit)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(row)

    merged: list[dict[str, Any]] = []
    for key in order:
        bucket = groups[key]
        cname, unit = key
        total: float | None = None
        any_numeric = False
        merged_optional = True
        uses: list[str] = []
        seen_use: set[str] = set()

        for r in bucket:
            if not r.get("optional", False):
                merged_optional = False
            v = _parse_quantity(r.get("quantity"))
            if v is not None:
                any_numeric = True
                total = (total or 0.0) + v
            use = r.get("use")
            if isinstance(use, str):
                u = use.strip()
                if u and u not in seen_use:
                    seen_use.add(u)
                    uses.append(u)

        out: dict[str, Any] = {
            "name": cname,
            "quantity": _format_quantity(total) if any_numeric and total is not None else "",
            "unit": unit,
            "optional": merged_optional,
        }
        if not any_numeric or total is None:
            # Preserve first non-empty quantity string if nothing parsed.
            for r in bucket:
                q = r.get("quantity")
                if q is not None and str(q).strip():
                    out["quantity"] = str(q).strip()
                    break

        if len(bucket) > 1:
            if uses:
                out["uses"] = uses
            else:
                out["uses"] = ["combined"]
        else:
            if uses:
                out["uses"] = uses

        merged.append(out)
    return merged


def process_extracted_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Run canonicalization + duplicate merge on model JSON."""
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    ing = out.get("ingredients")
    if not isinstance(ing, list):
        return out
    raw_rows = [dict(x) for x in ing if isinstance(x, dict)]
    out["ingredients"] = merge_duplicate_ingredients(raw_rows)
    from ingredient_registry import enrich_ingredients_with_registry

    out["ingredients"] = enrich_ingredients_with_registry(out["ingredients"])
    return out


def compute_heuristic_confidence(dish_name: str, payload: dict[str, Any]) -> float:
    """
    Deterministic confidence from inputs + model structural tags (not model's own confidence).

    Tuned heuristics (adjust constants as you gather eval data):
    - base_score starts optimistic for named dishes
    - penalize high ambiguity, very short user strings, and unknown/implicit cuisine
    """
    base_score = 0.85
    score = float(base_score)
    d = dish_name.strip()
    words = d.split()

    amb = payload.get("ambiguity")
    if not isinstance(amb, dict):
        amb = {}
    level = str(amb.get("level") or "low").strip().lower()
    cuisine = str(payload.get("cuisine") or "").strip().lower()

    if level == "high":
        score -= 0.25
    # Underspecified dish phrase (word count) or trivially short string
    if len(words) < 3 or len(d) < 3:
        score -= 0.15
    if cuisine in ("", "unknown"):
        score -= 0.1

    return max(0.0, min(1.0, round(score, 2)))


def _normalize_alternate_entry(entry: Any) -> dict[str, str] | None:
    if not isinstance(entry, dict):
        return None
    cuisine = str(entry.get("cuisine") or "").strip() or "Unknown"
    protein = str(entry.get("protein") or entry.get("label") or "unknown").strip()
    return {"cuisine": cuisine, "protein": protein}


def apply_heuristic_metadata(dish_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize ambiguity.alternates to {cuisine, protein} and overwrite confidence
    with compute_heuristic_confidence (model-supplied confidence is not trusted).
    """
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    raw_amb = out.get("ambiguity")
    if not isinstance(raw_amb, dict):
        raw_amb = {}
    raw_alts = raw_amb.get("alternates")
    if not isinstance(raw_alts, list):
        raw_alts = []
    alternates: list[dict[str, str]] = []
    for item in raw_alts[:3]:
        norm = _normalize_alternate_entry(item)
        if norm is not None:
            alternates.append(norm)
    level = str(raw_amb.get("level") or "low").strip().lower()
    if level not in ("low", "medium", "high"):
        level = "low"
    out["ambiguity"] = {"level": level, "alternates": alternates}
    out["confidence"] = compute_heuristic_confidence(dish_name, out)
    return out
