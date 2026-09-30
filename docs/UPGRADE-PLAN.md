# Upgrade plan — book-directory-scraping

## Current state

Score: **7/10** (was 6/10) — the stdlib-only location-intelligence pipeline is
bounded, fixture-tested and now retries Google Places transient errors safely,
with lint and offline CI. The Yellow Pages module is dead legacy code.

## Backlog

### P0
- (none open)

### P1
- Delete or port `directories/yellow_pages_scraper.py` (imports missing
  monorepo `adapters`/`core`; business phone numbers would need a privacy note
  before any port).
- Add a pagination-aware Text Search mode for the `cleaning` proxy category
  instead of the broad `service` type (README already flags this).
- Cache live Places responses per (center, radius, category) for the allowed
  Google caching window so re-runs do not re-bill identical queries.

### P2
- Add fixture tests for `normalize_place` with missing `location`/`types` and
  for `analyze_categories` when every query errored (`status: partial`).
- Record retry counts in `query_results` for cost visibility.

## Done in this pass
- `GooglePlacesProvider`: bounded retry with backoff on 429/5xx/network
  errors, fail-fast on other 4xx, non-object JSON payloads rejected, API key
  excluded from `repr`.
- New offline tests for retry, fail-fast, key/body non-leakage and malformed
  payloads (7 -> 12 tests).
- ruff config in `pyproject.toml`, lint fix, GitHub Actions CI with dry-run
  smoke; README entry points/checks corrected.
