# book-directory-scraping — Product brief

**Slug:** `bookchaowalit/book-directory-scraping`  
**Generated:** 2026-08-11 (bulk Book Dev closeout)  
**Status:** starter / portfolio boundary

## Purpose

Portfolio repository under Book Dev. This brief records ownership and the
current honest status so the nested tree is not an empty shell in the task
system.

## Runnable path

See `README.md` for install and run instructions when present.

## Limits

- Not claimed as production-ready unless README and tests prove it.
- Mobile smoke / emulator acceptance is separate and toolchain-dependent.

## Source README excerpt

```
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
# Prefer reading the scraper module docstring/i
```
