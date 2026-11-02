import logging
import uuid
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.models import FCMDevice, NotificationPreference, User
from apps.crowd.models.AppNotification import AppNotification
from apps.emergency import services
from apps.emergency.models import (
    EmergencyAudit,
    EmergencyRecipient,
    EmergencySOS,
    EmergencyStatusHistory,
    Status,
)
from apps.family.models import FamilyMember
from apps.notifications import services as inbox
from apps.notifications.models import Notification, NotificationDelivery
from apps.reunification.models import MeetingPoint
from apps.safety.models import SafetyHelper
from utils import push_notifications

FAMILY = "/api/family/"
EM = "/api/emergency/"
NOTE = "/api/notifications/"
PUSH = "apps.notifications.services.send_localized"
SENT = {"status": "sent", "success": 1, "failure": 0, "deactivated": 0}
NO_DEVICE = {"status": "no_devices", "success": 0, "failure": 0, "deactivated": 0}
DOWN = {"status": "disabled", "success": 0, "failure": 1, "deactivated": 0}


@override_settings(SAFETY_REQUIRE_HTTPS=False, EMERGENCY_LOCATION_RETENTION_DAYS=30)
class EmTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.organizer = self.user("41", "Suresh More")
        self.adult = self.user("42", "Asha More")
        self.relative = self.user("43", "Ravi More")
        self.outsider = self.user("44", "Stranger")
        self.client = APIClient()
        self.login(self.organizer)
        self.family = self.call("post", f"{FAMILY}circles/", {"name": "More Family"}, 201)
        self.fid = self.family["id"]
        self.join(self.adult)
        self.join(self.relative)
        self.staff = self.user("45", "Staff")
        SafetyHelper.objects.create(user=self.staff, role="safety_staff")
        self.desk = self.user("46", "Desk")
        SafetyHelper.objects.create(user=self.desk, role="help_desk")
        self.volunteer = self.user("47", "Volunteer")
        SafetyHelper.objects.create(user=self.volunteer, role="volunteer")

    def user(self, tail, name):
        return User.objects.create_user(phone_number=f"+9192200000{tail}", full_Name=name)

    def login(self, user):
        self.client.force_authenticate(user)

    def join(self, user):
        self.login(self.organizer)
        code = self.call("post", f"{FAMILY}circles/{self.fid}/invitations/", {"relationship": "sibling"}, 201)["code"]
        self.login(user)
        self.call("post", f"{FAMILY}invitations/accept/", {"code": code})

    def call(self, method, url, body=None, code=200, result=SENT):
        with mock.patch(PUSH, return_value=result), self.captureOnCommitCallbacks(execute=True):
            response = getattr(self.client, method)(url, body or {}, format="json")
        self.assertEqual(response.status_code, code, response.content)
        return response.json().get("data") if response.content else None

    def sos(self, user=None, code=201, result=SENT, **extra):
        self.login(user or self.adult)
        body = {"client_id": str(uuid.uuid4()), "category": "medical", **extra}
        return self.call("post", f"{EM}sos/", body, code, result)

    def ops(self, sos, action, user=None, body=None, code=200):
        self.login(user or self.staff)
        return self.call("post", f"{EM}ops/sos/{sos['id']}/{action}/", body, code)

    def row(self, data):
        return EmergencySOS.objects.get(pk=data["id"])


