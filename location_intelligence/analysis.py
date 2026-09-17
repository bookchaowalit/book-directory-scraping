"""Transparent opportunity scoring from normalized place observations."""

from __future__ import annotations

import math
from statistics import mean
from typing import Any, Iterable

from .models import CandidateCategory, DEFAULT_CATEGORIES


WEIGHTS = {
    "demand_proxy": 0.30,
    "quality_gap": 0.25,
    "convenience_gap": 0.20,
    "competition_gap": 0.25,
}


def _known(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _confidence(known_dimensions: int, count: int, source: str) -> tuple[float, str]:
    dimension_coverage = known_dimensions / len(WEIGHTS)
    evidence_coverage = min(1.0, count / 5.0)
    source_factor = 0.85 if source == "fixture" else 1.0
    score = round((0.55 * dimension_coverage + 0.45 * evidence_coverage) * source_factor, 2)
    label = "high" if score >= 0.75 else "medium" if score >= 0.45 else "low"
    return score, label


def _convenience_gap(rows: list[dict[str, Any]]) -> float | None:
    service_values = [
        not bool(row.get("delivery")) and not bool(row.get("takeout"))
        for row in rows
        if row.get("delivery") is not None or row.get("takeout") is not None
    ]
    closing_values = [
        float(row["closing_hour"]) < 20
        for row in rows
        if row.get("closing_hour") is not None
    ]
    values = service_values + closing_values
    return round(mean(values) * 5, 2) if values else None


def _category_rows(records: Iterable[dict[str, Any]], category: str, radius_m: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in records:
        if row.get("distance_m", float("inf")) > radius_m:
            continue
        categories = set(row.get("matched_categories") or [])
        if row.get("category") == category or category in categories:
            rows.append(row)
    return rows


def analyze_categories(
    records: Iterable[dict[str, Any]],
    *,
    radius_m: float,
    categories: Iterable[CandidateCategory] = DEFAULT_CATEGORIES,
    source: str = "fixture",
) -> list[dict[str, Any]]:
    """Return one auditable scorecard per candidate category.

    Scores are a prioritization aid.  Missing evidence is kept as ``None``
    and excluded from the weighted average; it never silently becomes zero.
    """

    records = list(records)
    all_totals: dict[str, int] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for category in categories:
        rows = _category_rows(records, category.name, radius_m)
        grouped[category.name] = rows
        all_totals[category.name] = sum(
            int(row["user_rating_count"])
            for row in rows
            if row.get("user_rating_count") is not None
        )
    max_total = max(all_totals.values(), default=0)
    output: list[dict[str, Any]] = []
    for category in categories:
        rows = grouped[category.name]
        count = len(rows)
        total_reviews = all_totals[category.name]
        ratings = [float(row["rating"]) for row in rows if _known(row.get("rating"))]
        low_rated = [rating for rating in ratings if rating < 4.2]
        demand = round(5 * math.sqrt(total_reviews / max_total), 2) if max_total and total_reviews else None
        quality = round(5 * len(low_rated) / len(ratings), 2) if ratings else None
        convenience = _convenience_gap(rows)
        competition = round(5 / (1 + math.sqrt(count)), 2) if count else None
        dimensions = {
            "demand_proxy": demand,
            "quality_gap": quality,
            "convenience_gap": convenience,
            "competition_gap": competition,
        }
        known = {key: value for key, value in dimensions.items() if _known(value)}
        if not rows or not known:
            score = None
            status = "validate_demand"
        else:
            denominator = sum(WEIGHTS[key] for key in known)
            score = round(sum(value * WEIGHTS[key] for key, value in known.items()) / denominator, 2)
            status = "pilot_candidate" if score >= 3.5 else "research_more"
        confidence_score, confidence_label = _confidence(len(known), count, source)
        if not rows:
            recommendation = "ยังไม่พบร้านในข้อมูลชุดนี้; ตรวจ demand ด้วยการสัมภาษณ์หรือ smoke test ก่อนสรุปว่าเป็นช่องว่าง"
        elif score is not None and score >= 3.5:
            recommendation = "เหมาะสำหรับออกแบบ smoke test ขนาดเล็ก โดยยืนยัน willingness-to-pay ก่อนลงทุน"
        else:
            recommendation = "เก็บหลักฐาน pain point และ convenience เพิ่มก่อนเลือกเป็น pilot"
        output.append(
            {
                "category": category.name,
                "radius_m": radius_m,
                "business_count": count,
                "total_user_rating_count": total_reviews,
                "average_rating": round(mean(ratings), 2) if ratings else None,
                "low_rating_share": round(len(low_rated) / len(ratings), 2) if ratings else None,
                "dimensions": dimensions,
                "score": score,
                "status": status,
                "confidence": {"score": confidence_score, "label": confidence_label},
                "evidence_ids": [row["evidence_id"] for row in rows],
                "recommendation": recommendation,
            }
        )
    return sorted(output, key=lambda item: (item["score"] is None, -(item["score"] or 0), item["category"]))
