from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from firebase_admin import messaging

from apps.authentication.models import FCMDevice, User
from apps.events.models.EventModel import Event
from apps.events.models.event_subscription import EventSubscription
from apps.events.models.schedule_notification import ScheduledNotification
from apps.events.reminders import dispatch_due_reminders, reminder_text
from utils import push_notifications


def _response(*outcomes):
    """Fake BatchResponse: True = delivered, an exception = failed."""
    items = [
        SimpleNamespace(success=o is True, exception=None if o is True else o)
        for o in outcomes
    ]
    return SimpleNamespace(
        responses=items,
        success_count=sum(i.success for i in items),
        failure_count=sum(not i.success for i in items),
    )


class PushSendingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number="9000000201")
        self.good = FCMDevice.objects.create(user=self.user, token="good", device_type="ANDROID")
        self.dead = FCMDevice.objects.create(user=self.user, token="dead", device_type="ANDROID")

    def test_message_has_notification_data_channel_and_icon(self):
        with mock.patch.object(messaging, "send_each_for_multicast", return_value=_response(True, True)) as send:
            push_notifications.send_to_user(
                self.user, "Title", "Body",
                data={"type": "event_reminder", "event_id": 42}, channel_id="event_reminders",
            )
        message = send.call_args.args[0]
        self.assertEqual(message.notification.title, "Title")
        self.assertEqual(message.data, {"type": "event_reminder", "event_id": "42"})
        self.assertEqual(message.android.priority, "high")
        self.assertEqual(message.android.notification.channel_id, "event_reminders")
        self.assertEqual(message.android.notification.icon, "ic_stat_notification")

    def test_dead_tokens_are_deactivated(self):
        unregistered = messaging.UnregisteredError("gone")
        with mock.patch.object(messaging, "send_each_for_multicast", return_value=_response(True, unregistered)):
            result = push_notifications.send_to_user(self.user, "T", "B")
        self.assertEqual(result["deactivated"], 1)
        self.dead.refresh_from_db()
        self.good.refresh_from_db()
        self.assertFalse(self.dead.is_active)
        self.assertTrue(self.good.is_active)

    def test_dry_run_never_deactivates(self):
        with mock.patch.object(
            messaging, "send_each_for_multicast",
            return_value=_response(True, messaging.UnregisteredError("gone")),
        ):
            push_notifications.send_to_user(self.user, "T", "B", dry_run=True)
        self.dead.refresh_from_db()
        self.assertTrue(self.dead.is_active)

    def test_tokens_are_sent_in_batches_of_500(self):
        tokens = [f"t{i}" for i in range(1201)]
        with mock.patch.object(
            messaging, "send_each_for_multicast",
            side_effect=lambda m, dry_run=False: _response(*([True] * len(m.tokens))),
        ) as send:
            result = push_notifications.send_to_tokens(tokens, "T", "B")
        self.assertEqual([len(c.args[0].tokens) for c in send.call_args_list], [500, 500, 201])
        self.assertEqual(result["success"], 1201)

    def test_missing_firebase_configuration_is_reported(self):
        with mock.patch.object(messaging, "send_each_for_multicast", side_effect=ValueError("no app")):
            result = push_notifications.send_to_user(self.user, "T", "B")
        self.assertEqual(result["status"], "disabled")

    def test_no_devices(self):
        other = User.objects.create_user(phone_number="9000000202")
        self.assertEqual(push_notifications.send_to_user(other, "T", "B")["status"], "no_devices")


class EventReminderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number="9000000301", preferred_language="mr")
        FCMDevice.objects.create(user=self.user, token="tok", device_type="ANDROID")
        self.event = Event.objects.create(
            event_name="Amrit Snan",
            event_category="SNAN",
            event_subtype="AMRIT_SNAN",
            event_date=date.today() + timedelta(days=2),
            start_time=time(6, 0),
            location_type="NASHIK",
            location_name="Ramkund",
            data_source="GOVT",
            is_verified=True,
            status="PUBLISHED",
        )
        self.subscription = EventSubscription.objects.create(
            user=self.user, event=self.event, reminder_offsets=[1440],
        )

    def _reminder(self, minutes_ago=1, offset=1440):
        return ScheduledNotification.objects.create(
            subscription=self.subscription,
            scheduled_at=timezone.now() - timedelta(minutes=minutes_ago),
            offset_minutes=offset,
        )

    def _send(self, result=None):
        return mock.patch(
            "apps.events.reminders.send_to_user",
            return_value=result or {"status": "sent", "success": 1, "failure": 0, "deactivated": 0},
        )

    def test_due_reminder_is_sent_once_in_users_language(self):
        reminder = self._reminder()
        with self._send() as send:
            first = dispatch_due_reminders()
            second = dispatch_due_reminders()
        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        send.assert_called_once()
        _, title, body = send.call_args.args
        self.assertEqual(title, "कार्यक्रम स्मरणपत्र")
        self.assertIn("Amrit Snan 1 दिवसात सुरू होईल.", body)
        self.assertEqual(send.call_args.kwargs["channel_id"], "event_reminders")
        self.assertEqual(send.call_args.kwargs["data"]["route"], "/shahiEvents")
        reminder.refresh_from_db()
        self.assertTrue(reminder.is_sent)

    def test_future_reminder_waits(self):
        self._reminder(minutes_ago=-30)
        with self._send() as send:
            dispatch_due_reminders()
        send.assert_not_called()

    def test_reminder_for_started_event_is_skipped_not_sent_late(self):
        self.event.event_date = date.today() - timedelta(days=1)
        self.event.save()
        reminder = self._reminder(minutes_ago=60 * 24 * 3)
        with self._send() as send:
            summary = dispatch_due_reminders()
        send.assert_not_called()
        self.assertEqual(summary["skipped"], 1)
        reminder.refresh_from_db()
        self.assertFalse(reminder.is_sent)
        self.assertEqual(reminder.del_flag, 1)

    def test_disabled_subscription_and_unpublished_event_are_skipped(self):
        self.subscription.is_active = False
        self.subscription.save()
        self._reminder()
        with self._send() as send:
            self.assertEqual(dispatch_due_reminders()["skipped"], 1)
        send.assert_not_called()

    def test_firebase_down_keeps_reminder_for_next_run(self):
        reminder = self._reminder()
        with self._send({"status": "disabled", "success": 0, "failure": 0, "deactivated": 0}):
            self.assertEqual(dispatch_due_reminders()["deferred"], 1)
        reminder.refresh_from_db()
        self.assertFalse(reminder.is_sent)

    def test_reminder_wording(self):
        self.assertEqual(
            reminder_text(self.event, 720, "en"),
            ("Event reminder", "Amrit Snan starts in 12 hours. Location: Ramkund"),
        )
        self.assertEqual(reminder_text(self.event, 5, "hi")[1], "Amrit Snan 5 मिनट में शुरू होगा। स्थान: Ramkund")
        self.assertEqual(reminder_text(self.event, 1440, "fr")[0], "Event reminder")

    def test_celery_task_uses_the_dispatcher(self):
        from apps.events.tasks import dispatch_event_reminders

        with mock.patch("apps.events.tasks.dispatch_due_reminders", return_value={"sent": 0}) as run:
            dispatch_event_reminders()
        run.assert_called_once()