class SubmitTests(EmTestCase):
    def test_creates_a_reference_and_records_each_step(self):
        data = self.sos(details="Chest pain")
        self.assertTrue(data["reference"].startswith("SOS-"))
        steps = [h.to_status for h in self.row(data).history.all()]
        self.assertEqual(steps, ["CREATED", "SUBMITTED", "FAMILY_NOTIFIED"])

    def test_needs_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(f"{EM}sos/", {}, format="json").status_code, 401)

    def test_every_category_works(self):
        for value in EmergencySOS.Category.values:
            data = self.sos(category=value)
            self.login(self.adult)
            self.call("post", f"{EM}sos/{data['id']}/cancel/", {"reason": "Test run"})

    def test_an_unknown_category_is_refused(self):
        self.sos(category="nonsense", code=400)
        self.assertFalse(EmergencySOS.objects.exists())

    def test_no_gps_is_still_an_sos(self):
        data = self.sos()
        self.assertIsNone(data["latitude"])
        self.assertIn(data["status"], ("SUBMITTED", "FAMILY_NOTIFIED"))

    def test_a_description_can_stand_in_for_gps(self):
        self.assertEqual(self.sos(location_text="Near gate 3")["location_text"], "Near gate 3")

    def test_records_position_accuracy_and_time(self):
        at = timezone.now().isoformat()
        data = self.sos(latitude="19.997500", longitude="73.789800", accuracy_m=9, location_at=at)
        self.assertEqual(data["latitude"], 19.9975)
        self.assertEqual(data["accuracy_m"], 9)
        self.assertIsNotNone(data["location_at"])

    def test_half_a_position_is_refused(self):
        self.sos(latitude="19.99", code=400)

    def test_a_future_time_is_refused(self):
        self.sos(
            latitude="19.99", longitude="73.78", location_at=(timezone.now() + timedelta(hours=1)).isoformat(), code=400,
        )

    def test_a_user_id_in_the_body_is_ignored(self):
        data = self.sos(user_id=str(self.organizer.pk))
        self.assertEqual(self.row(data).user, self.adult)

    def test_a_retry_returns_the_same_sos(self):
        client_id = str(uuid.uuid4())
        first = self.sos(client_id=client_id)
        second = self.sos(client_id=client_id, code=200)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(EmergencySOS.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(category="emergency", user=self.organizer).count(), 1)

    def test_a_second_sos_points_to_the_open_one(self):
        first = self.sos()
        self.login(self.adult)
        response = self.client.post(
            f"{EM}sos/", {"client_id": str(uuid.uuid4()), "category": "other"}, format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["errors"]["active_id"], first["id"])

    def test_the_database_allows_only_one_active(self):
        data = self.sos()
        with self.assertRaises(IntegrityError), transaction.atomic():
            EmergencySOS.objects.create(
                user=self.row(data).user, client_id=uuid.uuid4(), category="other", status=Status.SUBMITTED,
            )

    def test_a_written_offline_time_is_kept(self):
        written = (timezone.now() - timedelta(minutes=20)).isoformat()
        self.assertIsNotNone(self.sos(written_at=written)["written_at"])

    def test_no_family_still_creates_it(self):
        data = self.sos(self.outsider)
        self.assertEqual(data["status"], "SUBMITTED")

    def test_is_rate_limited(self):
        self.login(self.adult)
        with mock.patch("apps.emergency.views.SosThrottle.rate", "2/hour"):
            codes = [self.client.post(f"{EM}sos/", {}, format="json").status_code for _ in range(4)]
        self.assertIn(429, codes)

    def test_never_claims_dispatch(self):
        self.login(self.adult)
        self.assertIs(self.call("get", f"{EM}me/")["dispatch_integration"], False)

    def test_me_lists_who_would_be_told(self):
        self.login(self.adult)
        data = self.call("get", f"{EM}me/")
        self.assertEqual(data["family"], ["Ravi More", "Suresh More"])
        self.assertEqual(data["emergency_numbers"][0]["number"], "112")
        self.assertIsNone(data["active"])


