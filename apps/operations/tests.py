import logging
from datetime import timedelta
from unittest import mock

from django.contrib.admin.sites import site
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import Otp, User
from apps.crowd.models.Zone import Zone
from apps.emergency.models import EmergencySOS
from apps.lostfound.models import CaseAudit, LostFoundCase
from apps.lostfound.services import create_case
from apps.notifications.models import Notification
from apps.operations import services
from apps.operations.models import CaseAssignment, OperationsAudit
from apps.reunification.models import MeetingPoint
from apps.safety.models import SafetyHelper, SafetyScanLog
from apps.safety.zones import zone_for

OPS = "/api/operations/"
EM = "/api/emergency/"
LF = "/api/lostfound/"
PUSH = "apps.notifications.services.send_localized"
LF_PUSH = "apps.lostfound.notifications.send_localized"
SENT = {"status": "sent", "success": 1, "failure": 0, "deactivated": 0}
PASSWORD = "Ramkund-Ghat-2027!"


def zone(code, lat="19.9975", radius=1000):
    return Zone.objects.create(
        code=code, name=f"Zone {code}", city="Nashik", latitude=lat, longitude="73.7898", radius_m=radius,
    )


@override_settings(
    SAFETY_REQUIRE_HTTPS=False, OPERATIONS_SETUP_CODE_HOURS=48, OPERATIONS_DEFAULT_ZONE_RADIUS_M=1500,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class OpsTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.zone_a = zone("A")
        self.zone_b = zone("B", lat="20.1000")
        self.admin_user = User.objects.create_superuser("admin@test.in", "+919330000001", "Admin-Pass-2027!")
        self.pilgrim = self.user("02", "Pilgrim")
        self.volunteer = self.helper("03", "Volunteer A", "volunteer", [self.zone_a])
        self.other = self.helper("04", "Volunteer B", "volunteer", [self.zone_b])
        self.desk = self.helper("05", "Desk A", "help_desk", [self.zone_a])
        self.coordinator = self.helper("06", "Coord A", "safety_staff", [self.zone_a])
        self.coordinator_b = self.helper("07", "Coord B", "safety_staff", [self.zone_b])

    def user(self, tail, name):
        return User.objects.create_user(phone_number=f"+9193300000{tail}", full_Name=name)

    def helper(self, tail, name, role, zones):
        user = self.user(tail, name)
        helper = SafetyHelper.objects.create(user=user, role=role)
        helper.zones.set(zones)
        return user

    def login(self, user):
        self.client.force_authenticate(user)

    def call(self, method, url, body=None, code=200):
        with mock.patch(PUSH, return_value=SENT), mock.patch(LF_PUSH, return_value=SENT), \
                self.captureOnCommitCallbacks(execute=True):
            response = getattr(self.client, method)(url, body or {}, format="json")
        self.assertEqual(response.status_code, code, response.content)
        return response.json().get("data") if response.content else None

    def case(self, the_zone=None, vulnerabilities=None, lat="19.9975"):
        with mock.patch(LF_PUSH, return_value=SENT):
            return LostFoundCase.objects.create(
                case_type="lost", reporter=self.pilgrim, event_at=timezone.now(), location_text="Near Ramkund",
                latitude=lat, longitude="73.7898", clothing_description="Green saree", zone=the_zone or self.zone_a,
                vulnerabilities=vulnerabilities or [],
            )

    def assign(self, case=None, volunteer=None, by=None, code=201):
        case = case or self.case()
        self.login(by or self.coordinator)
        self.call("post", f"{OPS}cases/{case.pk}/assign/", {"volunteer_id": str((volunteer or self.volunteer).pk)}, code)
        return case


class AccountTests(OpsTestCase):
    def create(self, phone="+919330000050"):
        return services.create_volunteer(
            phone_number=phone, full_name="New Volunteer", role="volunteer", zones=[self.zone_a], by=self.admin_user,
        )

    def test_a_new_volunteer_starts_pending_with_no_admin_rights(self):
        helper, code = self.create()
        self.assertEqual(helper.status, "pending")
        self.assertFalse(helper.is_current)
        self.assertFalse(helper.user.is_staff)
        self.assertFalse(helper.user.is_superuser)
        self.assertFalse(helper.user.has_usable_password())
        self.assertEqual(len(code), 10)

    def test_the_code_isnt_stored_in_the_clear(self):
        helper, code = self.create()
        self.assertNotIn(code, helper.setup_code_hash)
        self.assertNotIn(code, str(list(OperationsAudit.objects.values_list("details", flat=True))))

    def test_codes_differ(self):
        self.assertNotEqual(services.new_setup_code(), services.new_setup_code())

    def test_an_existing_pilgrim_keeps_their_account(self):
        helper, _ = self.create(self.pilgrim.phone_number)
        self.assertEqual(helper.user, self.pilgrim)

    def test_an_admin_cant_be_made_a_volunteer(self):
        with self.assertRaises(services.OperationsError):
            self.create(self.admin_user.phone_number)

    def test_the_account_creation_is_audited(self):
        helper, _ = self.create()
        self.assertTrue(OperationsAudit.objects.filter(target=helper.user, action="volunteer_created").exists())

    def setup_call(self, phone, code, password=PASSWORD, expected=200):
        self.client.force_authenticate(None)
        return self.call("post", f"{OPS}auth/setup/", {
            "phone_number": phone, "code": code, "password": password,
        }, expected)

    def test_setup_then_password_login(self):
        helper, code = self.create()
        data = self.setup_call("9330000050", code)
        self.assertTrue(data["access_token"])
        again = self.call("post", f"{OPS}auth/login/", {"phone_number": "9330000050", "password": PASSWORD})
        self.assertTrue(again["access_token"])
        helper.refresh_from_db()
        self.assertEqual(helper.setup_code_hash, "")

    def test_the_code_works_once(self):
        _, code = self.create()
        self.setup_call("9330000050", code)
        self.setup_call("9330000050", code, expected=401)

    def test_an_expired_code_is_refused(self):
        helper, code = self.create()
        SafetyHelper.objects.filter(pk=helper.pk).update(setup_expires_at=timezone.now() - timedelta(minutes=1))
        self.setup_call("9330000050", code, expected=401)

    def test_a_weak_password_is_refused(self):
        _, code = self.create()
        self.setup_call("9330000050", code, password="123", expected=400)

    def test_wrong_details_all_look_the_same(self):
        _, code = self.create()
        self.client.force_authenticate(None)
        wrong = self.client.post(f"{OPS}auth/login/", {"phone_number": "9330000050", "password": "x"}, format="json")
        missing = self.client.post(f"{OPS}auth/login/", {"phone_number": "9330000099", "password": "x"}, format="json")
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.content, missing.content)

    def test_repeated_failures_lock_the_account(self):
        helper, code = self.create()
        self.setup_call("9330000050", code)
        for _ in range(5):
            self.client.post(f"{OPS}auth/login/", {"phone_number": "9330000050", "password": "bad"}, format="json")
        locked = self.client.post(f"{OPS}auth/login/", {"phone_number": "9330000050", "password": PASSWORD}, format="json")
        self.assertEqual(locked.status_code, 429)

    def test_a_pilgrim_cant_use_staff_sign_in(self):
        self.client.force_authenticate(None)
        self.call("post", f"{OPS}auth/login/", {"phone_number": self.pilgrim.phone_number, "password": "x"}, code=401)

    def test_an_admin_signs_in_with_their_existing_password(self):
        self.client.force_authenticate(None)
        data = self.call("post", f"{OPS}auth/login/", {
            "phone_number": self.admin_user.phone_number, "password": "Admin-Pass-2027!",
        })
        self.assertTrue(data["access_token"])

    def test_an_admin_with_the_wrong_password_is_refused(self):
        self.client.force_authenticate(None)
        self.call("post", f"{OPS}auth/login/", {
            "phone_number": self.admin_user.phone_number, "password": "wrong",
        }, code=401)

    def test_a_suspended_account_cant_sign_in(self):
        helper, code = self.create()
        self.setup_call("9330000050", code)
        services.set_status(helper, "suspended", self.admin_user)
        self.call("post", f"{OPS}auth/login/", {"phone_number": "9330000050", "password": PASSWORD}, code=401)

    def otp(self, user):
        Otp.objects.create(user=user, otp_code="111111", expiry_time=timezone.now() + timedelta(minutes=5))
        self.client.force_authenticate(None)
        return self.client.post("/api/auth/verify-mobile-otp/", {
            "phone_number": user.phone_number, "otp_code": "111111",
        }, format="json")

    def test_otp_is_refused_for_operational_accounts(self):
        for user in (self.volunteer, self.coordinator, self.admin_user):
            self.assertEqual(self.otp(user).status_code, 400)

    def test_a_pilgrim_still_signs_in_by_otp(self):
        response = self.otp(self.pilgrim)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["access_token"])

    def test_a_deactivated_volunteer_is_an_ordinary_pilgrim_again(self):
        helper = SafetyHelper.objects.get(user=self.volunteer)
        services.set_status(helper, "deactivated", self.admin_user)
        self.assertEqual(self.otp(self.volunteer).status_code, 200)
        self.login(self.volunteer)
        self.call("get", f"{OPS}cases/", code=403)

    def bearer(self, user):
        client = APIClient()
        token = str(RefreshToken.for_user(user).access_token)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client

    def test_ending_a_session_stops_an_old_token(self):
        client = self.bearer(self.volunteer)
        self.assertEqual(client.get(f"{OPS}me/").status_code, 200)
        User.objects.filter(pk=self.volunteer.pk).update(tokens_valid_after=timezone.now() + timedelta(seconds=5))
        self.assertEqual(client.get(f"{OPS}me/").status_code, 401)

    def test_a_token_issued_afterwards_works(self):
        User.objects.filter(pk=self.volunteer.pk).update(tokens_valid_after=timezone.now() - timedelta(seconds=5))
        self.assertEqual(self.bearer(self.volunteer).get(f"{OPS}me/").status_code, 200)

    def test_pilgrim_tokens_are_unaffected(self):
        self.assertEqual(self.bearer(self.pilgrim).get(f"{OPS}me/").status_code, 200)

    def test_deactivating_ends_access_on_the_next_request(self):
        client = self.bearer(self.volunteer)
        services.set_status(SafetyHelper.objects.get(user=self.volunteer), "deactivated", self.admin_user)
        # 401 once the token is cut off, and 403 from the live role check within
        # the same second. Either way, nothing comes back.
        self.assertIn(client.get(f"{OPS}cases/").status_code, (401, 403))

    def test_deactivating_returns_open_work(self):
        case = self.assign()
        with mock.patch(PUSH, return_value=SENT):
            services.set_status(SafetyHelper.objects.get(user=self.volunteer), "suspended", self.admin_user)
        case.refresh_from_db()
        self.assertIsNone(case.assigned_to)
        self.assertEqual(CaseAssignment.objects.get().status, "REASSIGNED")

    def test_status_changes_are_audited(self):
        services.set_status(SafetyHelper.objects.get(user=self.volunteer), "suspended", self.admin_user)
        row = OperationsAudit.objects.get(action="status_changed")
        self.assertEqual(row.details, {"previous": "active", "status": "suspended"})

    def test_a_reset_ends_the_old_password(self):
        helper, code = self.create()
        self.setup_call("9330000050", code)
        services.issue_setup_code(helper, self.admin_user)
        self.call("post", f"{OPS}auth/login/", {"phone_number": "9330000050", "password": PASSWORD}, code=401)

    def test_no_secrets_in_logs(self):
        _, code = self.create()
        with self.assertNoLogs("apps.operations", logging.INFO):
            self.setup_call("9330000050", code)


