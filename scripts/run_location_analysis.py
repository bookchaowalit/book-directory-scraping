#!/usr/bin/env python3
"""Run a bounded location opportunity analysis.

Examples:

    python3 scripts/run_location_analysis.py \
      --input fixtures/bangkapi_sample.json \
      --radii 500,1000,3000 --analysis-radius 1000

    GOOGLE_MAPS_API_KEY=... python3 scripts/run_location_analysis.py \
      --live --lat 13.765 --lng 100.643 --categories coffee,laundry \
      --radii 500,1000 --max-requests 10
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from location_intelligence.analysis import analyze_categories
from location_intelligence.models import CandidateCategory, DEFAULT_CATEGORIES
from location_intelligence.providers import (
    FixtureProvider,
    GooglePlacesProvider,
    ProviderError,
    build_query_plan,
    collect_places,
)
from location_intelligence.report import build_report, write_report


def _csv_floats(value: str) -> list[float]:
    try:
        values = [float(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be comma-separated numbers") from exc
    if not values:
        raise argparse.ArgumentTypeError("at least one value is required")
    if any(item <= 0 or item > 50_000 for item in values):
        raise argparse.ArgumentTypeError("radii must be > 0 and <= 50000 metres")
    return values


def _categories(value: str) -> tuple[CandidateCategory, ...]:
    wanted = [item.strip().lower() for item in value.split(",") if item.strip()]
    available = {category.name: category for category in DEFAULT_CATEGORIES}
    unknown = [item for item in wanted if item not in available]
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown categories: {', '.join(unknown)}")
    return tuple(available[item] for item in wanted)


def _center(args: argparse.Namespace, provider: FixtureProvider | None) -> tuple[float, float]:
    if args.lat is not None and args.lng is not None:
        return args.lat, args.lng
    if provider is not None:
        center = provider.metadata.get("center") or {}
        if center.get("lat") is not None and center.get("lng") is not None:
            return float(center["lat"]), float(center["lng"])
    raise SystemExit("provide --lat and --lng, or use a fixture with metadata.center")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="Fixture JSON path; required unless --live is used")
    parser.add_argument("--live", action="store_true", help="Call Google Places API (New)")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lng", type=float)
    parser.add_argument("--radii", type=_csv_floats, default=[500.0, 1000.0, 3000.0])
    parser.add_argument("--analysis-radius", type=float, default=1000.0)
    parser.add_argument("--categories", type=_categories, default=DEFAULT_CATEGORIES)
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument("--max-requests", type=int, default=25)
    parser.add_argument("--rank", choices=("POPULARITY", "DISTANCE"), default="POPULARITY")
    parser.add_argument("--output-dir", default="data/location-research")
    parser.add_argument("--budget-thb", type=float)
    parser.add_argument("--hours-per-week", type=float)
    parser.add_argument("--dry-run", action="store_true", help="Print the bounded query plan only")
    args = parser.parse_args(argv)
    if args.live and args.input:
        parser.error("use either --input or --live, not both")
    if not args.live and not args.input:
        parser.error("--input is required unless --live is used")
    if args.max_results < 1 or args.max_results > 20:
        parser.error("--max-results must be between 1 and 20")
    if args.max_requests < 1:
        parser.error("--max-requests must be at least 1")
    if args.analysis_radius <= 0:
        parser.error("--analysis-radius must be greater than 0")
    if args.analysis_radius > max(args.radii):
        parser.error("--analysis-radius cannot exceed the largest collected radius")

    fixture = FixtureProvider(args.input) if args.input else None
    center_lat, center_lng = _center(args, fixture)
    plan = build_query_plan(
        center_lat=center_lat,
        center_lng=center_lng,
        radii_m=args.radii,
        categories=args.categories,
        max_results=args.max_results,
        rank_preference=args.rank,
    )
    if len(plan) > args.max_requests and not args.dry_run:
        parser.error(f"query plan has {len(plan)} requests; increase --max-requests or reduce inputs")
    if args.dry_run:
        print(json.dumps({"request_count": len(plan), "query_plan": [
            {"radius_m": req.radius_m, "category": req.category.name, "max_results": req.max_results}
            for req in plan
        ], "within_limit": len(plan) <= args.max_requests,
        "warning": None if len(plan) <= args.max_requests else "plan exceeds --max-requests; live collection will be blocked"
        }, ensure_ascii=False, indent=2))
        return 0

    provider = fixture if fixture is not None else GooglePlacesProvider(os.environ.get("GOOGLE_MAPS_API_KEY", ""))
    try:
        collection = collect_places(
            provider,
            center_lat=center_lat,
            center_lng=center_lng,
            radii_m=args.radii,
            categories=args.categories,
            max_results=args.max_results,
            max_requests=args.max_requests,
            rank_preference=args.rank,
        )
    except ProviderError as exc:
        parser.error(str(exc))
    scorecards = analyze_categories(
        collection["records"],
        radius_m=args.analysis_radius,
        categories=args.categories,
        source=collection["source"],
    )
    report = build_report(
        center_lat=center_lat,
        center_lng=center_lng,
        radii_m=list(args.radii),
        analysis_radius_m=args.analysis_radius,
        collection=collection,
        scorecards=scorecards,
        input_profile={
            "budget_thb": args.budget_thb,
            "hours_per_week": args.hours_per_week,
        },
    )
    json_path, markdown_path = write_report(report, args.output_dir)
    print(json.dumps({
        "status": collection.get("status", "success"),
        "source": collection["source"],
        "places": len(collection["records"]),
        "requests": collection["request_count"],
        "json": json_path,
        "markdown": markdown_path,
        "errors": len(collection["errors"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
