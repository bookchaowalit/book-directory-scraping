"""Shared models and deterministic normalization helpers.

The module deliberately uses only the Python standard library.  A research
run can therefore be replayed from a fixture without credentials or network
access, while the live provider can be enabled explicitly by the operator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import math
import re
from typing import Any, Iterable


EARTH_RADIUS_M = 6_371_000.0
MAX_NEARBY_RESULTS = 20
GOOGLE_DATA_TTL_DAYS = 30


@dataclass(frozen=True)
class CandidateCategory:
    """A business category used for both query planning and scoring."""

    name: str
    google_types: tuple[str, ...]
    keywords: tuple[str, ...] = ()


DEFAULT_CATEGORIES: tuple[CandidateCategory, ...] = (
    CandidateCategory("coffee", ("cafe", "coffee_shop"), ("coffee", "กาแฟ", "คาเฟ่")),
    CandidateCategory("food", ("restaurant", "meal_takeaway"), ("restaurant", "อาหาร")),
    CandidateCategory("laundry", ("laundry",), ("laundry", "ซักรีด", "ซักผ้า")),
    # Google Places has no dedicated cleaning-service filter in the current
    # type table; ``service`` is a broad discovery proxy and needs manual
    # validation or a keyword/Text Search pass before production use.
    CandidateCategory("cleaning", ("service",), ("cleaning", "maid", "แม่บ้าน", "ทำความสะอาด")),
    CandidateCategory("pet", ("pet_store", "pet_care"), ("pet", "สัตว์เลี้ยง")),
    CandidateCategory("beauty", ("beauty_salon", "hair_salon"), ("beauty", "salon", "เสริมสวย")),
    CandidateCategory("healthy_meal", ("health_food_store", "restaurant"), ("healthy", "สุขภาพ", "คลีน")),
)


@dataclass(frozen=True)
class SearchRequest:
    center_lat: float
    center_lng: float
    radius_m: float
    category: CandidateCategory
    max_results: int = MAX_NEARBY_RESULTS
    rank_preference: str = "POPULARITY"

    def __post_init__(self) -> None:
        if not (-90 <= self.center_lat <= 90):
            raise ValueError("center_lat must be between -90 and 90")
        if not (-180 <= self.center_lng <= 180):
            raise ValueError("center_lng must be between -180 and 180")
        if not (0 < self.radius_m <= 50_000):
            raise ValueError("radius_m must be > 0 and <= 50000")
        if not (1 <= self.max_results <= MAX_NEARBY_RESULTS):
            raise ValueError("max_results must be between 1 and 20")
        if self.rank_preference not in {"POPULARITY", "DISTANCE"}:
            raise ValueError("rank_preference must be POPULARITY or DISTANCE")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def expires_at(collected_at: str, ttl_days: int = GOOGLE_DATA_TTL_DAYS) -> str:
    """Return an explicit expiry for source data with retention restrictions."""

    parsed = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
    return (parsed + timedelta(days=ttl_days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def haversine_m(lat_a: float, lng_a: float, lat_b: float, lng_b: float) -> float:
    """Great-circle distance in metres."""

    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lng_b - lng_a)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, value)))


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or "").strip()
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _location(raw: dict[str, Any]) -> tuple[float, float] | None:
    geometry = raw.get("geometry") or {}
    location = raw.get("location") or geometry.get("location") or {}
    lat = _float(location.get("latitude", location.get("lat")))
    lng = _float(location.get("longitude", location.get("lng")))
    if lat is None or lng is None:
        lat = _float(raw.get("lat", raw.get("latitude")))
        lng = _float(raw.get("lng", raw.get("longitude")))
    if lat is None or lng is None:
        return None
    return lat, lng


def _types(raw: dict[str, Any]) -> list[str]:
    values = raw.get("types") or raw.get("categories") or []
    if isinstance(values, str):
        values = re.split(r"[,|]", values)
    return [str(item).strip().lower() for item in values if str(item).strip()]


def classify_category(
    raw: dict[str, Any],
    requested_category: CandidateCategory,
    categories: Iterable[CandidateCategory],
) -> str:
    explicit = str(raw.get("category") or "").strip().lower()
    names = {category.name for category in categories}
    if explicit in names:
        return explicit
    # A query is already scoped to one candidate category.  Keep generic
    # Google types (for example ``restaurant``) attached to that query unless
    # a fixture or source supplies an explicit canonical category.  This
    # avoids classifying a healthy-meal query as generic food merely because
    # both use the restaurant type.
    if requested_category.name in names:
        primary = str(raw.get("primaryType") or raw.get("primary_type") or "").lower()
        raw_types = set(_types(raw))
        if primary in requested_category.google_types or raw_types & set(requested_category.google_types):
            return requested_category.name
    haystack = " ".join(
        [
            str(raw.get("primaryType") or raw.get("primary_type") or "").lower(),
            " ".join(_types(raw)),
            _text(raw.get("displayName") or raw.get("name")).lower(),
        ]
    )
    for category in categories:
        if any(token.lower() in haystack for token in (*category.google_types, *category.keywords)):
            return category.name
    return requested_category.name


def normalize_place(
    raw: dict[str, Any],
    *,
    request: SearchRequest,
    source: str,
    collected_at: str,
    categories: Iterable[CandidateCategory] = DEFAULT_CATEGORIES,
) -> dict[str, Any] | None:
    """Normalize a Places or fixture row into the report contract."""

    location = _location(raw)
    if location is None:
        return None
    place_id = _text(raw.get("id") or raw.get("placeId") or raw.get("place_id"))
    name = _text(raw.get("displayName") or raw.get("name"))
    if not place_id or not name:
        return None
    lat, lng = location
    distance = haversine_m(request.center_lat, request.center_lng, lat, lng)
    category = classify_category(raw, request.category, categories)
    rating = _float(raw.get("rating"))
    review_count = _int(raw.get("userRatingCount") or raw.get("user_rating_count"))
    matched_category = request.category.name
    evidence_id = hashlib.sha256(
        f"{source}|{place_id}|{collected_at[:10]}".encode("utf-8")
    ).hexdigest()[:16]
    return {
        "place_id": place_id,
        "name": name,
        "category": category,
        "matched_categories": [matched_category],
        "types": _types(raw),
        "primary_type": _text(raw.get("primaryType") or raw.get("primary_type")),
        "formatted_address": _text(raw.get("formattedAddress") or raw.get("formatted_address")) or None,
        "lat": round(lat, 7),
        "lng": round(lng, 7),
        "distance_m": round(distance, 1),
        "matched_radii_m": [request.radius_m],
        "rating": rating,
        "user_rating_count": review_count,
        "price_level": _text(raw.get("priceLevel") or raw.get("price_level")) or None,
        "business_status": _text(raw.get("businessStatus") or raw.get("business_status")) or None,
        "delivery": raw.get("delivery"),
        "takeout": raw.get("takeout"),
        "opening_hours": raw.get("regularOpeningHours") or raw.get("opening_hours"),
        "closing_hour": _float(raw.get("closing_hour") or raw.get("open_until")),
        "website_uri": _text(raw.get("websiteUri") or raw.get("website_uri")) or None,
        "google_maps_uri": _text(raw.get("googleMapsUri") or raw.get("google_maps_uri")) or None,
        "source": source,
        "collected_at": collected_at,
        "expires_at": expires_at(collected_at),
        "evidence_id": evidence_id,
        "data_status": "observed",
    }