class RoleTests(OpsTestCase):
    def me(self, user):
        self.login(user)
        return self.call("get", f"{OPS}me/")

    def test_roles_come_from_the_account(self):
        self.assertEqual(self.me(self.pilgrim)["role"], "PILGRIM")
        self.assertEqual(self.me(self.volunteer)["role"], "VOLUNTEER")
        self.assertEqual(self.me(self.desk)["role"], "HELP_DESK_OPERATOR")
        self.assertEqual(self.me(self.coordinator)["role"], "SAFETY_COORDINATOR")
        self.assertEqual(self.me(self.admin_user)["role"], "ADMIN")

    def test_a_role_in_the_request_changes_nothing(self):
        self.login(self.pilgrim)
        self.assertEqual(self.client.get(f"{OPS}me/?role=ADMIN", HTTP_X_ROLE="ADMIN").json()["data"]["role"], "PILGRIM")

    def test_each_role_can_do_only_its_own_things(self):
        self.assertFalse(self.me(self.volunteer)["can"]["assign_cases"])
        self.assertFalse(self.me(self.volunteer)["can"]["view_sos"])
        self.assertTrue(self.me(self.desk)["can"]["view_sos"])
        self.assertFalse(self.me(self.desk)["can"]["assign_cases"])
        self.assertTrue(self.me(self.coordinator)["can"]["assign_cases"])

    def test_a_pending_volunteer_can_do_nothing(self):
        helper, _ = services.create_volunteer(
            phone_number="+919330000051", full_name="P", role="volunteer", zones=[], by=self.admin_user,
        )
        data = self.me(helper.user)
        self.assertEqual(data["status"], "pending")
        self.assertFalse(any(data["can"].values()))
        self.call("get", f"{OPS}cases/", code=403)

    def test_pilgrims_get_nothing_operational(self):
        self.login(self.pilgrim)
        for url in ("cases/", "overview/", "zones/", "team/", "escalations/"):
            self.call("get", f"{OPS}{url}", code=403)
        self.call("patch", f"{OPS}me/availability/", {"availability": "BUSY"}, 403)
        case = self.case()
        self.call("post", f"{OPS}cases/{case.pk}/assign/", {"volunteer_id": str(self.pilgrim.pk)}, 403)
        self.call("get", f"{OPS}cases/{case.pk}/", code=404)

    def test_needs_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"{OPS}me/").status_code, 401)

    def test_a_volunteer_cant_use_django_admin(self):
        self.client.force_login(self.volunteer)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_a_superuser_can_use_django_admin(self):
        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_an_expired_helper_loses_access(self):
        SafetyHelper.objects.filter(user=self.volunteer).update(expires_at=timezone.now() - timedelta(days=1))
        self.login(self.volunteer)
        self.call("get", f"{OPS}cases/", code=403)

    def test_the_existing_helper_check_still_works(self):
        self.login(self.volunteer)
        self.assertTrue(self.call("get", "/api/safety/helper/me/")["is_helper"])


