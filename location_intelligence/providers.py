"""Fixture and Google Places (New) collection adapters."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import (
    CandidateCategory,
    DEFAULT_CATEGORIES,
    SearchRequest,
    _location,
    haversine_m,
    normalize_place,
    utc_now_iso,
)


class ProviderError(RuntimeError):
    """A provider failure safe to show without exposing response payloads."""


class FixtureProvider:
    """Read a local JSON capture; useful for demos, tests, and replay."""

    source_name = "fixture"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            self.places = payload
            self.metadata: dict[str, Any] = {}
        elif isinstance(payload, dict) and isinstance(payload.get("places"), list):
            self.places = payload["places"]
            self.metadata = payload.get("metadata") or {}
        else:
            raise ProviderError("fixture must be a JSON list or an object with a places list")

    def search(self, request: SearchRequest) -> list[dict[str, Any]]:
        """Return at most the same number of rows as the live endpoint."""

        requested = {request.category.name, *request.category.google_types, *request.category.keywords}
        rows: list[dict[str, Any]] = []
        for raw in self.places:
            if not isinstance(raw, dict):
                continue
            location = _location(raw)
            if location is None:
                continue
            if haversine_m(
                request.center_lat,
                request.center_lng,
                location[0],
                location[1],
            ) > request.radius_m:
                continue
            explicit = str(raw.get("category") or "").lower()
            types = {str(item).lower() for item in (raw.get("types") or [])}
            name = str(raw.get("name") or raw.get("displayName") or "").lower()
            if not (requested & ({explicit} | types) or any(token in name for token in request.category.keywords)):
                continue
            rows.append(raw)
        return rows[: request.max_results]


@dataclass
class GooglePlacesProvider:
    """Minimal stdlib client for Places API (New) Nearby Search."""

    api_key: str
    timeout_s: float = 20.0
    source_name: str = "google_places_new"
    endpoint: str = "https://places.googleapis.com/v1/places:searchNearby"

    FIELD_MASK = ",".join(
        (
            "places.id",
            "places.displayName",
            "places.primaryType",
            "places.types",
            "places.location",
            "places.formattedAddress",
            "places.rating",
            "places.userRatingCount",
            "places.priceLevel",
            "places.businessStatus",
            "places.regularOpeningHours",
            "places.delivery",
            "places.takeout",
            "places.websiteUri",
            "places.googleMapsUri",
        )
    )

    def search(self, request: SearchRequest) -> list[dict[str, Any]]:
        if not self.api_key.strip():
            raise ProviderError("GOOGLE_MAPS_API_KEY is empty")
        body = {
            "includedTypes": list(request.category.google_types),
            "maxResultCount": min(request.max_results, 20),
            "rankPreference": request.rank_preference,
            "languageCode": "th",
            "regionCode": "TH",
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": request.center_lat, "longitude": request.center_lng},
                    "radius": request.radius_m,
                }
            },
        }
        request_obj = Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": self.FIELD_MASK,
            },
            method="POST",
        )
        try:
            with urlopen(request_obj, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ProviderError(f"Google Places request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Google Places request failed: {type(exc).__name__}") from exc
        places = payload.get("places", [])
        if not isinstance(places, list):
            raise ProviderError("Google Places response did not contain a places list")
        return [row for row in places if isinstance(row, dict)]


def build_query_plan(
    *,
    center_lat: float,
    center_lng: float,
    radii_m: Iterable[float],
    categories: Iterable[CandidateCategory],
    max_results: int = 20,
    rank_preference: str = "POPULARITY",
) -> list[SearchRequest]:
    unique_radii: list[float] = []
    seen: set[float] = set()
    for radius in radii_m:
        value = float(radius)
        if value not in seen:
            unique_radii.append(value)
            seen.add(value)
    return [
        SearchRequest(center_lat, center_lng, radius, category, max_results, rank_preference)
        for radius in unique_radii
        for category in categories
    ]


def collect_places(
    provider: Any,
    *,
    center_lat: float,
    center_lng: float,
    radii_m: Iterable[float],
    categories: Iterable[CandidateCategory] = DEFAULT_CATEGORIES,
    max_results: int = 20,
    max_requests: int = 20,
    rank_preference: str = "POPULARITY",
    collected_at: str | None = None,
) -> dict[str, Any]:
    """Run bounded queries and merge duplicate places into one observation."""

    categories = tuple(categories)
    plan = build_query_plan(
        center_lat=center_lat,
        center_lng=center_lng,
        radii_m=radii_m,
        categories=categories,
        max_results=max_results,
        rank_preference=rank_preference,
    )
    if len(plan) > max_requests:
        raise ProviderError(
            f"query plan has {len(plan)} requests; increase --max-requests or reduce radii/categories"
        )
    captured = collected_at or utc_now_iso()
    by_id: dict[str, dict[str, Any]] = {}
    query_results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for request in plan:
        try:
            raw_rows = provider.search(request)
            normalized = [
                normalize_place(
                    row,
                    request=request,
                    source=provider.source_name,
                    collected_at=captured,
                    categories=categories,
                )
                for row in raw_rows
            ]
            normalized = [row for row in normalized if row is not None]
            for row in normalized:
                existing = by_id.get(row["place_id"])
                if existing is None:
                    by_id[row["place_id"]] = row
                    continue
                existing["matched_categories"] = sorted(
                    set(existing["matched_categories"]) | set(row["matched_categories"])
                )
                existing["matched_radii_m"] = sorted(
                    set(existing["matched_radii_m"]) | set(row["matched_radii_m"])
                )
                if row["distance_m"] < existing["distance_m"]:
                    existing["distance_m"] = row["distance_m"]
            query_results.append(
                {
                    "radius_m": request.radius_m,
                    "category": request.category.name,
                    "result_count": len(normalized),
                    "status": "ok",
                }
            )
        except ProviderError as exc:
            errors.append(
                {
                    "radius_m": request.radius_m,
                    "category": request.category.name,
                    "error": str(exc),
                }
            )
            query_results.append(
                {
                    "radius_m": request.radius_m,
                    "category": request.category.name,
                    "result_count": 0,
                    "status": "error",
                }
            )
    return {
        "records": sorted(by_id.values(), key=lambda row: (row["distance_m"], row["name"])),
        "query_plan": [
            {
                "radius_m": request.radius_m,
                "category": request.category.name,
                "included_types": list(request.category.google_types),
                "max_results": request.max_results,
                "rank_preference": request.rank_preference,
            }
            for request in plan
        ],
        "query_results": query_results,
        "errors": errors,
        "status": "partial" if errors else "success",
        "request_count": len(plan),
        "source": provider.source_name,
        "collected_at": captured,
    }
