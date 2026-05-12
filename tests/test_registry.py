from ingredient_registry import enrich_ingredients_with_registry, lookup_ingredient_identity


def test_lookup_white_onion_maps_to_onion_id() -> None:
    hit = lookup_ingredient_identity("white onion")
    assert hit is not None
    assert hit["id"] == "ingredient_onion"


def test_lookup_cilantro_after_canonical_map() -> None:
    hit = lookup_ingredient_identity("cilantro")
    assert hit is not None
    assert hit["id"] == "ingredient_coriander_leaves"


def test_enrich_adds_ids() -> None:
    rows = [{"name": "onion", "quantity": "1", "unit": "piece", "optional": False}]
    out = enrich_ingredients_with_registry(rows)
    assert out[0]["ingredient_id"] == "ingredient_onion"
    assert out[0]["category"] == "vegetable"
    assert out[0]["registry_canonical_name"] == "onion"


def test_enrich_unknown() -> None:
    rows = [{"name": "dragon fruit", "quantity": "1", "unit": "piece", "optional": False}]
    out = enrich_ingredients_with_registry(rows)
    assert out[0]["ingredient_id"] is None
    assert out[0]["category"] == "unknown"