class AvailabilityTests(OpsTestCase):
    def test_setting_it(self):
        self.login(self.volunteer)
        self.assertEqual(self.call("patch", f"{OPS}me/availability/", {"availability": "BUSY"})["availability"], "BUSY")
        self.call("patch", f"{OPS}me/availability/", {"availability": "ADMIN"}, 400)

    def test_it_grants_nothing(self):
        self.login(self.volunteer)
        self.call("patch", f"{OPS}me/availability/", {"availability": "AVAILABLE"})
        self.call("get", f"{OPS}team/", code=403)

    def test_off_duty_cant_take_cases(self):
        SafetyHelper.objects.filter(user=self.volunteer).update(availability="OFF_DUTY")
        self.assign(code=409)

    def test_the_team_view_shows_workload_in_the_coordinators_zones(self):
        self.assign()
        self.login(self.coordinator)
        rows = {r["name"]: r for r in self.call("get", f"{OPS}team/")}
        self.assertEqual(rows["Volunteer A"]["open_cases"], 1)
        self.assertNotIn("Volunteer B", rows)

    def test_only_coordinators_see_the_team(self):
        self.login(self.desk)
        self.call("get", f"{OPS}team/", code=403)


class AssignmentTests(OpsTestCase):
    def test_assigning_records_everything(self):
        case = self.assign()
        row = CaseAssignment.objects.get()
        self.assertEqual((row.case, row.volunteer, row.assigned_by, row.status),
                         (case, self.volunteer, self.coordinator, "ASSIGNED"))
        case.refresh_from_db()
        self.assertEqual(case.assigned_to, self.volunteer)
        self.assertTrue(CaseAudit.objects.filter(case=case, action="case_assigned").exists())

    def test_the_volunteer_is_told_without_details(self):
        case = self.assign()
        row = Notification.objects.get(user=self.volunteer)
        self.assertEqual(row.category, "operations")
        self.assertNotIn("Green", row.body)
        self.assertEqual(row.data["case_id"], str(case.pk))

    def test_reassigning_keeps_history(self):
        other_a = self.helper("08", "Volunteer C", "volunteer", [self.zone_a])
        case = self.assign()
        self.assign(case, other_a)
        self.login(self.coordinator)
        rows = self.call("get", f"{OPS}cases/{case.pk}/assignments/")
        self.assertEqual([r["status"] for r in rows], ["ASSIGNED", "REASSIGNED"])

    def test_the_old_volunteer_loses_access_on_reassignment(self):
        other_a = self.helper("08", "Volunteer C", "volunteer", [self.zone_a])
        case = self.assign()
        self.assign(case, other_a)
        self.login(self.volunteer)
        self.call("get", f"{OPS}cases/{case.pk}/", code=404)

    def test_removing_an_assignment(self):
        case = self.assign()
        self.login(self.coordinator)
        self.call("post", f"{OPS}cases/{case.pk}/unassign/", {"reason": "Shift ended"})
        case.refresh_from_db()
        self.assertIsNone(case.assigned_to)

    def test_only_one_open_assignment(self):
        case = self.assign()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CaseAssignment.objects.create(case=case, volunteer=self.other)

    def test_volunteers_and_desks_cant_assign(self):
        case = self.case()
        for user in (self.volunteer, self.desk):
            self.assign(case, self.volunteer, user, code=403)

    def test_a_coordinator_cant_assign_in_another_zone(self):
        self.assign(self.case(self.zone_b), self.other, self.coordinator, code=404)

    def test_a_volunteer_from_another_zone_cant_be_assigned(self):
        self.assign(self.case(), self.other, code=409)

    def test_a_pilgrim_cant_be_assigned(self):
        self.assign(self.case(), self.pilgrim, code=409)

    def test_a_pending_volunteer_cant_be_assigned(self):
        SafetyHelper.objects.filter(user=self.volunteer).update(status="pending")
        self.assign(code=409)

    def test_an_admin_reaches_every_zone(self):
        self.assign(self.case(self.zone_b), self.other, self.admin_user)

    def test_a_closed_case_cant_be_assigned(self):
        case = self.case()
        LostFoundCase.objects.filter(pk=case.pk).update(status="CLOSED")
        self.assign(case, code=409)


