import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore

from services.scraper import GoldRate, IST

CURRENT_DOC = "gold_prices/current"
HISTORY_COL = "price_history"
STATS_DOC = "price_statistics/summary"
USERS_COL = "users"


def init_firestore():

    try:

        cred_json = os.environ.get(
            "FIREBASE_SERVICE_ACCOUNT"
        )

        if cred_json:
            cred = credentials.Certificate(
                json.loads(cred_json)
            )

        else:
            cred = credentials.Certificate(
                "firebase-credentials.json"
            )

        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)

        print("Firestore Connected")

        return firestore.client()

    except Exception as e:

        print(f"Firestore Error: {e}")

        raise


def get_current_price(db: firestore.Client) -> dict[str, Any] | None:
    snapshot = db.document(CURRENT_DOC).get()
    return snapshot.to_dict() if snapshot.exists else None


def persist_if_changed(db: firestore.Client, rate: GoldRate) -> tuple[dict[str, Any] | None, bool]:
    old_price = get_current_price(db)

    if (old_price and int(old_price.get("gold22kt", 0)) == rate.gold22kt and int(old_price.get("gold24kt", 0)) == rate.gold24kt):
        return old_price, False

    current_payload = {
        "gold22kt": rate.gold22kt,
        "gold24kt": rate.gold24kt,
        "lastUpdated": firestore.SERVER_TIMESTAMP,
        "source": rate.source,
        "location": rate.location,
        "sourceUpdatedAt": rate.source_updated_at,
    }
    history_payload = {
        "gold22kt": rate.gold22kt,
        "gold24kt": rate.gold24kt,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "source": rate.source,
        "location": rate.location,
    }

    batch = db.batch()
    batch.set(db.document(CURRENT_DOC), current_payload)
    batch.set(db.collection(HISTORY_COL).document(), history_payload)
    batch.commit()

    update_statistics(db)
    return old_price, True


def update_statistics(db: firestore.Client) -> None:
    docs = list(db.collection(HISTORY_COL).order_by("timestamp").stream())
    entries = [doc.to_dict() for doc in docs]
    prices = [int(entry["gold22kt"]) for entry in entries if entry.get("gold22kt") is not None]
    if not prices:
        return

    now = datetime.now(IST)

    def change_over(hours: int) -> int:
        cutoff = now - timedelta(hours=hours)

        window = []

        for entry in entries:
            ts = entry.get("timestamp")

            if ts and hasattr(ts, "replace"):
                if ts >= cutoff:
                    window.append(int(entry["gold22kt"]))

        return window[-1] - window[0] if len(window) >= 2 else 0

    stats = {
        "highestPrice": max(prices),
        "lowestPrice": min(prices),
        "averagePrice": round(sum(prices) / len(prices), 2),
        "dailyChange": change_over(24),
        "weeklyChange": change_over(24 * 7),
        "monthlyChange": change_over(24 * 30),
        "lastCalculated": now.isoformat(),
        "totalDataPoints": len(prices),
    }
    db.document(STATS_DOC).set(stats)