class FamilyNotificationTests(EmTestCase):
    def test_tells_family_and_staff_but_not_the_sender_or_strangers(self):
        self.sos()
        users = set(Notification.objects.filter(category="emergency").values_list("user_id", flat=True))
        self.assertEqual(users, {self.organizer.pk, self.relative.pk, self.staff.pk})

    def test_ignores_muted_preferences(self):
        NotificationPreference.objects.create(user=self.organizer, safety_alerts=False)
        with mock.patch(PUSH, return_value=SENT) as push, self.captureOnCommitCallbacks(execute=True):
            self.login(self.adult)
            self.client.post(f"{EM}sos/", {"client_id": str(uuid.uuid4()), "category": "lost"}, format="json")
        self.assertTrue(all(call.args[0] is None for call in push.call_args_list))
        self.assertEqual(NotificationDelivery.objects.filter(state="sent").count(), 3)

    def test_the_lock_screen_text_holds_nothing_private(self):
        data = self.sos(location_text="Near gate 3", details="Chest pain")
        for row in NotificationDelivery.objects.all():
            text = row.push_title + row.push_body
            for private in ("Asha", "Medical", "gate 3", "Chest"):
                self.assertNotIn(private, text)
            self.assertIn(data["reference"], text)

    def test_the_centre_has_the_details_behind_the_login(self):
        self.sos()
        row = Notification.objects.get(user=self.organizer)
        self.assertIn("Asha More", row.title)
        self.assertIn("Medical emergency", row.body)

    def test_the_payload_holds_ids_only(self):
        self.sos(latitude="19.997500", longitude="73.789800", location_at=timezone.now().isoformat())
        data = str(Notification.objects.get(user=self.organizer).data)
        self.assertNotIn("19.99", data)

    def test_uses_the_recipients_language(self):
        User.objects.filter(pk=self.organizer.pk).update(preferred_language="hi")
        self.sos()
        self.assertIn("SOS भेजा", Notification.objects.get(user=self.organizer).title)

    def test_no_devices_doesnt_count_as_notified(self):
        data = self.sos(result=NO_DEVICE)
        self.assertEqual(self.row(data).status, "SUBMITTED")

    def test_a_failed_send_is_retried_and_then_counts(self):
        data = self.sos(result=DOWN)
        self.assertEqual(self.row(data).status, "SUBMITTED")
        self.assertEqual(NotificationDelivery.objects.filter(state="pending").count(), 3)
        NotificationDelivery.objects.update(next_attempt_at=timezone.now())
        with mock.patch(PUSH, return_value=SENT):
            services.sweep()
        self.assertEqual(self.row(data).status, "FAMILY_NOTIFIED")

    def test_a_crash_while_sending_stays_pending(self):
        with mock.patch(PUSH, side_effect=RuntimeError("down")), self.captureOnCommitCallbacks(execute=True):
            self.login(self.adult)
            response = self.client.post(
                f"{EM}sos/", {"client_id": str(uuid.uuid4()), "category": "lost"}, format="json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(NotificationDelivery.objects.filter(state="pending").count(), 3)

    def test_it_gives_up_eventually_and_says_so(self):
        self.sos(result=DOWN)
        row = NotificationDelivery.objects.first()
        NotificationDelivery.objects.filter(pk=row.pk).update(attempts=NotificationDelivery.MAX_ATTEMPTS - 1)
        row.refresh_from_db()
        with mock.patch(PUSH, return_value=DOWN):
            inbox._attempt(row)
        row.refresh_from_db()
        self.assertEqual(row.state, "failed")

    def test_a_row_left_behind_by_a_crash_gets_picked_up(self):
        self.sos(result=DOWN)
        NotificationDelivery.objects.update(
            next_attempt_at=None, created_at=timezone.now() - timedelta(minutes=5),
        )
        with mock.patch(PUSH, return_value=SENT):
            self.assertEqual(inbox.retry_pending(), 3)

    def test_acknowledgement_reaches_family_and_owner(self):
        data = self.sos()
        self.ops(data, "acknowledge")
        users = set(
            Notification.objects.filter(data__sos_id=data["id"], title__icontains="acknowledged")
            .values_list("user_id", flat=True)
        )
        self.assertEqual(users, {self.organizer.pk, self.relative.pk, self.adult.pk})

    def test_cancelling_tells_the_family(self):
        data = self.sos()
        self.call("post", f"{EM}sos/{data['id']}/cancel/", {"reason": "I am safe now"})
        self.assertTrue(Notification.objects.filter(user=self.organizer, title__icontains="cancelled").exists())

    def test_a_repeated_event_isnt_sent_twice(self):
        data = self.sos()
        sos = self.row(data)
        before = Notification.objects.count()
        services._tell(sos, "submitted", [self.organizer.pk])
        self.assertEqual(Notification.objects.count(), before)

    def test_no_position_in_logs(self):
        with self.assertLogs("apps.notifications", logging.WARNING) as logs:
            with mock.patch(PUSH, side_effect=RuntimeError("19.9975")), self.captureOnCommitCallbacks(execute=True):
                self.login(self.adult)
                self.client.post(f"{EM}sos/", {
                    "client_id": str(uuid.uuid4()), "category": "lost", "latitude": "19.9975", "longitude": "73.7898",
                }, format="json")
        self.assertNotIn("19.99", "\n".join(logs.output))


class AccessTests(EmTestCase):
    def test_family_sees_it_with_the_position(self):
        data = self.sos(latitude="19.997500", longitude="73.789800")
        self.login(self.organizer)
        seen = self.call("get", f"{EM}sos/{data['id']}/")
        self.assertEqual(seen["latitude"], 19.9975)
        self.assertEqual(seen["role"], "family")

    def test_strangers_get_404(self):
        data = self.sos()
        self.login(self.outsider)
        self.call("get", f"{EM}sos/{data['id']}/", code=404)
        self.call("post", f"{EM}sos/{data['id']}/contact/", code=404)

    def test_a_volunteer_gets_404(self):
        data = self.sos()
        self.login(self.volunteer)
        self.call("get", f"{EM}sos/{data['id']}/", code=404)

    def test_an_unassigned_help_desk_gets_404(self):
        data = self.sos()
        self.login(self.desk)
        self.call("get", f"{EM}sos/{data['id']}/", code=404)

    def test_someone_who_leaves_the_family_loses_access(self):
        data = self.sos()
        self.login(self.relative)
        self.call("post", f"{FAMILY}circles/{self.fid}/leave/", code=204)
        self.call("get", f"{EM}sos/{data['id']}/", code=404)

    def test_family_lose_the_position_when_it_ends(self):
        data = self.sos(latitude="19.997500", longitude="73.789800", location_text="Gate 3")
        self.call("post", f"{EM}sos/{data['id']}/cancel/", {"reason": "I am safe now"})
        self.login(self.organizer)
        seen = self.call("get", f"{EM}sos/{data['id']}/")
        self.assertIsNone(seen["latitude"])
        self.assertEqual(seen["location_text"], "")

    def test_family_dont_see_why_it_was_cancelled(self):
        data = self.sos()
        self.call("post", f"{EM}sos/{data['id']}/cancel/", {"reason": "Private reason"})
        self.login(self.organizer)
        seen = self.call("get", f"{EM}sos/{data['id']}/")
        self.assertEqual(seen["cancel_reason"], "")
        self.assertNotIn("Private reason", str(seen))

    def test_internal_notes_stay_internal(self):
        data = self.sos()
        self.ops(data, "update", body={"body": "Internal detail", "internal": True})
        for user in (self.organizer, self.adult):
            self.login(user)
            self.assertNotIn("Internal detail", str(self.call("get", f"{EM}sos/{data['id']}/")))

    def test_family_cant_change_the_owners_sos(self):
        data = self.sos()
        self.login(self.organizer)
        self.call("post", f"{EM}sos/{data['id']}/cancel/", {"reason": "Not mine"}, 403)
        self.call("post", f"{EM}sos/{data['id']}/info/", {"body": "x"}, 403)
        self.call("post", f"{EM}sos/{data['id']}/location/", {"location_text": "x"}, 403)

    def test_contact_is_audited_and_ends_with_the_emergency(self):
        data = self.sos()
        self.login(self.organizer)
        self.assertEqual(self.call("post", f"{EM}sos/{data['id']}/contact/")["phone"], self.adult.phone_number)
        self.assertTrue(EmergencyAudit.objects.filter(action="contact_used", actor=self.organizer).exists())
        self.login(self.adult)
        self.call("post", f"{EM}sos/{data['id']}/cancel/", {"reason": "I am safe now"})
        self.login(self.organizer)
        self.call("post", f"{EM}sos/{data['id']}/contact/", code=403)

    def test_the_audit_holds_no_private_values(self):
        data = self.sos(latitude="19.997500", longitude="73.789800")
        self.login(self.organizer)
        self.call("post", f"{EM}sos/{data['id']}/contact/")
        text = str(list(EmergencyAudit.objects.values_list("details", flat=True)))
        self.assertNotIn("19.99", text)
        self.assertNotIn(self.adult.phone_number, text)

    def test_responses_arent_cached(self):
        data = self.sos()
        response = self.client.get(f"{EM}sos/{data['id']}/")
        self.assertIn("no-store", response["Cache-Control"])

    def test_history_lists_only_your_own(self):
        self.sos()
        self.login(self.outsider)
        self.assertEqual(self.call("get", f"{EM}sos/")["results"], [])
        self.assertEqual(self.call("get", f"{EM}sos/?scope=family")["results"], [])
        self.login(self.organizer)
        self.assertEqual(len(self.call("get", f"{EM}sos/?scope=family")["results"]), 1)

    @override_settings(SAFETY_REQUIRE_HTTPS=True)
    def test_plain_http_is_refused_when_required(self):
        self.login(self.adult)
        self.assertEqual(self.client.post(f"{EM}sos/", {}, format="json").status_code, 400)


class LifecycleTests(EmTestCase):
    def status(self, data):
        return self.row(data).status

    def test_a_family_acknowledgement_is_never_a_responders(self):
        data = self.sos()
        self.login(self.organizer)
        seen = self.call("post", f"{EM}sos/{data['id']}/acknowledge-family/")
        self.assertTrue(seen["i_acknowledged"])
        self.assertEqual(seen["status"], "FAMILY_NOTIFIED")
        self.assertIsNone(seen["responder_acknowledged_at"])
        self.login(self.adult)
        family = self.call("get", f"{EM}sos/{data['id']}/")["family"]
        self.assertEqual(len([f for f in family if f["acknowledged_at"]]), 1)

    def test_only_operators_reach_operational_statuses(self):
        data = self.sos()
        for user in (self.adult, self.organizer, self.relative, self.outsider, self.volunteer, self.desk):
            for action in ("acknowledge", "coordinate", "resolve", "close", "update"):
                expected = 404 if user == self.desk else 403
                self.ops(data, action, user, {"body": "Trying"}, expected)
        self.assertEqual(self.status(data), "FAMILY_NOTIFIED")

    def test_pilgrims_cant_list_operations(self):
        self.sos()
        self.login(self.adult)
        self.call("get", f"{EM}ops/sos/", code=403)

    def test_the_full_path_records_everything(self):
        data = self.sos()
        self.ops(data, "acknowledge")
        self.ops(data, "coordinate", body={"body": "Help desk informed"})
        self.ops(data, "resolve", body={"body": "With family at the desk"})
        self.ops(data, "close")
        rows = list(EmergencyStatusHistory.objects.filter(sos_id=data["id"]))
        self.assertEqual([r.to_status for r in rows], [
            "CREATED", "SUBMITTED", "FAMILY_NOTIFIED", "ACKNOWLEDGED", "ASSISTANCE_COORDINATED", "RESOLVED", "CLOSED",
        ])
        self.assertEqual(rows[3].from_status, "FAMILY_NOTIFIED")
        self.assertEqual(rows[3].actor, self.staff)
        self.assertEqual(rows[3].actor_role, "responder")
        self.assertEqual(rows[5].reason, "With family at the desk")
        self.assertIsNone(rows[2].actor)

    def test_steps_cant_be_skipped(self):
        data = self.sos()
        self.ops(data, "coordinate", body={"body": "Too soon"}, code=409)
        self.ops(data, "resolve", body={"body": "Too soon"}, code=409)
        self.ops(data, "close", code=409)

    def test_resolving_needs_a_note(self):
        data = self.sos()
        self.ops(data, "acknowledge")
        self.ops(data, "resolve", code=400)

    def test_nothing_resolves_by_itself(self):
        data = self.sos()
        EmergencySOS.objects.filter(pk=data["id"]).update(created_at=timezone.now() - timedelta(days=30))
        with mock.patch(PUSH, return_value=SENT):
            services.sweep()
        self.assertEqual(self.status(data), "FAMILY_NOTIFIED")

    def test_cancelling_needs_a_reason(self):
        data = self.sos()
        self.call("post", f"{EM}sos/{data['id']}/cancel/", {}, 400)
        self.assertEqual(self.status(data), "FAMILY_NOTIFIED")

    def test_cancelling_keeps_the_record_and_the_reason(self):
        data = self.sos()
        seen = self.call("post", f"{EM}sos/{data['id']}/cancel/", {"reason": "Pressed by mistake"})
        self.assertEqual(seen["status"], "CANCELLED")
        self.assertEqual(seen["cancel_reason"], "Pressed by mistake")
        row = EmergencyStatusHistory.objects.get(sos_id=data["id"], to_status="CANCELLED")
        self.assertEqual((row.actor, row.actor_role, row.reason), (self.adult, "person", "Pressed by mistake"))

    def test_a_cancelled_sos_cant_be_cancelled_again(self):
        data = self.sos()
        self.call("post", f"{EM}sos/{data['id']}/cancel/", {"reason": "Mistake"})
        self.call("post", f"{EM}sos/{data['id']}/cancel/", {"reason": "Again"}, 409)

    def test_a_new_sos_can_follow_a_cancelled_one(self):
        data = self.sos()
        self.call("post", f"{EM}sos/{data['id']}/cancel/", {"reason": "Mistake"})
        self.sos()

    def test_the_person_can_add_details_and_a_new_position(self):
        data = self.sos()
        self.call("post", f"{EM}sos/{data['id']}/info/", {"body": "Near the red tent"})
        seen = self.call("post", f"{EM}sos/{data['id']}/location/", {
            "latitude": "19.900000", "longitude": "73.700000", "accuracy_m": 20,
            "location_at": timezone.now().isoformat(),
        })
        self.assertEqual(seen["latitude"], 19.9)
        self.assertEqual(seen["status"], "FAMILY_NOTIFIED")
        self.assertEqual([u["kind"] for u in seen["updates"]], ["person", "location"])

    def test_a_location_update_needs_something(self):
        data = self.sos()
        self.call("post", f"{EM}sos/{data['id']}/location/", {}, 400)

    def test_nothing_can_change_after_it_ends(self):
        data = self.sos()
        self.call("post", f"{EM}sos/{data['id']}/cancel/", {"reason": "Mistake"})
        self.call("post", f"{EM}sos/{data['id']}/info/", {"body": "x"}, 409)
        self.call("post", f"{EM}sos/{data['id']}/location/", {"location_text": "x"}, 409)

    def test_an_assigned_help_desk_can_work_it(self):
        data = self.sos()
        self.ops(data, "assign", body={"assignee_id": str(self.desk.pk)})
        self.ops(data, "acknowledge", self.desk)
        self.login(self.desk)
        self.assertEqual(len(self.call("get", f"{EM}ops/sos/")["results"]), 1)

    def test_only_staff_can_assign(self):
        data = self.sos()
        self.ops(data, "assign", body={"assignee_id": str(self.desk.pk)})
        self.ops(data, "assign", self.desk, {"assignee_id": str(self.desk.pk)}, 403)

    def test_a_pilgrim_cant_be_assigned(self):
        data = self.sos()
        self.ops(data, "assign", body={"assignee_id": str(self.adult.pk)}, code=409)

    def test_an_expired_helper_loses_access(self):
        data = self.sos()
        SafetyHelper.objects.filter(user=self.staff).update(expires_at=timezone.now() - timedelta(days=1))
        self.ops(data, "acknowledge", code=403)

    def test_operations_can_filter(self):
        self.sos()
        self.login(self.staff)
        self.assertEqual(len(self.call("get", f"{EM}ops/sos/?category=medical")["results"]), 1)
        self.assertEqual(self.call("get", f"{EM}ops/sos/?category=crowd")["results"], [])

    def test_operators_viewing_is_audited(self):
        data = self.sos()
        self.login(self.staff)
        self.call("get", f"{EM}ops/sos/{data['id']}/")
        self.assertTrue(EmergencyAudit.objects.filter(action="viewed", actor=self.staff).exists())

    def test_old_positions_are_removed_after_it_ends(self):
        data = self.sos(latitude="19.997500", longitude="73.789800")
        self.call("post", f"{EM}sos/{data['id']}/cancel/", {"reason": "Mistake"})
        EmergencySOS.objects.filter(pk=data["id"]).update(updated_at=timezone.now() - timedelta(days=31))
        with mock.patch(PUSH, return_value=SENT):
            services.sweep()
        self.assertIsNone(self.row(data).latitude)

    def test_active_positions_are_kept(self):
        data = self.sos(latitude="19.997500", longitude="73.789800")
        EmergencySOS.objects.filter(pk=data["id"]).update(updated_at=timezone.now() - timedelta(days=31))
        with mock.patch(PUSH, return_value=SENT):
            services.sweep()
        self.assertIsNotNone(self.row(data).latitude)

    def test_recipients_are_a_snapshot_of_the_family(self):
        data = self.sos()
        self.assertEqual(EmergencyRecipient.objects.filter(sos_id=data["id"]).count(), 2)
        self.assertFalse(FamilyMember.objects.filter(user=self.adult, emergency_alerts__isnull=False).exists())


class CentreTests(EmTestCase):
    def setUp(self):
        super().setUp()
        self.data = self.sos()
        self.login(self.organizer)

    def test_lists_your_own(self):
        rows = self.call("get", NOTE)["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category"], "emergency")
        self.assertFalse(rows[0]["read"])
        self.assertEqual(rows[0]["delivery"], "sent")

    def test_needs_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(NOTE).status_code, 401)

    def test_someone_elses_is_404(self):
        row = Notification.objects.get(user=self.organizer)
        self.login(self.outsider)
        self.call("post", f"{NOTE}{row.pk}/read/", code=404)
        row.refresh_from_db()
        self.assertIsNone(row.read_at)

    def test_read_and_unread_counts(self):
        row = Notification.objects.get(user=self.organizer)
        self.assertEqual(self.call("get", f"{NOTE}summary/")["unread"], 1)
        self.call("post", f"{NOTE}{row.pk}/read/")
        self.assertEqual(self.call("get", f"{NOTE}summary/")["unread"], 0)
        self.assertEqual(self.call("get", f"{NOTE}?unread=true")["results"], [])

    def test_mark_all_read(self):
        self.call("post", f"{NOTE}read-all/")
        self.assertEqual(self.call("get", f"{NOTE}summary/")["unread"], 0)

    def test_mark_all_leaves_other_peoples(self):
        self.call("post", f"{NOTE}read-all/")
        self.assertTrue(Notification.objects.filter(user=self.relative, read_at__isnull=True).exists())

    def test_filters_by_category(self):
        self.assertEqual(self.call("get", f"{NOTE}?category=lost_found")["results"], [])
        self.call("get", f"{NOTE}?category=nonsense", code=400)

    def test_fetching_counts_as_reaching_the_app_not_as_read(self):
        self.call("get", NOTE)
        row = Notification.objects.get(user=self.organizer)
        self.assertIsNotNone(row.delivered_at)
        self.assertIsNone(row.read_at)
        self.login(self.adult)
        family = self.call("get", f"{EM}sos/{self.data['id']}/")["family"]
        reached = [f for f in family if f["name"] == "Suresh More"][0]
        self.assertIsNotNone(reached["reached_app_at"])
        self.assertIsNone(reached["acknowledged_at"])

    def test_general_updates_are_included_and_read_as_a_group(self):
        AppNotification.objects.create(title="Gate closed", body="Use gate 2", type="ALERT")
        self.assertEqual(self.call("get", f"{NOTE}summary/")["by_category"]["general"], 1)
        rows = self.call("get", f"{NOTE}?category=general")["results"]
        self.assertEqual(rows[0]["title"], "Gate closed")
        self.call("post", f"{NOTE}read-all/", {"category": "general"})
        self.assertEqual(self.call("get", f"{NOTE}summary/")["by_category"]["general"], 0)
        self.assertEqual(self.call("get", f"{NOTE}summary/")["by_category"]["emergency"], 1)

    def test_pages(self):
        with mock.patch("apps.notifications.views.PAGE_SIZE", 1):
            for i in range(2):
                Notification.objects.create(user=self.organizer, category="general", title="t", body="b", dedupe_key=str(i))
            self.assertTrue(self.call("get", NOTE)["has_next"])


