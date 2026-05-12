"""HTTP API for ingredient extraction."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from extractor import extract_ingredients_json

app = FastAPI(title="Ingredient extractor", version="0.1.0")


class ExtractRequest(BaseModel):
    dish_name: str = Field(
        ...,
        min_length=1,
        description="Name of the dish to analyze",
    )
    ambiguity_mode: Literal["default", "alternates"] = Field(
        "default",
        description='default: single best reading, alternates=[]. alternates: model may add other plausible readings.',
    )


@app.post("/extract")
def extract(req: ExtractRequest) -> dict[str, Any]:
    """Infer structured ingredients for a dish name via Claude."""
    try:
        return extract_ingredients_json(
            req.dish_name.strip(),
            ambiguity_mode=req.ambiguity_mode,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
