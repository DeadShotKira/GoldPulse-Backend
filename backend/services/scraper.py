import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from playwright.async_api import async_playwright

log = logging.getLogger("goldpulse.scraper")

KALYAN_PAGE_URL = "https://www.kalyanjewellers.net/gold-rate/Gold-Rate-Today"

COUNTRY_ID = "1"      # India
STATE_ID = "11"       # Maharashtra
CITY_ID = "88"        # Pune

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class GoldRate:
    gold22kt: int
    gold24kt: int
    source: str
    location: str
    fetched_at: str


def parse_price(text: str) -> int:
    matches = re.findall(r"\b\d{4,6}\b", text.replace(",", ""))

    for value in matches:
        price = int(value)

        if 5000 <= price <= 200000:
            return price

    raise ValueError("No valid gold price found")


def build_rate(price_22kt: int) -> GoldRate:
    return GoldRate(
        gold22kt=price_22kt,
        gold24kt=round(price_22kt * 24 / 22),
        source="Kalyan Jewellers",
        location="Pune, Maharashtra, India",
        fetched_at=datetime.now(IST).isoformat(),
    )


async def fetch_gold_rate_async() -> GoldRate:

    log.info("Launching browser...")

    async with async_playwright() as pw:

        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        try:

            page = await browser.new_page()

            log.info("Opening Kalyan rate page")

            await page.goto(
                KALYAN_PAGE_URL,
                wait_until="networkidle",
                timeout=60000
            )

            log.info("Selecting India")

            await page.select_option(
                "#countryId",
                value=COUNTRY_ID
            )

            await page.wait_for_timeout(1000)

            log.info("Selecting Maharashtra")

            await page.select_option(
                "#stateId",
                value=STATE_ID
            )

            await page.wait_for_timeout(1000)

            log.info("Selecting Pune")

            await page.select_option(
                "#cityId",
                value=CITY_ID
            )

            await page.wait_for_timeout(3000)

            body_text = await page.inner_text("body")

            log.info("Extracting gold price")

            price_22kt = parse_price(body_text)

            log.info(
                "Gold price found: ₹%s",
                f"{price_22kt:,}"
            )

            return build_rate(price_22kt)

        finally:

            log.info("Closing browser")

            await browser.close()


def fetch_gold_rate() -> GoldRate:
    import asyncio
    return asyncio.run(fetch_gold_rate_async())