class MirrorTests(EmTestCase):
    def build(self, language):
        return {"en": ("Title", "Body"), "hi": ("शीर्षक", "विवरण"), "mr": ("शीर्षक", "तपशील")}[language]

    def test_records_in_each_language(self):
        User.objects.filter(pk=self.relative.pk).update(preferred_language="mr")
        inbox.mirror([self.organizer.pk, self.relative.pk], "lost_found", self.build, {"route": "/x"})
        self.assertEqual(Notification.objects.get(user=self.relative).body, "तपशील")

    def test_a_retried_message_isnt_recorded_twice(self):
        for _ in range(2):
            inbox.mirror([self.organizer.pk], "lost_found", self.build, {}, "case:1")
        self.assertEqual(Notification.objects.count(), 1)

    def test_send_localized_records_it_even_when_muted(self):
        NotificationPreference.objects.create(user=self.organizer, safety_alerts=False)
        FCMDevice.objects.create(user=self.organizer, token="t", device_type="ANDROID")
        with mock.patch("utils.push_notifications.send_to_tokens") as sender:
            push_notifications.send_localized(
                "safety_alerts", self.build, users=[self.organizer.pk], data={"route": "/x"},
                inbox={"category": "lost_found", "key": "e1"},
            )
        sender.assert_not_called()
        self.assertEqual(Notification.objects.filter(user=self.organizer).count(), 1)

    def test_a_centre_failure_never_stops_a_send(self):
        with mock.patch("apps.notifications.services.mirror", side_effect=RuntimeError("x")):
            result = push_notifications.send_localized(
                None, self.build, users=[self.organizer.pk], inbox={"category": "lost_found"},
            )
        self.assertEqual(result["status"], "no_devices")


