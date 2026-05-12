"""Contract checks for extract API payloads (fixtures, integration, CI)."""

from __future__ import annotations

from typing import Any

REQUIRED_TOP_LEVEL = (
    "dish_name",
    "cuisine",
    "estimated_servings",
    "ingredients",
    "equipment",
    "prep_time_minutes",
    "spice_level",
    "confidence",
    "ambiguity",
)

SPICE_LEVELS = frozenset({"none", "mild", "medium", "hot", "very_hot"})
AMBIGUITY_LEVELS = frozenset({"low", "medium", "high"})

# Minimum ingredient rows for shopping usefulness (tune per tier).
TIER_MIN_INGREDIENTS: dict[str, int] = {
    "easy": 5,
    "medium": 5,
    "ambiguous": 3,
    "adversarial": 0,
}


def validate_extract_response(
    obj: Any,
    *,
    tier: str,
) -> list[str]:
    """
    Return a list of human-readable validation errors (empty if valid).

    tier: easy | medium | ambiguous | adversarial (adversarial fixtures may be invalid-by-design).
    """
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["root must be an object"]

    for key in REQUIRED_TOP_LEVEL:
        if key not in obj:
            errors.append(f"missing top-level key: {key}")

    if errors:
        return errors

    if not isinstance(obj["ingredients"], list):
        errors.append("ingredients must be a list")
    if not isinstance(obj["equipment"], list):
        errors.append("equipment must be a list")
    if not isinstance(obj["ambiguity"], dict):
        errors.append("ambiguity must be an object")

    if errors:
        return errors

    amb = obj["ambiguity"]
    if amb.get("level") not in AMBIGUITY_LEVELS:
        errors.append(f"ambiguity.level must be one of {sorted(AMBIGUITY_LEVELS)}")
    if not isinstance(amb.get("alternates"), list):
        errors.append("ambiguity.alternates must be a list")
    else:
        for i, alt in enumerate(amb["alternates"]):
            if not isinstance(alt, dict):
                errors.append(f"alternates[{i}] must be an object")
                continue
            if "cuisine" not in alt or "protein" not in alt:
                errors.append(f"alternates[{i}] must include cuisine and protein")

    if obj.get("spice_level") not in SPICE_LEVELS:
        errors.append(f"spice_level must be one of {sorted(SPICE_LEVELS)}")

    try:
        servings = int(obj["estimated_servings"])
        if not (1 <= servings <= 24):
            errors.append("estimated_servings must be between 1 and 24")
    except (TypeError, ValueError):
        errors.append("estimated_servings must be an integer")

    try:
        prep = int(obj["prep_time_minutes"])
        if not (0 <= prep <= 480):
            errors.append("prep_time_minutes must be between 0 and 480")
    except (TypeError, ValueError):
        errors.append("prep_time_minutes must be an integer")

    try:
        conf = float(obj["confidence"])
        if not (0.0 <= conf <= 1.0):
            errors.append("confidence must be between 0 and 1")
    except (TypeError, ValueError):
        errors.append("confidence must be a number")

    names: list[str] = []
    for i, row in enumerate(obj["ingredients"]):
        if not isinstance(row, dict):
            errors.append(f"ingredients[{i}] must be an object")
            continue
        if "name" not in row:
            errors.append(f"ingredients[{i}] missing name")
            continue
        n = str(row["name"]).strip().lower()
        if not n:
            errors.append(f"ingredients[{i}] has empty name")
        else:
            names.append(n)

    if len(names) != len(set(names)):
        errors.append("duplicate ingredient names after merge (canonical names must be unique)")

    min_ing = TIER_MIN_INGREDIENTS.get(tier, 5)
    if min_ing and len(names) < min_ing:
        errors.append(f"expected at least {min_ing} ingredients for tier {tier!r}, got {len(names)}")

    return errors
