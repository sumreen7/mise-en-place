"""Pytest path: service package lives under services/ingredient-extractor/."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SERVICE = _ROOT / "services" / "ingredient-extractor"
if str(_SERVICE) not in sys.path:
    sys.path.insert(0, str(_SERVICE))
