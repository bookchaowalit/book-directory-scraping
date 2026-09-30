# Upgrade plan — book-directory-scraping

## Current state

Score: **7.5/10** (pass 1: 6 -> 7; pass 2: 7 -> 7.5) — the stdlib-only
location-intelligence pipeline is bounded, fixture-tested, retries Google
Places transient errors safely, and has lint + offline CI. No dead legacy code
remains; edge cases (missing fields, all queries failing) are covered.

## Backlog

### P0
- (none open)

### P1
- Add a pagination-aware Text Search mode for the `cleaning` proxy category
  instead of the broad `service` type (README already flags this).
- Cache live Places responses per (center, radius, category) for the allowed
  Google caching window so re-runs do not re-bill identical queries.

### P2
- Record retry counts in `query_results` for cost visibility.

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
