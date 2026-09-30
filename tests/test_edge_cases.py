"""Edge cases for normalization and all-errored collections (offline)."""

from __future__ import annotations

from location_intelligence.analysis import analyze_categories
from location_intelligence.models import CandidateCategory, SearchRequest, normalize_place
from location_intelligence.providers import ProviderError, collect_places

COFFEE = CandidateCategory("coffee", ("cafe",), ("coffee",))
REQUEST = SearchRequest(13.76, 100.64, 500, COFFEE)
NOW = "2026-01-01T00:00:00+00:00"


def _norm(raw: dict) -> dict | None:
    return normalize_place(raw, request=REQUEST, source="fixture", collected_at=NOW, categories=(COFFEE,))


def test_missing_location_is_dropped() -> None:
    assert _norm({"id": "p1", "displayName": "Cafe"}) is None


def test_missing_id_or_name_is_dropped() -> None:
    assert _norm({"displayName": "Cafe", "lat": 13.76, "lng": 100.64}) is None
    assert _norm({"id": "p1", "lat": 13.76, "lng": 100.64}) is None


def test_missing_types_and_optional_fields_stay_unknown() -> None:
    row = _norm({"id": "p1", "name": "Somewhere", "lat": 13.76, "lng": 100.64})
    assert row is not None
    assert row["types"] == []
    assert row["category"] == "coffee"  # scoped to the requesting query
    assert row["rating"] is None
    assert row["user_rating_count"] is None
    assert row["distance_m"] == 0.0


def test_malformed_numbers_do_not_raise() -> None:
    row = _norm(
        {
            "id": "p1",
            "displayName": {"text": "Cafe"},
            "location": {"latitude": "13.76", "longitude": "100.64"},
            "rating": "n/a",
            "userRatingCount": "many",
            "types": "cafe|food",
        }
    )
    assert row is not None
    assert row["rating"] is None
    assert row["user_rating_count"] is None
    assert row["types"] == ["cafe", "food"]


class _AlwaysFails:
    source_name = "fixture"

    def search(self, request: SearchRequest) -> list[dict]:
        raise ProviderError("upstream unavailable")


def test_all_queries_errored_is_partial_and_scores_nothing() -> None:
    collection = collect_places(
        _AlwaysFails(),
        center_lat=13.76,
        center_lng=100.64,
        radii_m=[500, 1000],
        categories=(COFFEE,),
        collected_at=NOW,
    )
    assert collection["status"] == "partial"
    assert collection["records"] == []
    assert len(collection["errors"]) == collection["request_count"] == 2
    assert all(item["status"] == "error" for item in collection["query_results"])

    cards = analyze_categories(collection["records"], radius_m=500, categories=(COFFEE,))
    assert len(cards) == 1
    assert cards[0]["score"] is None
    assert cards[0]["status"] == "validate_demand"
    assert cards[0]["business_count"] == 0


def test_non_finite_numbers_are_treated_as_missing() -> None:
    assert _norm({"id": "p1", "name": "Cafe", "lat": "NaN", "lng": 100.64}) is None
    assert _norm({"id": "p1", "name": "Cafe", "lat": 13.76, "lng": float("inf")}) is None
    row = _norm({"id": "p1", "name": "Cafe", "lat": 13.76, "lng": 100.64, "rating": "nan", "closing_hour": "inf"})
    assert row is not None
    assert row["rating"] is None
    assert row["closing_hour"] is None


def test_nan_closing_hour_is_not_evidence() -> None:
    row = _norm({"id": "p1", "name": "Cafe", "lat": 13.76, "lng": 100.64, "types": ["cafe"], "closing_hour": "nan"})
    scorecards = analyze_categories([row], radius_m=500, categories=(COFFEE,))
    assert scorecards[0]["business_count"] == 1
    assert scorecards[0]["dimensions"]["convenience_gap"] is None
