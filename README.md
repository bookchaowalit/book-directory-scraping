# book-directory-scraping

**Tier:** C / tool prototype (portfolio breadth, not interview flagship)  
**Owner path:** `bookchaowalit/book-apps/tools/book-directory-scraping`

## Purpose

Collect business/directory listings (e.g. Yellow Pages style sources) for local research.

## Entry points

- `directories/yellow_pages_scraper.py`

## Stack

Python scraper module(s)

## How to run (local)

```bash
# From this repository root
python3 -m venv .venv && source .venv/bin/activate
# Install whatever deps the script imports (often requests/httpx/bs4).
# Prefer reading the scraper module docstring/imports first — no lockfile yet.
python3 directories/yellow_pages_scraper.py
```

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