class VolunteerCaseTests(OpsTestCase):
    def setUp(self):
        super().setUp()
        self.subject = self.assign()
        self.login(self.volunteer)

    def test_lists_only_your_own(self):
        rows = self.call("get", f"{OPS}cases/?status=open")["results"]
        self.assertEqual([r["id"] for r in rows], [str(self.subject.pk)])
        self.login(self.other)
        self.assertEqual(self.call("get", f"{OPS}cases/")["results"], [])

    def test_another_volunteer_cant_open_it(self):
        self.login(self.other)
        self.call("get", f"{OPS}cases/{self.subject.pk}/", code=404)
        self.call("post", f"{OPS}cases/{self.subject.pk}/progress/", {"status": "ACCEPTED"}, 404)
        self.call("post", f"{OPS}cases/{self.subject.pk}/observation/", {"body": "x"}, 404)
        self.call("post", f"{OPS}cases/{self.subject.pk}/escalate/", {"reason": "Testing it"}, 404)

    def test_a_volunteer_gets_no_operations_routes(self):
        self.call("get", f"{LF}ops/cases/{self.subject.pk}/", code=403)
        self.call("get", f"{LF}ops/cases/", code=403)

    def test_the_work_flow(self):
        for state in ("ACCEPTED", "IN_PROGRESS", "COMPLETED"):
            self.call("post", f"{OPS}cases/{self.subject.pk}/progress/", {"status": state})
        row = CaseAssignment.objects.get()
        self.assertIsNotNone(row.completed_at)

    def test_steps_cant_be_skipped(self):
        self.call("post", f"{OPS}cases/{self.subject.pk}/progress/", {"status": "COMPLETED"}, 409)

    def test_finishing_never_changes_the_case(self):
        for state in ("ACCEPTED", "COMPLETED"):
            self.call("post", f"{OPS}cases/{self.subject.pk}/progress/", {"status": state})
        self.subject.refresh_from_db()
        self.assertEqual(self.subject.status, "SUBMITTED")
        self.assertIsNone(self.subject.reunited_at)

    def test_a_volunteer_cant_set_an_arbitrary_status(self):
        self.call("post", f"{OPS}cases/{self.subject.pk}/progress/", {"status": "REASSIGNED"}, 400)

    def test_the_view_holds_only_what_the_task_needs(self):
        text = str(self.call("get", f"{OPS}cases/{self.subject.pk}/"))
        self.assertIn("Green saree", text)
        for private in ("phone", "reporter", "notes_internal", "circumstances"):
            self.assertNotIn(private, text)

    def test_a_childs_exact_position_is_withheld(self):
        child = self.assign(self.case(vulnerabilities=["child"]))
        self.login(self.volunteer)
        seen = self.call("get", f"{OPS}cases/{child.pk}/")
        self.assertIsNone(seen["latitude"])
        self.assertEqual(seen["priority"], "high")

    def test_an_adults_position_is_available(self):
        self.assertEqual(self.call("get", f"{OPS}cases/{self.subject.pk}/")["latitude"], 19.9975)

    def test_viewing_is_audited(self):
        self.call("get", f"{OPS}cases/{self.subject.pk}/")
        self.assertTrue(CaseAudit.objects.filter(action="case_viewed", actor=self.volunteer).exists())

    def test_observations_stay_internal(self):
        self.call("post", f"{OPS}cases/{self.subject.pk}/observation/", {"body": "Seen near the gate"}, 201)
        self.login(self.pilgrim)
        self.assertNotIn("Seen near the gate", str(self.call("get", f"{LF}cases/{self.subject.pk}/")))

    def test_a_sighting_still_waits_for_review(self):
        response = self.call("post", f"{LF}cases/{self.subject.pk}/sightings/", {
            "description": "Seen", "location_text": "Gate 2", "seen_at": timezone.now().isoformat(),
        }, 201)
        self.assertEqual(response["review"], "pending")

    def test_found_reports_still_work(self):
        response = self.call("post", f"{LF}found/", {
            "found_category": "found", "clothing_description": "Blue shirt", "location_text": "Gate 2",
            "event_at": timezone.now().isoformat(),
        }, 201)
        self.assertEqual(response["case_type"], "found")


