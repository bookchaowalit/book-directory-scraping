# Upgrade plan — book-directory-scraping

## Current state

Score: **8/10** (pass 1: 6 -> 7; pass 2: 7 -> 7.5; pass 3: 7.5 -> 8) — the stdlib-only
location-intelligence pipeline is bounded, fixture-tested, retries Google
Places transient errors safely, and has lint + offline CI. No dead legacy code
remains; edge cases (missing fields, all queries failing) are covered.

## Backlog

### P0
- (none open)

### P1
- Add a pagination-aware Text Search mode for the `cleaning` proxy category
  instead of the broad `service` type (README already flags this).
- Cache live Places responses per (center, radius, category) so re-runs do
  not re-bill identical queries. Blocked on a terms review: Google Maps
  Platform only allows caching `place_id` indefinitely and lat/lng for up to
  30 days; other fields must not be cached. Implement as a place_id/lat-lng
  cache only, or not at all.

### P2
- Add a `--max-attempts` CLI knob (retries are fixed at 3 attempts today).

## Done in this pass (pass 1)
- `GooglePlacesProvider`: bounded retry with backoff on 429/5xx/network
  errors, fail-fast on other 4xx, non-object JSON payloads rejected, API key
  excluded from `repr`.
- New offline tests for retry, fail-fast, key/body non-leakage and malformed
  payloads (7 -> 12 tests).
- ruff config in `pyproject.toml`, lint fix, GitHub Actions CI with dry-run
  smoke; README entry points/checks corrected.

## Done in this pass (pass 2)
- Removed `directories/yellow_pages_scraper.py` (imported the retired monorepo
  `adapters`/`core`, never ran standalone, would bulk-collect business phone
  numbers). Google Places / fixture providers are the working replacement;
  README and PRODUCT.md explain the removal and how to recover it from history.
- `tests/test_edge_cases.py`: `normalize_place` with missing location/id/name/
  types and malformed numbers, plus an all-errored collection feeding
  `analyze_categories` (12 -> 17 tests).

## Done in this pass (pass 3)
- Reports written atomically (`location_intelligence/atomic_io.py`: temp file
  + fsync + `os.replace`); both outputs are rendered before either is written.
- Billable-attempt accounting: `GooglePlacesProvider.last_attempts`,
  per-query `query_results[].attempts`, `collection.attempt_count` in JSON and
  Markdown, `http_attempts` in the CLI summary (was P2).
- CLI validation: `--lat`/`--lng` ranges and pairing, non-negative
  `--budget-thb`, `--hours-per-week` 0-168.
- `tests/test_pass3_hardening.py` (17 -> 28 tests incl. parametrised).
- `models._float` treats NaN/inf as missing: NaN coordinates produced
  records with NaN lat/lng (invalid JSON) and a NaN `closing_hour` counted
  as evidence of no convenience gap (`tests/test_edge_cases.py`, 2 tests).
- Number edge cases: `models._int` let `int(inf)` raise `OverflowError`
  (aborting normalization) and kept negative review counts (the demand
  score's `math.sqrt` then raised); both are now missing. CLI float options
  (`--lat/--lng/--analysis-radius/--budget-thb/--hours-per-week/--radii`) use
  `_finite_float`: "nan" passed every range check. Regression tests in
  `tests/test_edge_cases.py` and `tests/test_pass3_hardening.py`.
