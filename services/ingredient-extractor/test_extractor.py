"""Quick manual test: calls the Anthropic-backed extractor for a sample dish."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python test_extractor.py` from this folder or `python services/ingredient-extractor/test_extractor.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from extractor import extract_ingredients_json

if __name__ == "__main__":
    result = extract_ingredients_json("chicken biryani")
    print(json.dumps(result, indent=2, ensure_ascii=False))
