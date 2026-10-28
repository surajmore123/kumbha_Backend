from datetime import date, time, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.models import FCMDevice, NotificationPreference, User
from apps.crowd.models import AppNotification, Incident, Zone
from apps.events.models.EventModel import Event
from apps.events.models.event_subscription import EventSubscription
from apps.events.models.schedule_notification import ScheduledNotification
from apps.events.reminders import dispatch_due_reminders
from utils import push_notifications

PREFS_URL = "/api/auth/notification-preferences/"


def _sent_ok(tokens, title, body, **kwargs):
    return {"status": "sent", "success": len(tokens), "failure": 0, "deactivated": 0}


class PreferenceApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number="9000000401")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_defaults_are_all_on(self):
        response = self.client.get(PREFS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"],
            {category: True for category in NotificationPreference.CATEGORIES},
        )

    def test_toggle_one_category(self):
        response = self.client.patch(PREFS_URL, {"crowd_alerts": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["crowd_alerts"])
        self.assertTrue(response.json()["data"]["event_reminders"])
        self.assertFalse(NotificationPreference.objects.get(user=self.user).crowd_alerts)

    def test_unknown_category_and_bad_value_are_rejected(self):
        self.assertEqual(self.client.patch(PREFS_URL, {"marketing": False}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(PREFS_URL, {"crowd_alerts": "maybe"}, format="json").status_code, 400)

    def test_requires_login(self):
        self.assertEqual(APIClient().get(PREFS_URL).status_code, 401)


class OptOutTests(TestCase):
    def setUp(self):
        self.on = User.objects.create_user(phone_number="9000000501", preferred_language="hi")
        self.off = User.objects.create_user(phone_number="9000000502")
        FCMDevice.objects.create(user=self.on, token="on-token", device_type="ANDROID")
        FCMDevice.objects.create(user=self.off, token="off-token", device_type="ANDROID")
        NotificationPreference.objects.create(user=self.off, crowd_alerts=False)

    def test_broadcast_skips_users_who_opted_out(self):
        with mock.patch.object(push_notifications, "send_to_tokens", side_effect=_sent_ok) as send:
            push_notifications.send_push_to_all("T", "B", category="crowd_alerts")
        self.assertEqual(send.call_args.args[0], ["on-token"])

    def test_localized_broadcast_uses_each_users_language(self):
        texts = {"en": ("Alert", "English"), "hi": ("सूचना", "हिंदी")}
        with mock.patch.object(push_notifications, "send_to_tokens", side_effect=_sent_ok) as send:
            push_notifications.send_localized("safety_alerts", lambda code: texts[code])
        sent = {call.args[1]: call.args[0] for call in send.call_args_list}
        self.assertEqual(sent, {"सूचना": ["on-token"], "Alert": ["off-token"]})

    def test_single_user_opt_out(self):
        result = push_notifications.send_to_user(self.off, "T", "B", category="crowd_alerts")
        self.assertEqual(result["status"], "opted_out")


def _event(**extra):
    values = dict(
        event_name="Amrit Snan",
        event_category="SNAN",
        event_subtype="AMRIT_SNAN",
        event_date=date.today() + timedelta(days=10),
        start_time=time(6, 0),
        location_type="NASHIK",
        location_name="Ramkund",
        data_source="GOVT",
        is_verified=True,
        status="PUBLISHED",
    )
    values.update(extra)
    return Event.objects.create(**values)


class EventChangeNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number="9000000601")
        FCMDevice.objects.create(user=self.user, token="tok", device_type="ANDROID")
        patcher = mock.patch("apps.events.notifications.send_localized", return_value={"status": "sent"})
        self.send = patcher.start()
        self.addCleanup(patcher.stop)

    def _kinds(self):
        return [call.kwargs["data"]["type"] for call in self.send.call_args_list]

    def test_publishing_announces_a_new_event_once(self):
        with self.captureOnCommitCallbacks(execute=True):
            event = _event(status="DRAFT")
        self.send.assert_not_called()
        with self.captureOnCommitCallbacks(execute=True):
            event.status = "PUBLISHED"
            event.save()
        self.assertEqual(self._kinds(), ["new_event"])
        self.assertEqual(self.send.call_args.args[0], "new_events")
        with self.captureOnCommitCallbacks(execute=True):
            event.short_description = "edited text"
            event.save()
        self.assertEqual(self._kinds(), ["new_event"])  # no repeat for other edits

    def test_time_change_notifies_subscribers_and_moves_reminders(self):
        with self.captureOnCommitCallbacks(execute=True):
            event = _event()
        subscription = EventSubscription.objects.create(user=self.user, event=event, reminder_offsets=[60])
        ScheduledNotification.objects.create(
            subscription=subscription,
            scheduled_at=timezone.now() + timedelta(days=9),
            offset_minutes=60,
        )
        self.send.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            event.start_time = time(8, 30)
            event.save()

        self.assertEqual(self._kinds(), ["event_update"])
        self.assertEqual(self.send.call_args.args[0], "event_updates")
        self.assertEqual(list(self.send.call_args.kwargs["users"]), [{"user_id": self.user.pk}])
        title, body = self.send.call_args.args[1]("en")
        self.assertEqual(title, "Event updated: Amrit Snan")
        self.assertIn("8:30 AM", body)
        reminder = ScheduledNotification.objects.get(subscription=subscription, is_sent=False)
        self.assertEqual(
            timezone.localtime(reminder.scheduled_at).time(), time(7, 30),
        )

    def test_withdrawing_cancels_reminders_and_tells_subscribers(self):
        with self.captureOnCommitCallbacks(execute=True):
            event = _event()
        subscription = EventSubscription.objects.create(user=self.user, event=event)
        pending = ScheduledNotification.objects.create(
            subscription=subscription, scheduled_at=timezone.now() + timedelta(days=5), offset_minutes=1440,
        )
        self.send.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            event.status = "ARCHIVED"
            event.save()
        self.assertEqual(self._kinds(), ["event_update"])
        title, _ = self.send.call_args.args[1]("mr")
        self.assertEqual(title, "कार्यक्रम काढला: Amrit Snan")
        pending.refresh_from_db()
        self.assertEqual(pending.del_flag, 1)

    def test_past_events_send_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            _event(event_date=date.today() - timedelta(days=3))
        self.send.assert_not_called()

    def test_push_failure_never_breaks_saving(self):
        self.send.side_effect = RuntimeError("fcm down")
        with self.captureOnCommitCallbacks(execute=True):
            _event()
        self.assertTrue(Event.objects.exists())


class ReminderOptOutTests(TestCase):
    def test_reminders_respect_the_setting(self):
        user = User.objects.create_user(phone_number="9000000701")
        NotificationPreference.objects.create(user=user, event_reminders=False)
        with mock.patch("apps.events.notifications.send_localized"):
            event = _event(event_date=date.today() + timedelta(days=1))
        subscription = EventSubscription.objects.create(user=user, event=event)
        reminder = ScheduledNotification.objects.create(
            subscription=subscription, scheduled_at=timezone.now() - timedelta(minutes=1), offset_minutes=1440,
        )
        with mock.patch.object(push_notifications, "send_to_tokens") as send:
            summary = dispatch_due_reminders()
        send.assert_not_called()
        self.assertEqual(summary["skipped"], 1)
        reminder.refresh_from_db()
        self.assertEqual(reminder.del_flag, 1)


class SafetyAlertTests(TestCase):
    def setUp(self):
        self.zone = Zone.objects.create(
            code="RAMKUND_01", name="Ramkund", city="Nashik",
            latitude=Decimal("19.997500"), longitude=Decimal("73.791000"), capacity=1000,
        )
        patcher = mock.patch("apps.crowd.notifications.send_localized", return_value={"status": "sent"})
        self.send = patcher.start()
        self.addCleanup(patcher.stop)

    def _incident(self, severity="HIGH", **extra):
        return Incident.objects.create(
            zone=self.zone, incident_type="CROWD", severity=severity, title="Gate 3 closed",
            description="Use gate 5.", start_time=timezone.now(), **extra,
        )

    def test_serious_incident_is_pushed_and_added_to_feed(self):
        with self.captureOnCommitCallbacks(execute=True):
            self._incident()
        self.send.assert_called_once()
        self.assertEqual(self.send.call_args.args[0], "safety_alerts")
        self.assertEqual(self.send.call_args.kwargs["data"]["route"], "/notifications")
        self.assertEqual(self.send.call_args.args[1]("hi"), ("सुरक्षा सूचना: Ramkund", "Gate 3 closed"))
        feed = AppNotification.objects.get()
        self.assertEqual((feed.type, feed.severity), ("ALERT", "HIGH"))

    def test_minor_incident_is_not_pushed_until_raised(self):
        with self.captureOnCommitCallbacks(execute=True):
            incident = self._incident(severity="LOW")
        self.send.assert_not_called()
        with self.captureOnCommitCallbacks(execute=True):
            incident.severity = "CRITICAL"
            incident.save()
        self.send.assert_called_once()
        with self.captureOnCommitCallbacks(execute=True):
            incident.description = "Update: use gate 6."
            incident.save()
        self.send.assert_called_once()  # no repeat while it stays serious
