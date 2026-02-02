from firebase_admin import messaging
from apps.authentication.models import FCMDevice

def send_test_push(user, title, body):
    devices = FCMDevice.objects.filter(
        user=user,
        is_active=True
    )

    tokens = [d.token for d in devices]

    if not tokens:
        return {"status": "no_devices"}

    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        tokens=tokens,
    )

    response = messaging.send_multicast(message)

    return {
        "success": response.success_count,
        "failure": response.failure_count,
    }