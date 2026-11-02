import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.admin.sites import site
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.family import models
from apps.family.models import (
    EmergencyContact,
    FamilyAuditLog,
    FamilyCircle,
    FamilyInvitation,
    FamilyMember,
    GuardianLink,
    hash_code,
)

BASE = "/api/family/"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class FamilyTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.father = User.objects.create_user(phone_number="+919100000021", full_Name="Suresh More")
        self.mother = User.objects.create_user(phone_number="+919100000022", full_Name="Asha More")
        self.outsider = User.objects.create_user(phone_number="+919100000023", full_Name="Stranger")
        self.client = APIClient()
        self.login(self.father)
        self.family = self.post(f"{BASE}circles/", {"name": "More Family", "language": "mr"}, 201)
        self.url = f"{BASE}circles/{self.family['id']}/"

    def login(self, user):
        self.client.force_authenticate(user)

    def post(self, url, body=None, code=200):
        response = self.client.post(url, body or {}, format="json")
        self.assertEqual(response.status_code, code, response.content)
        return response.json().get("data") if response.content else None

    def child(self, **extra):
        body = {
            "full_name": "Aarav More", "kind": "dependent_child", "relationship": "son",
            "age_group": "6_12", **extra,
        }
        return self.post(f"{self.url}members/", body, 201)

    def invite(self, **extra):
        return self.post(f"{self.url}invitations/", {"relationship": "spouse", **extra}, 201)

    def join(self, user=None):
        self.login(self.father)
        invitation = self.invite()
        self.login(user or self.mother)
        joined = self.post(f"{BASE}invitations/accept/", {"code": invitation["code"]})
        self.login(self.father)
        return joined


