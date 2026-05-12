"""Golden-style contract tests for extract JSON (no live LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from response_contract import validate_extract_response

_FIXTURE_ROOT = Path(__file__).resolve().parent


def _load_cases(subdir: str) -> list[tuple[Path, str, dict]]:
    out: list[tuple[Path, str, dict]] = []
    d = _FIXTURE_ROOT / subdir
    if not d.is_dir():
        return out
    for path in sorted(d.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append((path, data["tier"], data["response"]))
    return out


@pytest.mark.parametrize(
    "path,tier,body",
    _load_cases("easy") + _load_cases("medium") + _load_cases("ambiguous"),
)
def test_fixture_validates(path: Path, tier: str, body: dict) -> None:
    errs = validate_extract_response(body, tier=tier)
    assert errs == [], f"{path}: {errs}"


@pytest.mark.parametrize("path,tier,body", _load_cases("adversarial"))
def test_adversarial_fixture_fails_contract(path: Path, tier: str, body: dict) -> None:
    errs = validate_extract_response(body, tier=tier)
    assert any("duplicate ingredient" in e for e in errs), f"{path}: expected duplicate error, got {errs}"


def test_heuristic_confidence_grandma_style_curry() -> None:
    from ingredient_pipeline import apply_heuristic_metadata

    dish = "grandma style curry"
    payload = {
        "cuisine": "Indian",
        "ambiguity": {"level": "medium", "alternates": []},
    }
    out = apply_heuristic_metadata(dish, payload)
    assert out["confidence"] == 0.85
    assert out["ambiguity"]["alternates"] == []


def test_heuristic_confidence_high_ambiguity_unknown_cuisine_short() -> None:
    from ingredient_pipeline import apply_heuristic_metadata

    dish = "x"
    payload = {
        "cuisine": "Unknown",
        "ambiguity": {"level": "high", "alternates": []},
    }
    out = apply_heuristic_metadata(dish, payload)
    # base 0.85 -0.25 (high) -0.15 (underspecified: <3 words or <3 chars, one deduction) -0.1 (unknown cuisine)
    assert out["confidence"] == 0.35


def test_alternates_legacy_label_maps_to_protein() -> None:
    from ingredient_pipeline import apply_heuristic_metadata

    out = apply_heuristic_metadata(
        "curry",
        {
            "cuisine": "Indian",
            "ambiguity": {
                "level": "medium",
                "alternates": [{"cuisine": "Thai", "label": "green curry"}],
            },
        },
    )
    assert out["ambiguity"]["alternates"] == [{"cuisine": "Thai", "protein": "green curry"}]
