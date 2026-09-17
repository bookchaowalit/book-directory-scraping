from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from location_intelligence.analysis import analyze_categories
from location_intelligence.models import CandidateCategory, SearchRequest, haversine_m
from location_intelligence.providers import FixtureProvider, GooglePlacesProvider, collect_places
from location_intelligence.report import build_report, render_markdown, write_report


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "bangkapi_sample.json"
CATEGORIES = (
    CandidateCategory("coffee", ("cafe", "coffee_shop"), ("coffee", "กาแฟ")),
    CandidateCategory("laundry", ("laundry",), ("laundry", "ซักผ้า")),
    CandidateCategory("pet", ("pet_store",), ("pet", "สัตว์เลี้ยง")),
)


class LocationIntelligenceTests(unittest.TestCase):
    def test_haversine_zero_and_positive_distance(self) -> None:
        self.assertAlmostEqual(haversine_m(13.0, 100.0, 13.0, 100.0), 0.0)
        self.assertGreater(haversine_m(13.0, 100.0, 13.001, 100.0), 100)

    def test_fixture_collection_is_bounded_and_deduplicated(self) -> None:
        collection = collect_places(
            FixtureProvider(FIXTURE),
            center_lat=13.7652,
            center_lng=100.6431,
            radii_m=[500, 1000],
            categories=CATEGORIES,
            max_results=20,
            max_requests=10,
            collected_at="2026-09-13T00:00:00Z",
        )
        self.assertEqual(collection["request_count"], 6)
        self.assertEqual(len(collection["records"]), 3)
        self.assertEqual(collection["errors"], [])
        self.assertEqual(collection["status"], "success")
        coffee = next(row for row in collection["records"] if row["place_id"] == "fixture-coffee-1")
        self.assertEqual(coffee["matched_radii_m"], [500.0, 1000.0])
        self.assertEqual(coffee["expires_at"], "2026-10-13T00:00:00Z")

    def test_fixture_provider_respects_radius(self) -> None:
        payload = {
            "metadata": {"center": {"lat": 13.7652, "lng": 100.6431}},
            "places": [
                {
                    "id": "near",
                    "name": "Near Laundry",
                    "category": "laundry",
                    "location": {"lat": 13.766, "lng": 100.643},
                },
                {
                    "id": "far",
                    "name": "Far Laundry",
                    "category": "laundry",
                    "location": {"lat": 13.80, "lng": 100.643},
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            collection = collect_places(
                FixtureProvider(path),
                center_lat=13.7652,
                center_lng=100.6431,
                radii_m=[500],
                categories=(CATEGORIES[1],),
                max_requests=1,
            )
        self.assertEqual([row["place_id"] for row in collection["records"]], ["near"])

    def test_score_keeps_missing_demand_explicit(self) -> None:
        collection = collect_places(
            FixtureProvider(FIXTURE),
            center_lat=13.7652,
            center_lng=100.6431,
            radii_m=[1000],
            categories=CATEGORIES,
            max_requests=3,
            collected_at="2026-09-13T00:00:00Z",
        )
        scorecards = analyze_categories(collection["records"], radius_m=1000, categories=CATEGORIES)
        pet = next(item for item in scorecards if item["category"] == "pet")
        self.assertIsNone(pet["score"])
        self.assertEqual(pet["status"], "validate_demand")
        coffee = next(item for item in scorecards if item["category"] == "coffee")
        self.assertIsNotNone(coffee["score"])
        self.assertIn("evidence_ids", coffee)

    def test_google_provider_builds_bounded_thai_request(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"places": []}'

        request = SearchRequest(
            13.7652,
            100.6431,
            1000,
            CATEGORIES[0],
            max_results=20,
        )
        with patch("location_intelligence.providers.urlopen", return_value=FakeResponse()) as mocked:
            self.assertEqual(GooglePlacesProvider("test-key").search(request), [])
        sent = mocked.call_args.args[0]
        body = json.loads(sent.data.decode("utf-8"))
        self.assertEqual(body["maxResultCount"], 20)
        self.assertEqual(body["languageCode"], "th")
        self.assertEqual(body["regionCode"], "TH")
        self.assertIn("places.userRatingCount", sent.get_header("X-goog-fieldmask"))

    def test_report_writes_json_and_markdown(self) -> None:
        collection = collect_places(
            FixtureProvider(FIXTURE),
            center_lat=13.7652,
            center_lng=100.6431,
            radii_m=[1000],
            categories=CATEGORIES,
            max_requests=3,
            collected_at="2026-09-13T00:00:00Z",
        )
        scorecards = analyze_categories(collection["records"], radius_m=1000, categories=CATEGORIES)
        report = build_report(
            center_lat=13.7652,
            center_lng=100.6431,
            radii_m=[1000],
            analysis_radius_m=1000,
            collection=collection,
            scorecards=scorecards,
        )
        self.assertEqual(report["schema_version"], "location-opportunity.v1")
        self.assertIn("Nearby Search", render_markdown(report))
        with tempfile.TemporaryDirectory() as directory:
            json_path, markdown_path = write_report(report, directory)
            payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "location-opportunity.v1")
            self.assertTrue(Path(markdown_path).is_file())


if __name__ == "__main__":
    unittest.main()