class EscalationTests(OpsTestCase):
    def test_escalating_reaches_the_zones_coordinator(self):
        case = self.assign()
        self.login(self.volunteer)
        self.call("post", f"{OPS}cases/{case.pk}/escalate/", {"reason": "Needs a coordinator"})
        users = set(Notification.objects.filter(title="Case escalated").values_list("user_id", flat=True))
        self.assertEqual(users, {self.coordinator.pk})
        self.login(self.coordinator)
        self.assertEqual(len(self.call("get", f"{OPS}escalations/")["results"]), 1)

    def test_it_changes_no_case_status(self):
        case = self.assign()
        self.login(self.volunteer)
        self.call("post", f"{OPS}cases/{case.pk}/escalate/", {"reason": "Needs a coordinator"})
        case.refresh_from_db()
        self.assertEqual(case.status, "SUBMITTED")

    def test_it_needs_a_reason(self):
        case = self.assign()
        self.login(self.volunteer)
        self.call("post", f"{OPS}cases/{case.pk}/escalate/", {"reason": "x"}, 409)

    def test_a_help_desk_can_escalate_in_its_zone(self):
        case = self.case()
        self.login(self.desk)
        self.call("post", f"{OPS}cases/{case.pk}/escalate/", {"reason": "Needs a coordinator"})

    def test_other_zones_dont_see_it(self):
        case = self.assign()
        self.login(self.volunteer)
        self.call("post", f"{OPS}cases/{case.pk}/escalate/", {"reason": "Needs a coordinator"})
        self.login(self.coordinator_b)
        self.assertEqual(self.call("get", f"{OPS}escalations/")["results"], [])


