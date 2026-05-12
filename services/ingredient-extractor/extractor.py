"""Call Claude to infer structured ingredients for a dish name."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import anthropic

from ingredient_pipeline import apply_heuristic_metadata, process_extracted_payload

_SERVICE_DIR = Path(__file__).resolve().parent


def _apply_env_file(path: Path, *, override: bool) -> None:
    """Minimal `.env` parsing (KEY=value lines); no third-party dependency."""
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value


def _load_dotenv_files() -> None:
    """Load service `.env` first; if the API key is still empty, try cwd `.env`."""
    svc = _SERVICE_DIR / ".env"
    cwd = Path.cwd() / ".env"
    if svc.is_file():
        _apply_env_file(svc, override=True)
    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        if cwd.is_file() and (not svc.is_file() or cwd.resolve() != svc.resolve()):
            _apply_env_file(cwd, override=True)


_load_dotenv_files()

# JSON shape the model must return (single source of truth for prompt + parsing).
INGREDIENT_EXTRACTION_JSON_SPEC = """
{
  "dish_name": "<string, normalized title case>",
  "cuisine": "<string: primary cuisine or region label, e.g. North Indian, Italian, Mexican; use Unknown if truly unclear>",
  "estimated_servings": <integer: typical number of portions this recipe serves>,
  "ingredients": [
    {
      "name": "<ingredient name, lowercase when generic (paneer, olive oil)>",
      "quantity": "<string: decimal number as text, e.g. 250, 0.5, 1.25; use empty string if not inferable>",
      "unit": "<string: standardized unit from the allowed list below, or empty string if none>",
      "optional": <true if garnish or clearly optional>,
      "use": "<short role when the same ingredient appears in multiple roles, e.g. marinade, topping, sauce, garnish, dough, filling, broth, other; empty string if not applicable>"
    }
  ],
  "equipment": ["<string: notable equipment, e.g. blender, dutch oven, wok; omit minor items like bowls>"],
  "prep_time_minutes": <integer: active prep time excluding long passive marinating or overnight rests>,
  "spice_level": "<one of: none, mild, medium, hot, very_hot>",
  "confidence": <number 0-1; placeholder only — the server overwrites with a heuristic score>,
  "ambiguity": {
    "level": "<low, medium, high>",
    "alternates": [
      {"cuisine": "<e.g. Thai, Japanese, Caribbean>", "protein": "<e.g. chicken, beef, goat, tofu, none>"}
    ]
  }
}
"""

DEFAULT_MODEL = "claude-sonnet-4-20250514"


def _strip_json_fence(text: str) -> str:
    """Remove optional ```json ... ``` wrapping from model output."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def extract_ingredients_json(
    dish_name: str,
    *,
    ambiguity_mode: str = "default",
) -> dict[str, Any]:
    """
    Given a dish name, ask Claude for structured ingredient data and return it as a dict.

    Uses ANTHROPIC_API_KEY from the environment. Optional ANTHROPIC_MODEL overrides the model.

    ambiguity_mode:
      - "default": single best interpretation; alternates must be [].
      - "alternates": if the dish name is medium/high ambiguity, include up to 3 alternates; else [].
    """
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is missing or empty. Put the key on the same line as "
            "ANTHROPIC_API_KEY= with no line break after '=', save the file, and ensure "
            "you are not editing only an unsaved buffer (disk path: "
            f"{_SERVICE_DIR / '.env'}). You can also export ANTHROPIC_API_KEY in your shell."
        )

    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)

    if ambiguity_mode not in {"default", "alternates"}:
        ambiguity_mode = "default"

    ambiguity_rules = (
        'Ambiguity policy is "default": set ambiguity.alternates to [] always. Still set ambiguity.level from the dish name clarity.'
        if ambiguity_mode == "default"
        else 'Ambiguity policy is "alternates": set ambiguity.level from clarity. If level is medium or high, include up to 3 objects in ambiguity.alternates, each with "cuisine" and "protein" (primary animal protein or "none"/"tofu" for vegetarian) for a plausible alternate reading. If low, alternates may be []. The main dish_name/cuisine/ingredients must reflect your single best primary interpretation for shopping.'
    )

    user_prompt = f"""You are helping a cooking vs. ordering price comparison app infer what goes into a dish.

Dish name: {dish_name!r}

Infer a plausible home-cooked version of this dish. Return ONLY valid JSON (no markdown fences, no commentary before or after) matching exactly this structure:

{INGREDIENT_EXTRACTION_JSON_SPEC}

Allowed ingredient units (pick one per ingredient; convert mentally if needed):
  Mass: g, kg, oz, lb
  Volume: ml, l, cup, tbsp, tsp, fl_oz
  Count: piece, clove, bunch, leaf, slice, sheet, pinch
  Other: whole, to_taste — only when quantity is not meaningful; prefer g/ml/cup when you can estimate

Rules:
- {ambiguity_rules}
- Use realistic quantities as strings and standardized units only from the list (or empty string when unknown).
- Tag cuisine honestly; use Unknown when the dish name does not imply a specific cuisine. Numeric confidence in JSON is a placeholder — the API replaces it with a deterministic score from ambiguity level, input length, and cuisine clarity.
- For ingredients that play multiple roles (e.g. onion in marinade vs topping), output separate lines with the same name and distinct non-empty "use" values so downstream merging can combine them.
- Include staple ingredients that are usually necessary unless the dish name is extremely generic.
- equipment should list tools that change shopping or effort (pressure cooker, food processor), not every spoon.
- spice_level reflects the finished dish heat, not raw chile count alone.
- If the name is ambiguous, pick the most common interpretation for the main payload; reflect uncertainty in ambiguity.level (and alternates when policy allows), not in the numeric confidence field."""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": user_prompt}],
    )

    parts: list[str] = []
    for block in message.content:
        if block.type == "text":
            parts.append(block.text)
    raw = "".join(parts)

    try:
        data = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError as e:
        raise ValueError(f"Model did not return valid JSON: {e}\n---\n{raw}") from e

    data = process_extracted_payload(data)
    return apply_heuristic_metadata(dish_name.strip(), data)
