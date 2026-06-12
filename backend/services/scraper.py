import asyncio
import logging
import re
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
    """Fetch Pune Kalyan rate using the hidden API, with Playwright as fallback."""
    try:
        return fetch_gold_rate_from_api()
    except Exception as exc:
        log.warning("Kalyan API fetch failed, falling back to Playwright: %s", exc)
        return asyncio.run(fetch_gold_rate_with_playwright())


def fetch_gold_rate_from_api() -> GoldRate:
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
    response = requests.post(
        KALYAN_RATE_API_URL,
        data=payload,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    price_22kt = parse_price(data.get("today_22k") or data.get("html", ""))
    return build_rate(
        price_22kt,
        source_updated_at=extract_updated_time(data),
    )


async def fetch_gold_rate_with_playwright() -> GoldRate:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        try:
            await page.goto(KALYAN_PAGE_URL, wait_until="networkidle", timeout=60_000)
            await page.select_option("#countryId", value=COUNTRY_ID)
            await page.wait_for_timeout(750)
            await page.select_option("#stateId", value=STATE_ID)
            await page.wait_for_timeout(750)
            await page.select_option("#cityId", value=CITY_ID)
            await page.wait_for_timeout(2_000)
            body_text = await page.inner_text("body")
            return build_rate(parse_price(body_text))
        finally:
            await browser.close()


def parse_price(value: Any) -> int:
    text = str(value)
    match = re.search(r"(?:INR|Rs\.?|₹)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", text, re.I)
    if not match:
        raise ValueError(f"Could not parse gold price from: {text[:120]}")

    price = int(round(float(match.group(1).replace(",", ""))))
    if not 5_000 <= price <= 200_000:
        raise ValueError(f"Parsed price outside expected range: {price}")
    return price


def build_rate(price_22kt: int, source_updated_at: str | None = None) -> GoldRate:
    return GoldRate(
        gold22kt=price_22kt,
        gold24kt=round(price_22kt * 24 / 22),
        source=f"Kalyan Jewellers ({CITY.title()})",
        location=f"{CITY}, {STATE}, {COUNTRY}",
        fetched_at=datetime.now(IST).isoformat(),
        source_updated_at=source_updated_at,
    )


def extract_updated_time(data: dict[str, Any]) -> str | None:
    disclaimer = data.get("disclaimer") or ""
    match = re.search(r"Refreshed on\s*([^.<]+)", disclaimer)
    if match:
        return match.group(1).strip()
    updated_time = data.get("updated_time")
    if updated_time and updated_time != "01 Jan 1970 00:00":
        return str(updated_time)
    return None