class ZoneTests(OpsTestCase):
    def test_a_position_finds_its_zone(self):
        self.assertEqual(zone_for("19.9976", "73.7899"), self.zone_a)
        self.assertIsNone(zone_for("25.0", "80.0"))
        self.assertIsNone(zone_for(None, None))

    def test_a_new_case_gets_its_zone(self):
        with mock.patch(LF_PUSH, return_value=SENT):
            case, _ = create_case(
                reporter=self.pilgrim, reporter_role="pilgrim", case_type="lost",
                data={
                    "event_at": timezone.now(), "location_text": "Ramkund", "latitude": "19.9976",
                    "longitude": "73.7899",
                },
            )
        self.assertEqual(case.zone, self.zone_a)

    def lists(self, user):
        self.login(user)
        return {r["reference"] for r in self.call("get", f"{LF}ops/cases/")["results"]}

    def test_coordinators_see_only_their_zones(self):
        here, there = self.case(), self.case(self.zone_b)
        self.assertEqual(self.lists(self.coordinator), {here.reference})
        self.login(self.coordinator)
        self.call("get", f"{LF}ops/cases/{there.pk}/", code=404)

    def test_an_unzoned_case_still_reaches_coordinators(self):
        case = self.case()
        LostFoundCase.objects.filter(pk=case.pk).update(zone=None)
        self.assertEqual(self.lists(self.coordinator), {case.reference})
        self.assertEqual(self.lists(self.coordinator_b), {case.reference})

    def test_a_help_desk_sees_its_zone_only(self):
        here, there = self.case(), self.case(self.zone_b)
        self.assertEqual(self.lists(self.desk), {here.reference})
        self.assertTrue(there.reference)

    def test_an_admin_sees_every_zone(self):
        self.case(), self.case(self.zone_b)
        self.assertEqual(len(self.lists(self.admin_user)), 2)

    def test_a_case_can_list_as_unassigned(self):
        self.case()
        self.login(self.coordinator)
        self.assertEqual(len(self.call("get", f"{LF}ops/cases/?unassigned=true")["results"]), 1)

    def test_zones_show_only_verified_places(self):
        MeetingPoint.objects.create(
            name="Desk", category="help_desk", status="verified", latitude="19.9976", longitude="73.7899",
            source_detail="Visited",
        )
        MeetingPoint.objects.create(
            name="Tree", category="family_meeting", status="community", latitude="19.9976", longitude="73.7899",
        )
        self.login(self.volunteer)
        data = self.call("get", f"{OPS}zones/")
        self.assertEqual([z["code"] for z in data], ["A"])
        self.assertEqual([p["name"] for p in data[0]["points"]], ["Desk"])

    def test_alerts_go_to_the_zones_coordinator(self):
        from apps.lostfound.policy import staff_recipients

        self.assertEqual(staff_recipients(self.zone_a.pk), [self.coordinator.pk])

    def test_a_zone_nobody_covers_still_alerts_someone(self):
        from apps.lostfound.policy import staff_recipients

        self.assertEqual(len(staff_recipients(zone("C", lat="21.0").pk)), 2)