class CircleTests(FamilyTestCase):
    def test_creator_becomes_organizer_with_a_random_identifier(self):
        self.assertEqual(self.family["my_role"], "organizer")
        self.assertEqual(self.family["member_count"], 1)
        self.assertEqual(len(self.family["id"]), 36, "a UUID, never a sequential id")
        me = FamilyMember.objects.get(user=self.father)
        self.assertEqual(me.kind, "account_holder")

    def test_needs_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"{BASE}circles/").status_code, 401)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_name_is_required_and_circles_are_limited(self):
        self.post(f"{BASE}circles/", {"name": "  "}, 400)
        self.post(f"{BASE}circles/", {"name": "Two"}, 201)
        self.post(f"{BASE}circles/", {"name": "Three"}, 201)
        self.post(f"{BASE}circles/", {"name": "Four"}, 400)

    def test_only_the_organizer_updates_or_deletes(self):
        self.join()
        self.login(self.mother)
        self.assertEqual(self.client.patch(self.url, {"name": "Mine"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(self.url).status_code, 403)
        self.login(self.father)
        self.assertEqual(self.client.patch(self.url, {"name": "New"}, format="json").status_code, 200)

    def test_delete_is_blocked_while_other_adults_remain(self):
        self.join()
        self.assertEqual(self.client.delete(self.url).status_code, 409)
        self.login(self.mother)
        self.post(f"{self.url}leave/", code=204)
        self.login(self.father)
        self.child()
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertFalse(FamilyMember.objects.exists())
        self.assertTrue(FamilyAuditLog.objects.filter(action="family_deleted").exists(), "audit outlives the family")


class DependentTests(FamilyTestCase):
    def test_child_has_no_account_and_organizer_is_guardian(self):
        child = self.child()
        self.assertTrue(child["is_dependent"])
        self.assertEqual(child["guardians"][0]["name"], "Suresh More")
        self.assertIsNone(FamilyMember.objects.get(pk=child["id"]).user)

    def test_elderly_dependent_needs_a_recorded_basis(self):
        body = {"full_name": "Aji", "kind": "dependent_elderly", "relationship": "grandmother", "age_group": "senior"}
        self.post(f"{self.url}members/", body, 400)
        added = self.post(f"{self.url}members/", {**body, "consent_basis": "agreed"}, 201)
        self.assertEqual(added["consent_basis"], "agreed")
        log = FamilyAuditLog.objects.get(action="dependent_added")
        self.assertEqual(log.details["consent_basis"], "agreed")

    def test_validation(self):
        for extra in (
            {"full_name": " "}, {"relationship": "self"}, {"mobile": "12345"},
            {"date_of_birth": (date.today() + timedelta(days=1)).isoformat()}, {"kind": "independent_adult"},
        ):
            self.post(f"{self.url}members/", {
                "full_name": "A", "kind": "dependent_child", "relationship": "son", "age_group": "6_12", **extra,
            }, 400)
        self.post(f"{self.url}members/", {"full_name": "A", "kind": "dependent_child", "relationship": "son"}, 400)

    def test_adults_cannot_be_added_directly(self):
        """No route creates an account member without their acceptance."""
        response = self.client.post(f"{self.url}members/", {
            "full_name": "Asha", "kind": "independent_adult", "relationship": "spouse",
            "user": str(self.mother.pk), "age_group": "adult",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FamilyMember.objects.filter(user=self.mother).exists())

    def test_database_rejects_impossible_members(self):
        family = FamilyCircle.objects.get(pk=self.family["id"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            FamilyMember.objects.create(family=family, kind="independent_adult", relationship="spouse")
        with self.assertRaises(IntegrityError), transaction.atomic():
            FamilyMember.objects.create(family=family, user=self.mother, kind="dependent_child", relationship="son")
        with self.assertRaises(IntegrityError), transaction.atomic():
            FamilyMember.objects.create(
                family=family, user=self.mother, kind="independent_adult", role="organizer", relationship="spouse",
            )

    def test_guardians_can_edit_and_the_edit_is_scoped(self):
        child = self.child()
        url = f"{self.url}members/{child['id']}/"
        self.assertEqual(self.client.patch(url, {"full_name": "Aarav S"}, format="json").status_code, 200)
        self.join()
        self.login(self.mother)
        self.assertEqual(self.client.patch(url, {"full_name": "No"}, format="json").status_code, 403)

    def test_organizer_manages_dependents_without_being_their_guardian(self):
        child = self.child()
        mother = self.join()["member_id"]
        GuardianLink.objects.filter(dependent_id=child["id"]).delete()
        GuardianLink.objects.create(dependent_id=child["id"], guardian_id=mother)
        url = f"{self.url}members/{child['id']}/"
        self.assertEqual(self.client.patch(url, {"language": "hi"}, format="json").status_code, 200)
        self.post(f"{url}contacts/", {"name": "Aunt", "mobile": "9876543210"}, 201)

    def test_multiple_guardians(self):
        child = self.child()
        mother = self.join()["member_id"]
        url = f"{self.url}members/{child['id']}/guardians/"
        self.post(url, {"member_id": mother}, 201)
        self.login(self.mother)
        edit = self.client.patch(f"{self.url}members/{child['id']}/", {"language": "hi"}, format="json")
        self.assertEqual(edit.status_code, 200)
        self.post(url, {"member_id": mother}, 403)  # guardians don't appoint guardians
        self.login(self.father)
        self.assertEqual(self.client.delete(f"{url}{mother}/").status_code, 204)
        organizer = FamilyMember.objects.get(user=self.father).pk
        self.assertEqual(self.client.delete(f"{url}{organizer}/").status_code, 409, "never left without a guardian")

    def test_a_dependent_cannot_be_a_guardian(self):
        one, two = self.child(), self.child(full_name="Second")
        self.post(f"{self.url}members/{one['id']}/guardians/", {"member_id": two["id"]}, 400)

    def test_dependents_are_reassigned_when_a_sole_guardian_goes(self):
        child = self.child()
        mother = self.join()["member_id"]
        GuardianLink.objects.filter(dependent_id=child["id"]).delete()
        GuardianLink.objects.create(dependent_id=child["id"], guardian_id=mother)
        self.login(self.mother)
        self.post(f"{self.url}leave/", code=204)
        link = GuardianLink.objects.get(dependent_id=child["id"])
        self.assertEqual(link.guardian.user, self.father)


class InvitationTests(FamilyTestCase):
    def test_code_is_random_and_never_stored(self):
        invitation = self.invite()
        self.assertEqual(len(invitation["code"]), 12)
        stored = FamilyInvitation.objects.get()
        self.assertEqual(stored.code_hash, hash_code(invitation["code"]))
        self.assertNotIn(invitation["code"], str(stored.__dict__))
        listed = self.client.get(f"{self.url}invitations/").json()["data"]
        self.assertNotIn("code", listed[0])

    def test_invitee_reviews_then_consents(self):
        code = self.invite()["code"]
        self.login(self.mother)
        preview = self.post(f"{BASE}invitations/lookup/", {"code": code})
        self.assertEqual((preview["family_name"], preview["organizer_name"]), ("More Family", "Suresh More"))
        self.assertFalse(FamilyMember.objects.filter(user=self.mother).exists(), "reviewing isn't joining")
        self.post(f"{BASE}invitations/accept/", {"code": code})
        member = FamilyMember.objects.get(user=self.mother)
        self.assertEqual((member.kind, member.role), ("independent_adult", "member"))
        self.assertFalse(member.share_phone or member.location_sharing_consent, "everything starts private")

    def test_single_use(self):
        code = self.invite()["code"]
        self.login(self.mother)
        self.post(f"{BASE}invitations/accept/", {"code": code})
        self.login(self.outsider)
        self.post(f"{BASE}invitations/accept/", {"code": code}, 404)

    def test_expiry_and_revoke_and_decline(self):
        expired = self.invite()
        FamilyInvitation.objects.filter(pk=expired["id"]).update(expires_at=timezone.now() - timedelta(minutes=1))
        revoked = self.invite()
        self.post(f"{self.url}invitations/{revoked['id']}/revoke/")
        declined = self.invite()
        self.login(self.mother)
        self.post(f"{BASE}invitations/lookup/", {"code": expired["code"]}, 404)
        self.post(f"{BASE}invitations/accept/", {"code": expired["code"]}, 404)
        self.post(f"{BASE}invitations/accept/", {"code": revoked["code"]}, 404)
        self.post(f"{BASE}invitations/decline/", {"code": declined["code"]}, 204)
        self.post(f"{BASE}invitations/accept/", {"code": declined["code"]}, 404)
        self.assertFalse(FamilyMember.objects.filter(user=self.mother).exists())

    def test_in_app_invitation_is_only_for_that_number(self):
        invitation = self.invite(phone="9100000022")
        self.login(self.outsider)
        self.post(f"{BASE}invitations/accept/", {"code": invitation["code"]}, 404)
        self.post(f"{BASE}invitations/accept/", {"invitation_id": invitation["id"]}, 404)
        self.assertEqual(self.client.get(f"{BASE}invitations/mine/").json()["data"], [])
        self.login(self.mother)
        mine = self.client.get(f"{BASE}invitations/mine/").json()["data"]
        self.assertEqual(mine[0]["family_name"], "More Family")
        self.post(f"{BASE}invitations/accept/", {"invitation_id": invitation["id"]})
        self.assertTrue(FamilyMember.objects.filter(user=self.mother).exists())

    def test_inviting_a_number_reveals_nothing_about_accounts(self):
        known = self.invite(phone="9100000022")
        unknown = self.invite(phone="9888888888")
        self.assertEqual(set(known), set(unknown))
        self.assertEqual(known["state"], unknown["state"])

    def test_only_the_organizer_invites_or_revokes(self):
        self.join()
        invitation = self.invite()
        self.login(self.mother)
        self.post(f"{self.url}invitations/", {"relationship": "son"}, 403)
        self.post(f"{self.url}invitations/{invitation['id']}/revoke/", code=403)
        self.assertEqual(self.client.get(f"{self.url}invitations/").status_code, 403)

    def test_rejects_bad_requests(self):
        self.post(f"{self.url}invitations/", {"relationship": "self"}, 400)
        self.post(f"{self.url}invitations/", {"relationship": "spouse", "phone": "123"}, 400)
        self.login(self.mother)
        self.post(f"{BASE}invitations/lookup/", {"code": "WRONGCODE123"}, 404)
        self.post(f"{BASE}invitations/lookup/", {}, 404)

    def test_guessing_is_throttled(self):
        self.login(self.outsider)
        codes = [
            self.client.post(f"{BASE}invitations/lookup/", {"code": f"GUESS{i}"}, format="json").status_code
            for i in range(25)
        ]
        self.assertIn(429, codes)

    def test_already_a_member(self):
        code = self.invite()["code"]
        self.post(f"{BASE}invitations/accept/", {"code": code}, 409)


class PrivacyTests(FamilyTestCase):
    def setUp(self):
        super().setUp()
        self.mother_id = self.join()["member_id"]
        self.father_id = str(FamilyMember.objects.get(user=self.father).pk)

    def test_outsiders_get_404_everywhere(self):
        child = self.child()
        contact = self.post(f"{self.url}contacts/", {"name": "Uncle", "mobile": "9876543210"}, 201)
        invitation = self.invite()
        self.login(self.outsider)
        for url in (
            self.url, f"{self.url}members/", f"{self.url}members/{child['id']}/",
            f"{self.url}members/{child['id']}/photo/", f"{self.url}members/{child['id']}/contacts/",
            f"{self.url}contacts/", f"{self.url}invitations/",
        ):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        for url in (
            f"{self.url}leave/", f"{self.url}members/", f"{self.url}contacts/reorder/",
            f"{self.url}invitations/{invitation['id']}/revoke/", f"{self.url}organizer/accept/",
        ):
            self.assertEqual(self.client.post(url, {}, format="json").status_code, 404, url)
        self.assertEqual(self.client.delete(f"{self.url}contacts/{contact['id']}/").status_code, 404)
        self.assertEqual(self.client.delete(self.url).status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}circles/").json()["data"], [])

    def test_ids_from_another_family_are_refused(self):
        child = self.child()
        self.login(self.outsider)
        other = self.post(f"{BASE}circles/", {"name": "Other"}, 201)
        url = f"{BASE}circles/{other['id']}/"
        self.assertEqual(self.client.get(f"{url}members/{child['id']}/").status_code, 404)
        self.assertEqual(self.client.delete(f"{url}members/{child['id']}/").status_code, 404)
        self.post(f"{url}members/{child['id']}/contacts/", {"name": "x", "mobile": "9876543210"}, 404)

    def test_organizer_cannot_edit_or_impersonate_an_adult(self):
        url = f"{self.url}members/{self.mother_id}/"
        for body in ({"language": "hi"}, {"share_phone": True}, {"location_sharing_consent": True}):
            self.assertEqual(self.client.patch(url, body, format="json").status_code, 403)
        self.post(f"{url}contacts/", {"name": "x", "mobile": "9876543210"}, 403)
        photo = self.client.put(f"{url}photo/", {"photo": SimpleUploadedFile("a.png", PNG)}, format="multipart")
        self.assertEqual(photo.status_code, 403)

    def test_organizer_may_correct_a_relationship_label_only(self):
        url = f"{self.url}members/{self.mother_id}/"
        self.assertEqual(self.client.patch(url, {"relationship": "mother"}, format="json").status_code, 200)

    def test_adult_details_stay_private_until_they_choose(self):
        url = f"{self.url}members/{self.mother_id}/"
        seen = self.client.get(url).json()["data"]
        self.assertIsNone(seen["phone"])
        self.assertIsNone(seen["privacy"], "their choices aren't shown to others")
        self.login(self.mother)
        self.assertEqual(self.client.patch(url, {"share_phone": True}, format="json").status_code, 200)
        self.login(self.father)
        self.assertEqual(self.client.get(url).json()["data"]["phone"], "+919100000022")

    def test_adult_contacts_are_private_from_the_organizer_by_default(self):
        self.login(self.mother)
        url = f"{self.url}members/{self.mother_id}/"
        contact = self.post(f"{url}contacts/", {"name": "Sister", "mobile": "9876543210"}, 201)
        self.login(self.father)
        self.assertEqual(self.client.get(f"{url}contacts/").status_code, 403)
        self.assertEqual(self.client.delete(f"{self.url}contacts/{contact['id']}/").status_code, 403)
        self.login(self.mother)
        self.client.patch(url, {"share_contacts_with_organizer": True}, format="json")
        self.login(self.father)
        self.assertEqual(self.client.get(f"{url}contacts/").status_code, 200)
        self.assertEqual(self.client.delete(f"{self.url}contacts/{contact['id']}/").status_code, 403, "read, not edit")

    def test_dependent_details_go_only_to_guardians(self):
        child = self.child(mobile="9876543210", date_of_birth="2018-01-01")
        url = f"{self.url}members/{child['id']}/"
        self.assertEqual(self.client.get(url).json()["data"]["phone"], "+919876543210")
        self.login(self.mother)
        seen = self.client.get(url).json()["data"]
        self.assertIsNone(seen["phone"])
        self.assertIsNone(seen["date_of_birth"])
        listed = self.client.get(f"{self.url}members/").json()["data"]
        self.assertTrue(all(m["phone"] is None for m in listed if m["is_dependent"]))
        self.assertEqual(self.client.get(f"{url}contacts/").status_code, 403)

    def test_photos_are_private_and_checked_by_content(self):
        child = self.child()
        url = f"{self.url}members/{child['id']}/photo/"
        bad = self.client.put(url, {"photo": SimpleUploadedFile("x.png", b"<script>")}, format="multipart")
        self.assertEqual(bad.status_code, 400)
        big = SimpleUploadedFile("x.png", PNG + b"0" * (2 * 1024 * 1024))
        self.assertEqual(self.client.put(url, {"photo": big}, format="multipart").status_code, 400)
        self.assertEqual(self.client.put(url, {"photo": SimpleUploadedFile("x.png", PNG)}, format="multipart").status_code, 200)
        got = self.client.get(url)
        self.assertEqual(got["Content-Type"], "image/png")
        self.assertIn("no-store", got["Cache-Control"])
        self.login(self.mother)
        self.assertEqual(self.client.get(url).status_code, 200, "the family can see the photo")
        self.assertEqual(self.client.delete(url).status_code, 403, "only a guardian changes it")
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_removing_and_leaving(self):
        self.assertEqual(self.client.delete(f"{self.url}members/{self.father_id}/").status_code, 403)
        self.post(f"{self.url}leave/", code=409)
        self.login(self.mother)
        self.assertEqual(self.client.delete(f"{self.url}members/{self.father_id}/").status_code, 403)
        self.post(f"{self.url}leave/", code=204)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.login(self.father)
        mother = self.join()["member_id"]
        self.assertEqual(self.client.delete(f"{self.url}members/{mother}/").status_code, 204)
        self.assertTrue(FamilyAuditLog.objects.filter(action="member_removed").exists())

    def test_organizer_role_moves_only_with_acceptance(self):
        self.login(self.mother)
        self.post(f"{self.url}organizer/", {"member_id": self.mother_id}, 403)
        self.post(f"{self.url}organizer/accept/", code=403)
        self.login(self.father)
        self.post(f"{self.url}organizer/", {"member_id": self.mother_id})
        self.assertEqual(FamilyMember.objects.get(user=self.father).role, "organizer")
        self.login(self.mother)
        self.assertTrue(self.client.get(self.url).json()["data"]["organizer_offer_for_me"])
        self.post(f"{self.url}organizer/accept/")
        self.assertEqual(FamilyMember.objects.get(user=self.mother).role, "organizer")
        self.assertEqual(FamilyMember.objects.get(user=self.father).role, "member")

    def test_sensitive_changes_are_audited_without_personal_details(self):
        self.login(self.mother)
        self.client.patch(f"{self.url}members/{self.mother_id}/", {"share_phone": True}, format="json")
        log = FamilyAuditLog.objects.get(action="privacy_changed")
        self.assertEqual(log.details, {"fields": ["share_phone"]})


class AccountDeletionTests(FamilyTestCase):
    def test_a_family_with_no_adult_left_is_removed(self):
        self.child()
        self.father.delete()
        self.assertFalse(FamilyCircle.objects.exists())
        self.assertFalse(FamilyMember.objects.exists())

    def test_the_organizer_role_opens_up_for_the_remaining_adult(self):
        self.join()
        self.father.delete()
        self.login(self.mother)
        self.assertTrue(self.client.get(self.url).json()["data"]["organizer_offer_for_me"])
        self.post(f"{self.url}organizer/accept/")
        self.assertEqual(FamilyMember.objects.get(user=self.mother).role, "organizer")


class ContactTests(FamilyTestCase):
    def test_lifecycle_and_priority(self):
        child = self.child()
        url = f"{self.url}members/{child['id']}/contacts/"
        one = self.post(url, {"name": "Aunt", "mobile": "9876543210", "method": "whatsapp"}, 201)
        two = self.post(url, {"name": "Uncle", "mobile": "+91 98765 43211"}, 201)
        self.assertEqual((one["priority"], two["priority"], two["mobile"]), (1, 2, "+919876543211"))
        ordered = self.post(f"{self.url}contacts/reorder/", {"member_id": child["id"], "contact_ids": [two["id"], one["id"]]})
        self.assertEqual([c["name"] for c in ordered], ["Uncle", "Aunt"])
        contact = f"{self.url}contacts/{one['id']}/"
        self.assertEqual(self.client.patch(contact, {"name": "Aunty"}, format="json").json()["data"]["name"], "Aunty")
        self.assertEqual(self.client.delete(contact).status_code, 204)

    def test_validation_and_limits(self):
        self.post(f"{self.url}contacts/", {"name": "x", "mobile": "123"}, 400)
        self.post(f"{self.url}contacts/", {"name": " ", "mobile": "9876543210"}, 400)
        self.post(f"{self.url}contacts/reorder/", {"contact_ids": ["bad"]}, 400)
        for i in range(EmergencyContact.MAX_PER_OWNER):
            self.post(f"{self.url}contacts/", {"name": f"c{i}", "mobile": "9876543210"}, 201)
        self.post(f"{self.url}contacts/", {"name": "x", "mobile": "9876543210"}, 400)

    def test_family_contacts_are_readable_by_members_but_set_by_the_organizer(self):
        self.join()
        self.post(f"{self.url}contacts/", {"name": "Uncle", "mobile": "9876543210"}, 201)
        self.login(self.mother)
        self.assertEqual(len(self.client.get(f"{self.url}contacts/").json()["data"]), 1)
        self.post(f"{self.url}contacts/", {"name": "x", "mobile": "9876543210"}, 403)


class OfflineSyncTests(FamilyTestCase):
    ID = "3f2b8c1e-7a44-4d19-9f0e-6c1d2a7b4e55"

    def contact(self, **extra):
        return self.post(f"{self.url}contacts/", {"name": "Uncle", "mobile": "9876543210", **extra}, 201)

    def test_a_retried_create_makes_no_duplicate(self):
        first = self.contact(id=self.ID)
        self.assertEqual(first["id"], self.ID)
        again = self.post(f"{self.url}contacts/", {"id": self.ID, "name": "Uncle", "mobile": "9876543210"}, 200)
        self.assertEqual(again["id"], self.ID)
        self.assertEqual(EmergencyContact.objects.count(), 1)
        self.assertEqual(FamilyAuditLog.objects.filter(action="contact_added").count(), 1)

    def test_an_id_cant_reach_another_family(self):
        self.contact(id=self.ID)
        self.login(self.outsider)
        other = self.post(f"{BASE}circles/", {"name": "Other"}, 201)
        self.post(f"{BASE}circles/{other['id']}/contacts/", {"id": self.ID, "name": "x", "mobile": "9876543210"}, 400)
        self.assertEqual(EmergencyContact.objects.get().family_id, FamilyCircle.objects.get(name="More Family").pk)

    def test_bad_id_is_refused(self):
        self.post(f"{self.url}contacts/", {"id": "nope", "name": "x", "mobile": "9876543210"}, 400)

    def patch(self, contact, body, tag):
        return self.client.patch(
            f"{self.url}contacts/{contact['id']}/", body, format="json", headers={"If-Match": tag},
        )

    def test_matching_version_updates(self):
        contact = self.contact()
        response = self.patch(contact, {"name": "New"}, contact["updated_at"])
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()["data"]["updated_at"], contact["updated_at"])

    def test_stale_update_is_refused_with_the_current_record(self):
        contact = self.contact()
        self.patch(contact, {"name": "Newer"}, contact["updated_at"])
        response = self.patch(contact, {"name": "Stale"}, contact["updated_at"])
        self.assertEqual(response.status_code, 412)
        self.assertEqual(response.json()["data"]["name"], "Newer")
        self.assertEqual(EmergencyContact.objects.get().name, "Newer")

    def test_stale_delete_is_refused(self):
        contact = self.contact()
        self.patch(contact, {"name": "Newer"}, contact["updated_at"])
        url = f"{self.url}contacts/{contact['id']}/"
        response = self.client.delete(url, headers={"If-Match": contact["updated_at"]})
        self.assertEqual(response.status_code, 412)
        self.assertTrue(EmergencyContact.objects.exists())

    def test_reordering_doesnt_count_as_an_edit(self):
        one, two = self.contact(), self.contact(name="Aunt")
        self.post(f"{self.url}contacts/reorder/", {"contact_ids": [two["id"], one["id"]]})
        self.assertEqual(self.patch(one, {"name": "x"}, one["updated_at"]).status_code, 200)

    def test_a_bad_version_is_refused_and_no_header_still_works(self):
        contact = self.contact()
        self.assertEqual(self.patch(contact, {"name": "x"}, "yesterday").status_code, 400)
        url = f"{self.url}contacts/{contact['id']}/"
        self.assertEqual(self.client.patch(url, {"name": "y"}, format="json").status_code, 200)

    def test_permission_is_checked_before_the_version(self):
        self.join()
        contact = self.contact()
        self.login(self.mother)
        self.assertEqual(self.patch(contact, {"name": "x"}, "2020-01-01T00:00:00Z").status_code, 403)


class InvitationLinkTests(FamilyTestCase):
    def token_of(self, invitation):
        base, _, fragment = invitation["link"].partition("#t=")
        self.assertEqual(base, "https://kumbhapath.in/join/family")
        return fragment

    def link(self, **extra):
        invitation = self.invite(**extra)
        return invitation, self.token_of(invitation)

    def test_links_are_long_unique_and_never_stored(self):
        first, token = self.link()
        _, other = self.link()
        self.assertGreaterEqual(len(token), 43)
        self.assertNotEqual(token, other)
        stored = FamilyInvitation.objects.get(pk=first["id"])
        self.assertEqual(stored.link_hash, hash_code(token))
        self.assertNotIn(token, str(stored.__dict__))
        listed = self.client.get(f"{self.url}invitations/").json()["data"]
        self.assertNotIn("link", listed[0])

    def test_token_is_only_ever_after_the_hash(self):
        _, token = self.link()
        self.assertNotIn("?", self.invite()["link"])
        self.assertEqual(self.invite()["link"].count("#"), 1)
        self.assertNotIn(token, "https://kumbhapath.in/join/family")

    def test_a_link_needs_a_signed_in_user(self):
        _, token = self.link()
        self.client.force_authenticate(None)
        for action in ("lookup", "accept", "decline"):
            response = self.client.post(f"{BASE}invitations/{action}/", {"token": token}, format="json")
            self.assertEqual(response.status_code, 401)

    def test_review_then_accept(self):
        _, token = self.link()
        self.login(self.mother)
        preview = self.post(f"{BASE}invitations/lookup/", {"token": token})
        self.assertEqual(preview["family_name"], "More Family")
        self.assertFalse(preview["already_member"])
        self.assertFalse(FamilyMember.objects.filter(user=self.mother).exists(), "reviewing isn't joining")
        self.post(f"{BASE}invitations/accept/", {"token": token})
        self.assertEqual(FamilyMember.objects.get(user=self.mother).kind, "independent_adult")

    def test_review_shows_nothing_beyond_the_decision(self):
        self.post(f"{self.url}contacts/", {"name": "Uncle Secret", "mobile": "9876543210"}, 201)
        self.child()
        _, token = self.link()
        self.login(self.mother)
        preview = self.post(f"{BASE}invitations/lookup/", {"token": token})
        self.assertEqual(set(preview), {
            "id", "family_name", "organizer_name", "member_count", "relationship", "state",
            "expires_at", "already_member",
        })
        text = str(preview)
        for private in ("Uncle Secret", "Aarav", "9876543210", "+919100000021", self.family["id"]):
            self.assertNotIn(private, text)

    def closed(self, action, token, state):
        response = self.client.post(f"{BASE}invitations/{action}/", {"token": token}, format="json")
        self.assertEqual(response.status_code, 410, response.content)
        body = response.json()
        self.assertEqual(body["errors"]["state"], state)
        self.assertNotIn("data", body)
        self.assertNotIn("More Family", str(body))

    def test_single_use(self):
        _, token = self.link()
        self.login(self.mother)
        self.post(f"{BASE}invitations/accept/", {"token": token})
        self.login(self.outsider)
        self.closed("lookup", token, "accepted")
        self.closed("accept", token, "accepted")
        self.assertFalse(FamilyMember.objects.filter(user=self.outsider).exists())

    def test_expired(self):
        invitation, token = self.link()
        FamilyInvitation.objects.filter(pk=invitation["id"]).update(
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.login(self.mother)
        self.closed("lookup", token, "expired")
        self.closed("accept", token, "expired")
        self.closed("decline", token, "expired")

    def test_revoked(self):
        invitation, token = self.link()
        self.post(f"{self.url}invitations/{invitation['id']}/revoke/")
        self.login(self.mother)
        self.closed("lookup", token, "revoked")
        self.closed("accept", token, "revoked")
        self.assertFalse(FamilyMember.objects.filter(user=self.mother).exists())

    def test_declined(self):
        _, token = self.link()
        self.login(self.mother)
        self.post(f"{BASE}invitations/decline/", {"token": token}, 204)
        self.closed("accept", token, "declined")
        self.assertFalse(FamilyMember.objects.filter(user=self.mother).exists())

    def test_link_and_code_end_together(self):
        invitation, token = self.link()
        self.login(self.mother)
        self.post(f"{BASE}invitations/accept/", {"code": invitation["code"]})
        self.login(self.outsider)
        self.closed("accept", token, "accepted")

    def test_unknown_tokens_get_the_same_404(self):
        self.login(self.mother)
        for bad in ("x" * 43, "", 5, ["a"], {"a": 1}):
            self.post(f"{BASE}invitations/lookup/", {"token": bad}, 404)
            self.post(f"{BASE}invitations/accept/", {"token": bad}, 404)

    def test_a_code_cant_be_used_as_a_token_or_the_reverse(self):
        invitation, token = self.link()
        self.login(self.mother)
        self.post(f"{BASE}invitations/lookup/", {"token": invitation["code"]}, 404)
        self.post(f"{BASE}invitations/lookup/", {"code": token}, 404)

    def test_a_closed_code_still_says_nothing(self):
        invitation, _ = self.link()
        self.post(f"{self.url}invitations/{invitation['id']}/revoke/")
        self.login(self.mother)
        self.post(f"{BASE}invitations/lookup/", {"code": invitation["code"]}, 404)

    def test_a_targeted_link_only_works_for_that_number(self):
        _, token = self.link(phone="9100000022")
        self.login(self.outsider)
        self.post(f"{BASE}invitations/lookup/", {"token": token}, 404)
        self.post(f"{BASE}invitations/accept/", {"token": token}, 404)
        self.post(f"{BASE}invitations/decline/", {"token": token}, 404)
        self.login(self.mother)
        self.post(f"{BASE}invitations/accept/", {"token": token})

    def test_the_organizer_opening_their_own_link(self):
        _, token = self.link()
        preview = self.post(f"{BASE}invitations/lookup/", {"token": token})
        self.assertTrue(preview["already_member"])
        self.post(f"{BASE}invitations/accept/", {"token": token}, 409)

    def test_tokens_are_throttled(self):
        self.login(self.outsider)
        codes = [
            self.client.post(f"{BASE}invitations/lookup/", {"token": f"guess{i}"}, format="json").status_code
            for i in range(25)
        ]
        self.assertIn(429, codes)

    def test_old_invitations_without_links_still_work_by_code(self):
        invitation = self.invite()
        FamilyInvitation.objects.filter(pk=invitation["id"]).update(link_hash=None)
        self.invite()  # a second row with no link must not clash
        FamilyInvitation.objects.update(link_hash=None)
        self.login(self.mother)
        self.post(f"{BASE}invitations/accept/", {"code": invitation["code"]})


class AssociationFileTests(TestCase):
    """The files published at https://kumbhapath.in/.well-known/."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        path = Path(settings.BASE_DIR) / "deploy/kumbhapath-web/build_association_files.py"
        spec = importlib.util.spec_from_file_location("build_association_files", path)
        cls.build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.build)

    GOOD = {
        "android_package": "in.kumbhapath.app",
        "android_sha256": ["AB:" * 31 + "AB"],
        "android_debug_sha256": [],
        "apple_team_id": "A1B2C3D4E5",
        "ios_bundle_id": "in.kumbhapath.app",
    }

    def test_current_files_match_the_identity_file(self):
        identity = self.build.load_identity()
        folder = Path(settings.BASE_DIR) / "deploy/kumbhapath-web/.well-known"
        self.assertEqual(
            json.loads((folder / "assetlinks.json").read_text()), self.build.assetlinks(identity),
        )
        self.assertEqual(
            json.loads((folder / "apple-app-site-association").read_text()), self.build.apple(identity),
        )

    def test_a_complete_identity_passes(self):
        self.assertEqual(self.build.problems(self.GOOD), [])
        self.assertEqual(
            self.build.apple(self.GOOD)["applinks"]["details"][0]["appIDs"], ["A1B2C3D4E5.in.kumbhapath.app"],
        )

    def test_production_refuses_anything_unfinished(self):
        for change in (
            {"android_package": "com.example.kumbha_path"},
            {"ios_bundle_id": "com.example.kumbhaPath"},
            {"android_sha256": []},
            {"android_sha256": ["not-a-fingerprint"]},
            {"android_sha256": self.GOOD["android_debug_sha256"] + ["AB:CD"]},
            {"apple_team_id": None},
            {"apple_team_id": "short"},
        ):
            self.assertTrue(self.build.problems({**self.GOOD, **change}), change)

    def test_the_debug_key_cant_reach_production(self):
        fingerprint = self.GOOD["android_sha256"][0]
        self.assertTrue(self.build.problems({**self.GOOD, "android_debug_sha256": [fingerprint]}))

    def test_the_current_identity_is_not_production_ready(self):
        self.assertTrue(self.build.problems(self.build.load_identity()))


class AdminTests(TestCase):
    def test_pages_render_without_private_details(self):
        staff = User.objects.create_superuser("admin@example.org", "+919100000031", "pw-for-tests")
        owner = User.objects.create_user(phone_number="+919100000032", full_Name="Suresh More")
        family = FamilyCircle.objects.create(name="More Family")
        organizer = FamilyMember.objects.create(
            family=family, user=owner, kind="account_holder", role="organizer", relationship="self",
        )
        child = FamilyMember.objects.create(
            family=family, kind="dependent_child", relationship="son", full_name="Aarav Secret", mobile="+919812345678",
        )
        GuardianLink.objects.create(dependent=child, guardian=organizer)
        FamilyInvitation.objects.create(
            family=family, code_hash="a" * 64, relationship="son", expires_at=timezone.now(),
        )
        self.client.force_login(staff)
        for url in (
            "/admin/family/familycircle/", f"/admin/family/familycircle/{family.pk}/change/",
            "/admin/family/familymember/", f"/admin/family/familymember/{child.pk}/change/",
            "/admin/family/guardianlink/", "/admin/family/familyinvitation/", "/admin/family/familyauditlog/",
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertNotContains(response, "Aarav Secret")
            self.assertNotContains(response, "+919812345678")

    def test_nothing_private_is_registered_or_editable(self):
        self.assertNotIn(models.EmergencyContact, site._registry)
        self.assertNotIn(models.MemberPhoto, site._registry)
        request = type("R", (), {"user": None})()
        for model in (models.FamilyCircle, models.FamilyMember, models.FamilyInvitation, models.FamilyAuditLog):
            admin = site._registry[model]
            self.assertFalse(admin.has_change_permission(request))
            self.assertFalse(admin.has_add_permission(request))
        self.assertNotIn("full_name", site._registry[models.FamilyMember].fields)
        self.assertNotIn("code_hash", site._registry[models.FamilyInvitation].fields)
        self.assertNotIn("link_hash", site._registry[models.FamilyInvitation].fields)
