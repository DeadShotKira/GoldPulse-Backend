import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

log = logging.getLogger("goldpulse.scraper")

KALYAN_PAGE_URL = "https://www.kalyanjewellers.net/gold-rate/Gold-Rate-Today"
KALYAN_RATE_API_URL = "https://www.kalyanjewellers.net/kalyan_gold_rates/ajax/get_rate"

COUNTRY_ID = "1"
STATE_ID = "11"
CITY_ID = "88"

COUNTRY = "INDIA"
STATE = "MAHARASHTRA"
CITY = "PUNE"

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class GoldRate:
    gold22kt: int
    gold24kt: int
    source: str
    location: str
    fetched_at: str
    source_updated_at: str | None = None


def fetch_gold_rate() -> GoldRate:
    log.info("=" * 60)
    log.info("Starting gold price fetch process")
    log.info("Location: %s, %s, %s", CITY, STATE, COUNTRY)

    try:
        log.info("Trying hidden Kalyan API...")
        start = time.time()

        result = fetch_gold_rate_from_api()

        log.info(
            "API fetch successful in %.2f seconds",
            time.time() - start,
        )

        return result

    except Exception as exc:
        log.exception("API fetch failed")

        log.warning(
            "Falling back to Playwright scraping..."
        )

        start = time.time()

        result = asyncio.run(
            fetch_gold_rate_with_playwright()
        )

        log.info(
            "Playwright fetch successful in %.2f seconds",
            time.time() - start,
        )

        return result


def fetch_gold_rate_from_api() -> GoldRate:

    log.info("Preparing API request payload")

    payload = {
        "countryId": COUNTRY_ID,
        "stateId": STATE_ID,
        "cityId": CITY_ID,
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Referer": KALYAN_PAGE_URL,
        "X-Requested-With": "XMLHttpRequest",
    }

    log.info(
        "Sending POST request to: %s",
        KALYAN_RATE_API_URL,
    )

    response = requests.post(
        KALYAN_RATE_API_URL,
        data=payload,
        headers=headers,
        timeout=10,
    )

    log.info(
        "Response status code: %s",
        response.status_code,
    )

    response.raise_for_status()

    data = response.json()

    log.info(
        "Response received successfully"
    )

    log.debug(
        "API response keys: %s",
        list(data.keys())
    )

    raw_value = data.get("today_22k") or data.get("html", "")

    log.info(
        "Extracting 22KT price from API response"
    )

    price_22kt = parse_price(raw_value)

    log.info(
        "Parsed 22KT price: ₹%s",
        f"{price_22kt:,}"
    )

    updated_time = extract_updated_time(data)

    log.info(
        "Source updated time: %s",
        updated_time
    )

    return build_rate(
        price_22kt,
        source_updated_at=updated_time,
    )


async def fetch_gold_rate_with_playwright() -> GoldRate:

    log.info("Initializing Playwright")

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:

        log.info("Launching Chromium browser")

        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={
                "width": 1280,
                "height": 800,
            },
        )

        page = await context.new_page()

        try:

            log.info(
                "Opening Kalyan page..."
            )

            await page.goto(
                KALYAN_PAGE_URL,
                wait_until="domcontentloaded",
                timeout=20_000,
            )

            log.info(
                "Selecting Country=%s",
                COUNTRY_ID,
            )

            await page.select_option(
                "#countryId",
                value=COUNTRY_ID,
            )

            await page.wait_for_timeout(750)

            log.info(
                "Selecting State=%s",
                STATE_ID,
            )

            await page.select_option(
                "#stateId",
                value=STATE_ID,
            )

            await page.wait_for_timeout(750)

            log.info(
                "Selecting City=%s",
                CITY_ID,
            )

            await page.select_option(
                "#cityId",
                value=CITY_ID,
            )

            await page.wait_for_timeout(2000)

            log.info(
                "Reading page content..."
            )

            body_text = await page.inner_text(
                "body"
            )

            log.info(
                "Parsing gold price from webpage"
            )

            price = parse_price(body_text)

            log.info(
                "Parsed Playwright price: ₹%s",
                f"{price:,}"
            )

            return build_rate(price)

        finally:

            log.info(
                "Closing browser"
            )

            await browser.close()


def parse_price(value: Any) -> int:

    text = str(value)

    log.debug(
        "Attempting price extraction"
    )

    match = re.search(
        r"(?:INR|Rs\.?|₹)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        text,
        re.I,
    )

    if not match:

        log.error(
            "Price parsing failed"
        )

        raise ValueError(
            f"Could not parse gold price from: {text[:120]}"
        )

    price = int(
        round(
            float(
                match.group(1).replace(",", "")
            )
        )
    )

    log.info(
        "Extracted numeric price: %s",
        price,
    )

    if not 5_000 <= price <= 200_000:

        log.error(
            "Price outside expected range: %s",
            price,
        )

        raise ValueError(
            f"Parsed price outside expected range: {price}"
        )

    return price


def build_rate(
    price_22kt: int,
    source_updated_at: str | None = None,
) -> GoldRate:

    price_24kt = round(
        price_22kt * 24 / 22
    )

    log.info(
        "Building GoldRate object"
    )

    log.info(
        "22KT = ₹%s | 24KT = ₹%s",
        f"{price_22kt:,}",
        f"{price_24kt:,}",
    )

    return GoldRate(
        gold22kt=price_22kt,
        gold24kt=price_24kt,
        source=f"Kalyan Jewellers ({CITY.title()})",
        location=f"{CITY}, {STATE}, {COUNTRY}",
        fetched_at=datetime.now(IST).isoformat(),
        source_updated_at=source_updated_at,
    )


def extract_updated_time(
    data: dict[str, Any]
) -> str | None:

    log.debug(
        "Extracting source update time"
    )

    disclaimer = data.get(
        "disclaimer"
    ) or ""

    match = re.search(
        r"Refreshed on\s*([^.<]+)",
        disclaimer,
    )

    if match:

        value = match.group(1).strip()

        log.info(
            "Found update time in disclaimer: %s",
            value,
        )

        return value

    updated_time = data.get(
        "updated_time"
    )

    if (
        updated_time
        and updated_time != "01 Jan 1970 00:00"
    ):

        log.info(
            "Found update time in response: %s",
            updated_time,
        )

        return str(updated_time)

    log.info(
        "No source update time found"
    )

    return None