class SosTests(OpsTestCase):
    def sos(self, the_zone=None):
        return EmergencySOS.objects.create(
            user=self.pilgrim, client_id="00000000-0000-0000-0000-000000000001", category="medical",
            status="SUBMITTED", zone=the_zone or self.zone_a,
        )

    def test_operators_see_only_their_zone(self):
        here = self.sos()
        self.login(self.coordinator)
        self.assertEqual(len(self.call("get", f"{EM}ops/sos/")["results"]), 1)
        self.login(self.desk)
        self.assertEqual(len(self.call("get", f"{EM}ops/sos/")["results"]), 1)
        self.login(self.coordinator_b)
        self.assertEqual(self.call("get", f"{EM}ops/sos/")["results"], [])
        self.call("post", f"{EM}ops/sos/{here.pk}/acknowledge/", code=404)

    def test_a_volunteer_cant_touch_an_sos(self):
        here = self.sos()
        self.login(self.volunteer)
        self.call("get", f"{EM}ops/sos/", code=403)
        for action in ("acknowledge", "coordinate", "resolve", "close", "escalate"):
            self.call("post", f"{EM}ops/sos/{here.pk}/{action}/", {"body": "x"}, 403)

    def test_a_help_desk_can_acknowledge_in_its_zone(self):
        here = self.sos()
        self.login(self.desk)
        self.assertEqual(self.call("post", f"{EM}ops/sos/{here.pk}/acknowledge/")["status"], "ACKNOWLEDGED")

    def test_escalating_tells_coordinators_and_changes_no_status(self):
        here = self.sos()
        self.login(self.desk)
        self.assertEqual(self.call("post", f"{EM}ops/sos/{here.pk}/escalate/", {"body": "Needs help"})["status"], "SUBMITTED")
        self.assertTrue(Notification.objects.filter(user=self.coordinator, title__icontains="escalated").exists())

    def test_a_responder_from_another_zone_cant_be_assigned(self):
        here = self.sos()
        self.login(self.coordinator)
        self.call("post", f"{EM}ops/sos/{here.pk}/assign/", {"assignee_id": str(self.coordinator_b.pk)}, 409)

    def test_an_unzoned_sos_still_reaches_coordinators(self):
        here = self.sos()
        EmergencySOS.objects.filter(pk=here.pk).update(zone=None)
        self.login(self.coordinator_b)
        self.assertEqual(len(self.call("get", f"{EM}ops/sos/")["results"]), 1)


