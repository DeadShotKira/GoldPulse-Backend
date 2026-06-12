import logging

from firebase_admin import firestore, messaging

from services.firestore_service import USERS_COL
from services.scraper import GoldRate

log = logging.getLogger("goldpulse.notifications")

FCM_TOPIC = "gold_updates"
ANDROID_CHANNEL_ID = "gold_price_updates"


def send_price_change_notification(old_price: dict, rate: GoldRate) -> None:
    old22 = int(old_price.get("gold22kt", 0))
    delta = rate.gold22kt - old22

    message = messaging.Message(
        notification=messaging.Notification(
            title="Gold Price Updated",
            body=f"22KT:\n₹{old22:,} → ₹{rate.gold22kt:,}",
        ),
        data={
            "type": "PRICE_UPDATE",
            "gold22kt": str(rate.gold22kt),
            "gold24kt": str(rate.gold24kt),
            "delta22kt": str(delta),
            "location": rate.location,
            "click_action": "CHART_SCREEN",
        },
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                icon="ic_notification",
                color="#FFD700",
                channel_id=ANDROID_CHANNEL_ID,
                click_action="OPEN_CHART",
            ),
        ),
        topic=FCM_TOPIC,
    )
    response = messaging.send(message)
    log.info("Price update notification sent: %s", response)


def evaluate_user_alerts(db: firestore.Client, rate: GoldRate) -> None:
    users_ref = db.collection(USERS_COL)
    for user_doc in users_ref.stream():
        alerts_ref = users_ref.document(user_doc.id).collection("alerts")
        for alert_doc in alerts_ref.where("active", "==", True).stream():
            alert = alert_doc.to_dict()
            alert_type = alert.get("type", "")
            threshold = int(alert.get("threshold", 0))
            token = alert.get("fcmToken")

            triggered = (
                (alert_type == "above" and rate.gold22kt >= threshold)
                or (alert_type == "below" and rate.gold22kt <= threshold)
            )
            if not triggered or not token:
                continue

            send_user_alert(token, alert_type, threshold, rate)
            if alert.get("oneTime", False):
                alert_doc.reference.update({"active": False})


def send_user_alert(token: str, alert_type: str, threshold: int, rate: GoldRate) -> None:
    direction = "above" if alert_type == "above" else "below"
    message = messaging.Message(
        notification=messaging.Notification(
            title="Gold Price Alert",
            body=f"22KT gold is {direction} ₹{threshold:,}. Current: ₹{rate.gold22kt:,}",
        ),
        data={
            "type": "PRICE_ALERT",
            "gold22kt": str(rate.gold22kt),
            "threshold": str(threshold),
            "alertType": alert_type,
        },
        token=token,
    )
    response = messaging.send(message)
    log.info("User alert sent: %s", response)
