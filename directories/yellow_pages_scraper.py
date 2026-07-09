#!/usr/bin/env python3
"""
Thai Yellow Pages scraper — uses httpx+BS4 engine.
Scrapes business listings from yellowpages.co.th.

MCP Tool: search_businesses
Data: name, category, address, phone, website, URL
"""

import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from adapters.outbound.engines.httpx_bs4 import HttpxBS4Scraper
from core.models import BusinessListing

logger = logging.getLogger(__name__)

CATEGORIES = [
    "restaurants",
    "clinics",
    "real-estate",
    "accounting",
    "law-firms",
    "construction",
]

BASE_URL = "https://www.yellowpages.co.th/search"


class YellowPagesScraper(HttpxBS4Scraper):
    """Scrape business listings from Thai Yellow Pages."""

    def __init__(self):
        super().__init__(
            name="thai_yellow_pages",
            rate_limit=3.0,
            max_retries=3,
            timeout=30.0,
        )

    def build_search_url(self, category: str, page: int = 1) -> str:
        return f"{BASE_URL}?k={category}&p={page}"

    def parse_listing(self, card) -> Optional[BusinessListing]:
        """Parse a single business listing."""
        try:
            name_el = card.select_one("h2.business-name a") or card.select_one("h2 a")
            name = name_el.get_text(strip=True) if name_el else ""

            addr_el = card.select_one("span.address") or card.select_one(".listing-address")
            address = addr_el.get_text(strip=True) if addr_el else ""

            phone_el = card.select_one("span.phone") or card.select_one(".listing-phone")
            phone = phone_el.get_text(strip=True) if phone_el else ""

            website_el = card.select_one("a.website-link") or card.select_one("a[href*='http']")
            website = website_el.get("href", "") if website_el else ""

            link = ""
            if name_el and name_el.get("href"):
                href = name_el["href"]
                link = f"https://www.yellowpages.co.th{href}" if href.startswith("/") else href

            if not name:
                return None

            return BusinessListing(
                name=name,
                address=address,
                phone=phone,
                website=website,
                url=link,
                source="yellow_pages",
            )
        except Exception as e:
            logger.error(f"Error parsing listing: {e}")
            return None

    async def scrape_category(self, category: str, max_pages: int = 3):
        """Scrape all pages for a business category."""
        logger.info(f"Scraping Yellow Pages: {category}")

        for page in range(1, max_pages + 1):
            url = self.build_search_url(category, page)
            soup = await self.fetch_and_parse(url)
            if not soup:
                break

            cards = soup.select("div.listing-card") or soup.select("article.business-listing")
            if not cards:
                logger.info(f"  No more results on page {page}")
                break

            for card in cards:
                listing = self.parse_listing(card)
                if listing:
                    listing.category = category
                    self.add_result(listing.__dict__)

            logger.info(f"  Page {page}: {len(cards)} listings found")

    async def run(self, categories: List[str] = None, max_pages: int = 3):
        """Run scraper for all categories."""
        categories = categories or CATEGORIES

        for cat in categories:
            await self.scrape_category(cat, max_pages)

        self.print_stats()
        self.export_csv("yellow_pages_businesses.csv")
        self.export_json("yellow_pages_businesses.json")
        return self.results


async def main():
    scraper = YellowPagesScraper()
    results = await scraper.run()
    print(f"\nTotal businesses scraped: {len(results)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