class ScanTests(OpsTestCase):
    def scan(self, user):
        self.login(user)
        return self.client.post("/api/safety/scan/resolve/", {"token": "nonsense"}, format="json")

    def test_only_active_helpers_can_scan(self):
        self.assertEqual(self.scan(self.pilgrim).status_code, 403)
        self.assertEqual(self.scan(self.volunteer).status_code, 404)

    def test_a_suspended_volunteer_cant_scan(self):
        services.set_status(SafetyHelper.objects.get(user=self.volunteer), "suspended", self.admin_user)
        self.assertEqual(self.scan(self.volunteer).status_code, 403)

    def test_refused_scans_are_logged(self):
        self.scan(self.pilgrim)
        self.assertTrue(SafetyScanLog.objects.filter(user=self.pilgrim, outcome="denied").exists())


class AdminTests(OpsTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)

    def test_the_list_masks_phones(self):
        response = self.client.get(reverse("admin:safety_safetyhelper_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.volunteer.phone_number)
        self.assertNotContains(response, "setup_code_hash")

    def test_creating_a_volunteer_shows_the_code_once(self):
        response = self.client.post(reverse("admin:safety_safetyhelper_add"), {
            "phone_number": "9330000060", "full_name": "From Admin", "role": "volunteer",
            "zones": [str(self.zone_a.pk)],
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "shown only this once")
        user = User.objects.get(phone_number="+919330000060")
        self.assertFalse(user.is_staff)
        self.assertEqual(SafetyHelper.objects.get(user=user).status, "pending")

    def test_a_duplicate_is_refused_on_the_form(self):
        response = self.client.post(reverse("admin:safety_safetyhelper_add"), {
            "phone_number": self.volunteer.phone_number, "full_name": "Again", "role": "volunteer",
        })
        self.assertContains(response, "already has an operations account")

    def test_the_detail_page_opens(self):
        helper = SafetyHelper.objects.get(user=self.volunteer)
        response = self.client.get(reverse("admin:safety_safetyhelper_change", args=[helper.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.volunteer.phone_number)

    def test_changing_a_role_is_audited(self):
        helper = SafetyHelper.objects.get(user=self.volunteer)
        self.client.post(reverse("admin:safety_safetyhelper_change", args=[helper.pk]), {
            "role": "help_desk", "zones": [str(self.zone_a.pk)],
        })
        self.assertTrue(OperationsAudit.objects.filter(action="role_changed", target=self.volunteer).exists())

    def test_changing_zones_is_audited(self):
        helper = SafetyHelper.objects.get(user=self.volunteer)
        self.client.post(reverse("admin:safety_safetyhelper_change", args=[helper.pk]), {
            "role": "volunteer", "zones": [str(self.zone_b.pk)],
        })
        self.assertTrue(OperationsAudit.objects.filter(action="zones_changed", target=self.volunteer).exists())

    def test_volunteers_cant_be_deleted(self):
        request = RequestFactory().get("/")
        request.user = self.admin_user
        self.assertFalse(site._registry[SafetyHelper].has_delete_permission(request))

    def test_the_activate_action(self):
        helper, _ = services.create_volunteer(
            phone_number="+919330000061", full_name="P", role="volunteer", zones=[], by=self.admin_user,
        )
        self.client.post(reverse("admin:safety_safetyhelper_changelist"), {
            "action": "activate", "_selected_action": [str(helper.pk)],
        })
        helper.refresh_from_db()
        self.assertTrue(helper.is_current)

    def test_the_audit_is_read_only(self):
        request = RequestFactory().get("/")
        request.user = self.admin_user
        audit = site._registry[OperationsAudit]
        self.assertFalse(audit.has_add_permission(request))
        self.assertFalse(audit.has_change_permission(request))
        self.assertFalse(audit.has_delete_permission(request))
