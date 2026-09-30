# book-directory-scraping

**Tier:** C / tool prototype (portfolio breadth, not interview flagship)  
**Owner path:** `bookchaowalit/book-apps/tools/book-directory-scraping`

## Purpose

Collect business/directory listings (e.g. Yellow Pages style sources) for local research.

## Automated location opportunity analysis

The `location_intelligence` module turns a center point into a bounded,
evidence-aware comparison of local business categories. It supports a local
synthetic/JSON fixture first, then an explicit Google Places API (New) mode.
The output is a JSON contract plus a Markdown report with query coverage,
expiry, evidence IDs, and a scorecard. Missing demand evidence stays explicit;
the score is a prioritization aid and is not a sales forecast.

Run the deterministic demo from this repository root:

```bash
python3 scripts/run_location_analysis.py \
  --input fixtures/bangkapi_sample.json \
  --radii 500,1000,3000 \
  --analysis-radius 1000 \
  --categories coffee,laundry,cleaning,beauty,pet
```

It writes `data/location-research/location-analysis.json` and
`data/location-research/location-analysis.md` (the directory is ignored by
Git). The default 25-request guard prevents an accidental unbounded run. Use
`--dry-run` to inspect the request plan without collecting rows.

To call Google Places (New), set `GOOGLE_MAPS_API_KEY` in the process
environment and opt in explicitly:

```bash
GOOGLE_MAPS_API_KEY='…' python3 scripts/run_location_analysis.py \
  --live --lat 13.7652 --lng 100.6431 \
  --radii 500,1000 --categories coffee,laundry \
  --max-requests 10
```

The client requests only the fields needed for the first scorecard and caps
each Nearby Search at 20 results. It never logs the key or raw provider error
body (the key is also hidden from the provider's `repr`). HTTP 429/5xx,
network errors and timeouts are retried at most twice more with 1 s / 2 s
backoff; other 4xx errors fail immediately. `--max-requests` bounds the query
plan, so the worst case is `3 x max-requests` billable calls. Review Google Maps attribution, caching, and service terms before using
the live output in a customer-facing product.

The `cleaning` candidate uses Google's broad `service` type because the current
type table has no dedicated cleaning-service filter. Treat that category as a
discovery proxy and add a keyword/Text Search or manual verification step before
using it for a decision.

Run the offline checks (no network; the Google client is mocked) with:

```bash
pip install pytest ruff
ruff check .
python -m pytest -q          # or: bash scripts/test_location_intelligence.sh
```

CI (`.github/workflows/ci.yml`) runs lint, tests and a `--dry-run` plan.

## Entry points

- `scripts/run_location_analysis.py` — location opportunity analysis (active, stdlib-only).

The former `directories/yellow_pages_scraper.py` prototype was removed in the
2026-09 upgrade pass: it imported the retired monorepo `adapters`/`core`
packages, never ran from a standalone checkout, used unverified selectors, and
would have bulk-collected business phone numbers. Business discovery is served
by the Google Places / fixture providers in `location_intelligence/`. Recover
it from Git history if a directory source is ever needed again, and add a
privacy note before porting.

## Stack

Python 3.10+ standard library (`pyproject.toml` has no runtime dependencies).

## Boundaries

- **Not** a lake-first data product. Durable market datasets live under `book-*-data` repos.
- **Not** coupled to Solo Empire monorepo runtime. Nested Git repo; commit only inside this tree.
- Never commit `.env`, cookies, session dumps, or scraped PII dumps to Git.

## Limitations (honest)

Not a production data product. No lake-first contract. Respect site ToS and robots rules; personal research use only.

## Related

- Active collection product: `book-job-scraping` (Tier A tool)
- Lake products: `book-crypto-data`, `book-fx-data`, `book-stock-data`, …
- Solo Empire catalog: `repository-catalog/BOOK-DEV-BACKLOG-BD.md` (BD-012)
