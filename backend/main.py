import logging

from services.firestore_service import init_firestore, persist_if_changed
from services.notification_service import (
    evaluate_user_alerts,
    send_price_change_notification,
)
from services.scraper import fetch_gold_rate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("goldpulse")


def main() -> None:
    db = init_firestore()
    try:
    rate = fetch_gold_rate()

except Exception as e:
    log.exception(
        "Gold scraping failed: %s",
        e
    )

    return
    log.info(
        "Fetched Kalyan Pune rate: 22KT=Rs %s 24KT=Rs %s",
        f"{rate.gold22kt:,}",
        f"{rate.gold24kt:,}",
    )

    old_price, changed = persist_if_changed(db, rate)
    if not changed:
        log.info("Price unchanged. Firestore write and FCM broadcast skipped.")
        return

    if old_price is not None:
        send_price_change_notification(old_price, rate)
    evaluate_user_alerts(db, rate)
    log.info("Firestore current/history updated successfully.")


if __name__ == "__main__":
    main()
