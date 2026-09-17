"""JSON and Markdown outputs for a location analysis run."""

from __future__ import annotations

import json
from typing import Any


def build_report(
    *,
    center_lat: float,
    center_lng: float,
    radii_m: list[float],
    analysis_radius_m: float,
    collection: dict[str, Any],
    scorecards: list[dict[str, Any]],
    input_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "location-opportunity.v1",
        "generated_at": collection["collected_at"],
        "location": {
            "center_lat": center_lat,
            "center_lng": center_lng,
            "radii_m": radii_m,
            "analysis_radius_m": analysis_radius_m,
        },
        "input_profile": input_profile or {},
        "collection": {
            "source": collection["source"],
            "status": collection.get("status", "success"),
            "collected_at": collection["collected_at"],
            "expires_at": _latest_expiry(collection.get("records", [])),
            "request_count": collection["request_count"],
            "query_plan": collection["query_plan"],
            "query_results": collection["query_results"],
            "errors": collection["errors"],
            "coverage_warning": (
                "Nearby Search คืนได้สูงสุด 20 ผลต่อคำขอ; รายการนี้คือร้านที่พบจาก query plan "
                "ไม่ใช่สำมะโนร้านทั้งหมด"
            ),
            "demand_warning": "จำนวนรีวิวเป็น demand proxy; ยังไม่ใช่ยอดขายหรือ review velocity",
        },
        "scorecards": scorecards,
        "places": collection["records"],
    }


def _latest_expiry(records: list[dict[str, Any]]) -> str | None:
    values = [str(row.get("expires_at")) for row in records if row.get("expires_at")]
    return max(values) if values else None


def render_markdown(report: dict[str, Any]) -> str:
    location = report["location"]
    collection = report["collection"]
    lines = [
        "# Location Opportunity Analysis",
        "",
        f"- Schema: `{report['schema_version']}`",
        f"- Source: `{collection['source']}`",
        f"- Center: `{location['center_lat']}, {location['center_lng']}`",
        f"- Analysis radius: `{location['analysis_radius_m']} m`",
        f"- Generated: `{report['generated_at']}`",
        "",
        "> รายงานนี้จัดอันดับหัวข้อที่ควรตรวจสอบต่อ ไม่ใช่การยืนยันยอดขายหรือ market gap",
        "",
        "## Opportunity scorecards",
        "",
        "| Category | Businesses | Reviews | Score | Confidence | Status |",
        "|---|---:|---:|---:|---|---|",
    ]
    for item in report["scorecards"]:
        score = "—" if item["score"] is None else f"{item['score']:.2f}"
        lines.append(
            f"| {item['category']} | {item['business_count']} | {item['total_user_rating_count']} | "
            f"{score} | {item['confidence']['label']} ({item['confidence']['score']:.2f}) | {item['status']} |"
        )
    lines.extend(
        [
            "",
            "## Recommended next checks",
            "",
        ]
    )
    for item in report["scorecards"]:
        lines.append(f"- **{item['category']}** — {item['recommendation']}")
    lines.extend(
        [
            "",
            "## Collection notes",
            "",
            f"- Query requests: `{collection['request_count']}`",
            f"- Unique places retained: `{len(report['places'])}`",
            f"- Data expiry: `{collection['expires_at'] or 'not available'}`",
            f"- {collection['coverage_warning']}",
            f"- {collection['demand_warning']}",
        ]
    )
    if collection["errors"]:
        lines.extend(["", "### Query errors", ""])
        for error in collection["errors"]:
            lines.append(f"- `{error['category']}` at `{error['radius_m']} m`: {error['error']}")
    lines.extend(["", "## Evidence", "", "Every place row has an `evidence_id`, source, collection time, expiry, and maps URL when supplied."])
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], output_dir: str) -> tuple[str, str]:
    from pathlib import Path

    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    json_path = path / "location-analysis.json"
    markdown_path = path / "location-analysis.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return str(json_path), str(markdown_path)