class PreferenceTests(EmTestCase):
    def test_the_new_categories_can_be_changed(self):
        self.login(self.adult)
        data = self.call("patch", "/api/auth/notification-preferences/", {"family_location": False, "reunification": False})
        self.assertFalse(data["family_location"])
        self.assertTrue(data["crowd_alerts"])

    def test_emergency_alerts_have_no_switch(self):
        self.login(self.adult)
        self.call("patch", "/api/auth/notification-preferences/", {"emergency": False}, 400)


class AssistanceTests(EmTestCase):
    def point(self, name, category, status="verified", **extra):
        return MeetingPoint.objects.create(
            name=name, category=category, status=status, latitude="19.99", longitude="73.78",
            source_detail="Visited" if status == "verified" else "", **extra,
        )

    def test_there_is_no_seed_data(self):
        self.assertEqual(MeetingPoint.objects.count(), 0)

    def test_ambulance_and_fire_points_can_be_listed(self):
        self.point("Ambulance base", "ambulance", address="Main road", contact_phone="108")
        self.point("Fire post", "fire_rescue")
        self.login(self.adult)
        rows = self.call("get", "/api/reunification/points/?verified=true")["results"]
        self.assertEqual({r["category"] for r in rows}, {"ambulance", "fire_rescue"})
        self.assertEqual(rows[0]["address"], "Main road")
