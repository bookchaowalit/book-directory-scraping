"""Atomic report writes, billable-attempt accounting and CLI bounds."""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from location_intelligence import report as report_module
from location_intelligence.atomic_io import write_text_atomic
from location_intelligence.models import CandidateCategory
from location_intelligence.providers import GooglePlacesProvider, collect_places
from location_intelligence.report import build_report, render_markdown, write_report
from scripts.run_location_analysis import main as location_main

COFFEE = CandidateCategory("coffee", ("cafe",), ("coffee",))
FIXTURE = ROOT / "fixtures" / "bangkapi_sample.json"


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def _http_error(code: int) -> HTTPError:
    return HTTPError("https://places.example", code, "err", {}, io.BytesIO(b"{}"))


def test_write_text_atomic_replaces_and_leaves_no_temp(tmp_path):
    target = tmp_path / "nested" / "out.json"
    write_text_atomic(target, "old")
    write_text_atomic(target, "new ข้อมูล")
    assert target.read_text(encoding="utf-8") == "new ข้อมูล"
    assert [p.name for p in target.parent.iterdir()] == ["out.json"]


def test_write_text_atomic_keeps_previous_file_on_failure(tmp_path):
    target = tmp_path / "out.json"
    target.write_text("previous", encoding="utf-8")
    with patch("location_intelligence.atomic_io.os.replace", side_effect=OSError("disk")):
        with pytest.raises(OSError):
            write_text_atomic(target, "partial")
    assert target.read_text(encoding="utf-8") == "previous"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def _collection(provider):
    return collect_places(
        provider,
        center_lat=13.7652,
        center_lng=100.6431,
        radii_m=[500, 1000],
        categories=(COFFEE,),
        max_requests=2,
        collected_at="2026-09-13T00:00:00Z",
    )


def test_attempts_are_recorded_per_query_and_in_report():
    provider = GooglePlacesProvider("k", sleep=lambda _s: None)
    effects = [
        _http_error(503),
        _Response(b'{"places": []}'),
        _http_error(429),
        _http_error(429),
        _http_error(429),
    ]
    with patch("location_intelligence.providers.urlopen", side_effect=effects):
        collection = _collection(provider)
    assert [q["attempts"] for q in collection["query_results"]] == [2, 3]
    assert [q["status"] for q in collection["query_results"]] == ["ok", "error"]
    assert collection["attempt_count"] == 5
    report = build_report(
        center_lat=13.7652,
        center_lng=100.6431,
        radii_m=[500, 1000],
        analysis_radius_m=1000,
        collection=collection,
        scorecards=[],
    )
    assert report["collection"]["attempt_count"] == 5
    assert "HTTP attempts incl. retries: `5`" in render_markdown(report)


def test_fixture_provider_counts_one_attempt_per_query():
    from location_intelligence.providers import FixtureProvider

    collection = _collection(FixtureProvider(FIXTURE))
    assert collection["attempt_count"] == collection["request_count"] == 2


def test_write_report_does_not_touch_files_when_rendering_fails(tmp_path):
    (tmp_path / "location-analysis.json").write_text("previous", encoding="utf-8")
    with patch.object(report_module, "render_markdown", side_effect=KeyError("broken")):
        with pytest.raises(KeyError):
            write_report({"schema_version": "x"}, str(tmp_path))
    assert (tmp_path / "location-analysis.json").read_text(encoding="utf-8") == "previous"


@pytest.mark.parametrize(
    "extra",
    [
        ["--lat", "91", "--lng", "100"],
        ["--lat", "13", "--lng", "-181"],
        ["--lat", "13"],
        ["--budget-thb", "-1"],
        ["--hours-per-week", "169"],
    ],
)
def test_cli_rejects_out_of_range_inputs(extra):
    with redirect_stderr(io.StringIO()):
        with pytest.raises(SystemExit) as ctx:
            location_main(["--input", str(FIXTURE), "--dry-run", *extra])
    assert ctx.value.code == 2


def test_cli_accepts_valid_explicit_center(capsys):
    assert location_main(["--input", str(FIXTURE), "--dry-run", "--lat", "13.7", "--lng", "100.6"]) == 0
    assert json.loads(capsys.readouterr().out)["request_count"] > 0
