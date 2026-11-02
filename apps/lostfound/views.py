"""
Lost & Found API (all under /api/lostfound/, JWT required).

Pilgrim routes return only a case's family view. `ops/` routes are for staff,
and an ordinary user gets 403 there. A case someone can't reach answers 404, the
same as one that doesn't exist, so references can't be tested.
"""

from django.http import Http404
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.family.models import FamilyMember
from apps.family.views import error, forbidden, ok
from apps.lostfound import ai, matching, policy, serializers, services
from apps.lostfound.models import (
    ACTIVE_STATUSES,
    CaseAttachment,
    CaseMatch,
    CaseNote,
    CaseSighting,
    CaseTranslation,
    LostFoundCase,
)
from apps.lostfound.services import CaseError


OPEN_MATCHES = ("suggested", "approved")


class ReportThrottle(UserRateThrottle):
    scope = "lostfound_report"
    rate = "20/hour"


class AIThrottle(UserRateThrottle):
    scope = "lostfound_ai"
    rate = "60/hour"


class ContributionThrottle(UserRateThrottle):
    scope = "lostfound_contribution"
    rate = "60/hour"


class _Base(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def case_for(self, request, case_id):
        """404 for anything this person can't see."""
        case = get_object_or_404(LostFoundCase.objects.select_related("member__user"), pk=case_id)
        if not policy.can_view(request.user, case):
            return None
        return case

    def nothing(self):
        return error({"detail": "Not found."}, status.HTTP_404_NOT_FOUND)

    def family_case(self, request, case_id):
        case = self.case_for(request, case_id)
        return case if case is not None and policy.is_family_side(request.user, case) else None

    def family_view(self, request, case, code=status.HTTP_200_OK):
        return ok(serializers.FamilyCaseSerializer(case, context={"request": request}).data, code)

    def run(self, action):
        """Turns a refused change into a 409 with its reason."""
        try:
            return action()
        except CaseError as refused:
            return error({refused.field: [refused.message]}, status.HTTP_409_CONFLICT)


class CapabilitiesAPI(_Base):
    def get(self, request):
        role = policy.helper_role(request.user)
        return ok({
            "role": role,
            "can_report_found": role is not None,
            "can_operate": role in (policy.STAFF, policy.HELP_DESK),
            "is_staff": role == policy.STAFF,
        })


class CaseListAPI(_Base):
    def get_throttles(self):
        return [ReportThrottle()] if self.request.method == "POST" else []

    def get(self, request):
        """Reports this person made, and cases in families they can see."""
        cases = LostFoundCase.objects.filter(
            Q(reporter=request.user) | Q(family__members__user=request.user),
        ).select_related("member").distinct()
        visible = [c for c in cases[:100] if policy.can_view(request.user, c)]
        return ok(serializers.CaseListSerializer(visible, many=True).data)

    def post(self, request):
        """A missing-person report. Repeating a client_id returns the first."""
        serializer = serializers.LostReportSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        data = dict(serializer.validated_data)
        client_id = data.pop("client_id", None)
        family_id = data.pop("family_id", None)
        member_id = data.pop("member_id", None)
        member = None
        family = None
        if member_id:
            actor = FamilyMember.objects.filter(user=request.user, family_id=family_id).select_related("family").first()
            member = FamilyMember.objects.filter(pk=member_id, family_id=family_id).select_related("user").first()
            if actor is None or member is None:
                return error({"member_id": ["Choose someone in your family."]})
            family = actor.family
            data.setdefault("person_name", member.display_name)
            kind = {"dependent_child": "child", "dependent_elderly": "elderly"}.get(member.kind)
            if kind and kind not in data.get("vulnerabilities", []):
                data["vulnerabilities"] = [*data.get("vulnerabilities", []), kind]
        case, created = services.create_case(
            reporter=request.user, reporter_role="pilgrim", case_type=LostFoundCase.Type.LOST,
            data=data, member=member, family=family, client_id=client_id,
        )
        body = dict(serializers.CaseListSerializer(case).data)
        body["duplicate"] = not created
        return ok(body, status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class FoundReportAPI(_Base):
    throttle_classes = [ReportThrottle]

    def post(self, request):
        role = policy.helper_role(request.user)
        if role is None:
            return forbidden()
        serializer = serializers.FoundReportSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        data = dict(serializer.validated_data)
        client_id = data.pop("client_id", None)
        if data["found_category"] == LostFoundCase.FoundCategory.CHILD:
            data["vulnerabilities"] = sorted({*data.get("vulnerabilities", []), "child"})
        case, created = services.create_case(
            reporter=request.user, reporter_role=role, case_type=LostFoundCase.Type.FOUND,
            data=data, client_id=client_id,
        )
        body = dict(serializers.HelperCaseSerializer(case).data)
        body["duplicate"] = not created
        return ok(body, status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class CaseDetailAPI(_Base):
    def get(self, request, case_id):
        case = self.case_for(request, case_id)
        if case is None:
            return self.nothing()
        if not policy.is_family_side(request.user, case):
            return ok(serializers.HelperCaseSerializer(case).data)
        return self.family_view(request, case)


class _FamilyAction(_Base):
    throttle_classes = [ContributionThrottle]

    def with_text(self, request, case_id, action):
        case = self.family_case(request, case_id)
        if case is None:
            return self.nothing()
        serializer = serializers.TextSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        return self.run(lambda: action(case, serializer.validated_data["body"]) and self.family_view(request, case))


class CaseInfoAPI(_FamilyAction):
    def post(self, request, case_id):
        return self.with_text(
            request, case_id,
            lambda case, body: services.add_note(case, request.user, CaseNote.Kind.FAMILY_INFO, body),
        )


class CaseCorrectionAPI(_FamilyAction):
    def post(self, request, case_id):
        return self.with_text(
            request, case_id,
            lambda case, body: services.add_note(case, request.user, CaseNote.Kind.CORRECTION, body),
        )


class CaseCancelAPI(_FamilyAction):
    def post(self, request, case_id):
        case = self.case_for(request, case_id)
        if case is None or case.reporter_id != request.user.pk or case.reporter_role != "pilgrim":
            return self.nothing()
        reason = str(request.data.get("reason") or "")[:500]
        return self.run(lambda: self.family_view(request, services.cancel_report(case, request.user, reason)))


class CaseConfirmReunionAPI(_FamilyAction):
    def post(self, request, case_id):
        case = self.family_case(request, case_id)
        if case is None:
            return self.nothing()
        return self.run(lambda: self.family_view(request, services.family_confirm_reunion(case, request.user)))


class CaseSightingListAPI(_Base):
    """Anyone with access can add one. It waits for staff review before the
    family sees it, and is labelled as community-reported."""

    throttle_classes = [ContributionThrottle]

    def post(self, request, case_id):
        case = self.case_for(request, case_id)
        if case is None:
            return self.nothing()
        serializer = serializers.SightingInputSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        role = policy.helper_role(request.user) or "pilgrim"
        sighting = services.add_sighting(case, request.user, role, serializer.validated_data)
        return ok({"id": str(sighting.pk), "review": sighting.review}, status.HTTP_201_CREATED)


class AttachmentListAPI(_Base):
    parser_classes = [MultiPartParser]
    throttle_classes = [ContributionThrottle]

    def post(self, request, case_id):
        case = self.case_for(request, case_id)
        if case is None:
            return self.nothing()
        upload = request.FILES.get("photo")
        if upload is None or upload.size > CaseAttachment.MAX_BYTES:
            return error({"photo": ["Choose a photo under 6 MB."]})
        client_id = request.data.get("client_id") or None
        return self.run(lambda: ok(
            {"id": str(services.add_attachment(case, request.user, upload.read(), client_id).pk)},
            status.HTTP_201_CREATED,
        ))


class AttachmentDetailAPI(_Base):
    """Never a public URL: every read passes this check, and isn't cached."""

    def get(self, request, attachment_id):
        attachment = get_object_or_404(CaseAttachment.objects.select_related("case__member"), pk=attachment_id)
        if not policy.can_view(request.user, attachment.case):
            return self.nothing()
        if policy.can_operate(request.user, attachment.case):
            services.audit(attachment.case, request.user, "attachment_viewed")
        response = HttpResponse(bytes(attachment.data), content_type=attachment.content_type)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class _Ops(_Base):
    def role_allowed(self, request):
        return policy.helper_role(request.user) in (policy.STAFF, policy.HELP_DESK)

    def ops_case(self, request, case_id):
        case = get_object_or_404(LostFoundCase.objects.select_related("member__user"), pk=case_id)
        return case if policy.can_operate(request.user, case) else None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.allowed = self.role_allowed(request)

    def ops_view(self, request, case, code=status.HTTP_200_OK):
        return ok(serializers.OpsCaseSerializer(case, context={"request": request}).data, code)

    def parsed(self, serializer_class, request):
        serializer = serializer_class(data=request.data)
        return (serializer.validated_data, None) if serializer.is_valid() else (None, error(serializer.errors))


class OpsCaseListAPI(_Ops):
    def get(self, request):
        if not self.allowed:
            return forbidden()
        cases = policy.ops_scope(request.user, LostFoundCase.objects.select_related("member")).annotate(
            open_lost=Count("matches_as_lost", filter=Q(matches_as_lost__state__in=OPEN_MATCHES), distinct=True),
            open_found=Count("matches_as_found", filter=Q(matches_as_found__state__in=OPEN_MATCHES), distinct=True),
        ).annotate(open_match_count=F("open_lost") + F("open_found"))
        if request.query_params.get("unassigned") == "true":
            cases = cases.filter(assigned_to__isnull=True, status__in=ACTIVE_STATUSES)
        case_type = request.query_params.get("type")
        state = request.query_params.get("status")
        query = request.query_params.get("q", "").strip()
        if case_type:
            cases = cases.filter(case_type=case_type)
        if state:
            cases = cases.filter(status=state)
        if query:
            cases = cases.filter(reference__iexact=query)
        if request.query_params.get("mine") == "true":
            cases = cases.filter(assigned_to=request.user)
        page = Paginator(cases, 25).get_page(request.query_params.get("page") or 1)
        return ok({
            "results": serializers.OpsListSerializer(page.object_list, many=True, context={"request": request}).data,
            "count": page.paginator.count,
            "has_next": page.has_next(),
        })


class OpsCaseDetailAPI(_Ops):
    def get(self, request, case_id):
        if not self.allowed:
            return forbidden()
        case = self.ops_case(request, case_id)
        if case is None:
            return self.nothing()
        services.audit(case, request.user, "case_viewed")
        return self.ops_view(request, case)


class OpsStatusAPI(_Ops):
    def post(self, request, case_id):
        if not self.allowed:
            return forbidden()
        case = self.ops_case(request, case_id)
        if case is None:
            return self.nothing()
        data, problem = self.parsed(serializers.StatusChangeSerializer, request)
        if problem:
            return problem
        return self.run(lambda: self.ops_view(
            request, services.change_status(case, data["status"], request.user, data["reason"]),
        ))


class OpsAssignAPI(_Ops):
    def post(self, request, case_id):
        if not policy.is_staff(request.user):
            return forbidden()
        case = self.ops_case(request, case_id)
        if case is None:
            return self.nothing()
        if case.assigned_to_id != request.user.pk:
            from apps.operations import services as operations

            try:
                operations.assign(case, request.user, request.user)
            except operations.OperationsError as refused:
                return error({refused.field: [refused.message]}, status.HTTP_409_CONFLICT)
        return self.ops_view(request, case)


class OpsNoteAPI(_Ops):
    def post(self, request, case_id):
        if not self.allowed:
            return forbidden()
        case = self.ops_case(request, case_id)
        if case is None:
            return self.nothing()
        data, problem = self.parsed(serializers.NoteSerializer, request)
        if problem:
            return problem
        services.add_note(case, request.user, data["kind"], data["body"])
        return self.ops_view(request, case, status.HTTP_201_CREATED)


class OpsContactAPI(_Ops):
    """The reporter's number, for someone working the case. Every read is
    audited, and it's never part of a case response."""

    def post(self, request, case_id):
        if not self.allowed:
            return forbidden()
        case = self.ops_case(request, case_id)
        if case is None:
            return self.nothing()
        services.audit(case, request.user, "contact_revealed")
        reporter = case.reporter
        response = ok({
            "phone": reporter.phone_number if reporter else None,
            "preferred_contact": case.preferred_contact,
        })
        response["Cache-Control"] = "no-store"
        return response


class OpsFindMatchesAPI(_Ops):
    def post(self, request, case_id):
        if not self.allowed:
            return forbidden()
        case = self.ops_case(request, case_id)
        if case is None:
            return self.nothing()
        matching.find_matches(case)
        return self.ops_view(request, case)


class OpsVerifyAPI(_Ops):
    def post(self, request, case_id):
        if not self.allowed:
            return forbidden()
        case = self.ops_case(request, case_id)
        if case is None:
            return self.nothing()
        data, problem = self.parsed(serializers.CheckSerializer, request)
        if problem:
            return problem
        return self.run(lambda: self.ops_view(request, services.verify_case(case, request.user, **data)))


class OpsReuniteAPI(_Ops):
    def post(self, request, case_id):
        if not self.allowed:
            return forbidden()
        case = self.ops_case(request, case_id)
        if case is None:
            return self.nothing()
        data, problem = self.parsed(serializers.ReunionSerializer, request)
        if problem:
            return problem
        return self.run(lambda: self.ops_view(request, services.record_reunion(case, request.user, **data)))


class OpsSightingReviewAPI(_Ops):
    def post(self, request, sighting_id):
        if not self.allowed:
            return forbidden()
        sighting = get_object_or_404(CaseSighting.objects.select_related("case"), pk=sighting_id)
        if not policy.can_operate(request.user, sighting.case):
            return self.nothing()
        services.review_sighting(
            sighting, request.user, approve=request.data.get("approve") is True,
            verified=request.data.get("verified") is True,
        )
        return self.ops_view(request, sighting.case)


class OpsMatchListAPI(_Ops):
    def get(self, request):
        if not policy.is_staff(request.user):
            return forbidden()
        rows = CaseMatch.objects.select_related(
            "lost_case__ai_extraction", "found_case__ai_extraction",
        ).filter(
            state=request.query_params.get("state") or "suggested",
            lost_case__in=policy.ops_scope(request.user, LostFoundCase.objects.all()),
        )
        page = Paginator(rows, 25).get_page(request.query_params.get("page") or 1)
        return ok({
            "results": serializers.MatchSerializer(page.object_list, many=True).data,
            "count": page.paginator.count,
            "has_next": page.has_next(),
        })


class _OpsMatch(_Ops):
    def match(self, match_id):
        match = get_object_or_404(CaseMatch.objects.select_related("lost_case"), pk=match_id)
        if not policy.can_operate(self.request.user, match.lost_case):
            raise Http404
        return match

    def done(self, match):
        return ok(serializers.MatchSerializer(match).data)


class OpsMatchApproveAPI(_OpsMatch):
    def post(self, request, match_id):
        if not policy.is_staff(request.user):
            return forbidden()
        notify = request.data.get("notify_family") is True
        return self.run(lambda: self.done(
            services.approve_match(self.match(match_id), request.user, notify_family=notify),
        ))


class OpsMatchDismissAPI(_OpsMatch):
    def post(self, request, match_id):
        if not policy.is_staff(request.user):
            return forbidden()
        reason = str(request.data.get("reason") or "")[:500]
        return self.run(lambda: self.done(services.dismiss_match(self.match(match_id), request.user, reason)))


class OpsMatchConfirmAPI(_OpsMatch):
    def post(self, request, match_id):
        if not policy.is_staff(request.user):
            return forbidden()
        data, problem = self.parsed(serializers.CheckSerializer, request)
        if problem:
            return problem
        return self.run(lambda: self.done(services.confirm_match(self.match(match_id), request.user, **data)))


class _OpsAI(_Ops):
    """Optional help. Every route answers without touching the case, and a failure
    is a clear 503 that staff can ignore."""

    def unavailable(self):
        return error(
            {"detail": "AI assistance is unavailable. You can carry on without it.", "code": "ai_unavailable"},
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def attempt(self, action):
        try:
            return action()
        except ai.AIUnavailable:
            return self.unavailable()
        except ai.NothingToProcess:
            return error({"detail": "There's no text here to work on."})

    def operator_case(self, request, case_id):
        return self.ops_case(request, case_id) if self.allowed else None

    def reader_case(self, request, case_id):
        """Staff with access, or the volunteer assigned to this case."""
        case = get_object_or_404(LostFoundCase, pk=case_id)
        if self.allowed and policy.can_operate(request.user, case):
            return case, True
        return (case, False) if policy.is_assigned_volunteer(request.user, case) else (None, False)


class OpsCaseAIAPI(_OpsAI):
    def get(self, request, case_id):
        case, operator = self.reader_case(request, case_id)
        if case is None:
            return self.nothing()
        rows = case.translations.all()
        if not operator:
            rows = rows.filter(source_type="field", source_ref__in=ai.VOLUNTEER_FIELDS)
        extraction = getattr(case, "ai_extraction", None) if operator else None
        return ok({
            "available": ai.is_available(),
            "translations": serializers.TranslationSerializer(rows, many=True).data,
            "extraction": serializers.ExtractionSerializer(extraction).data if extraction else None,
        })


class OpsTranslateAPI(_OpsAI):
    throttle_classes = [AIThrottle]

    def post(self, request, case_id):
        case, operator = self.reader_case(request, case_id)
        if case is None:
            return self.nothing()
        data, problem = self.parsed(serializers.TranslateSerializer, request)
        if problem:
            return problem
        if not operator and (data["source_type"] != "field" or data["source_ref"] not in ai.VOLUNTEER_FIELDS):
            return self.nothing()
        return self.attempt(lambda: ok(serializers.TranslationSerializer(ai.translate(
            case, data["source_type"], data["source_ref"], data["target_language"], request.user,
        )).data))


class OpsTranslationReviewAPI(_OpsAI):
    def post(self, request, translation_id):
        row = get_object_or_404(CaseTranslation.objects.select_related("case"), pk=translation_id)
        if not self.allowed or not policy.can_operate(request.user, row.case):
            return self.nothing()
        data, problem = self.parsed(serializers.TranslationReviewSerializer, request)
        if problem:
            return problem
        return ok(serializers.TranslationSerializer(ai.review_translation(row, data["text"], request.user)).data)


class OpsExtractAPI(_OpsAI):
    throttle_classes = [AIThrottle]

    def post(self, request, case_id):
        case = self.operator_case(request, case_id)
        if case is None:
            return self.nothing()
        return self.attempt(lambda: ok(serializers.ExtractionSerializer(ai.extract(case, request.user)).data))


class OpsExtractionReviewAPI(_OpsAI):
    def post(self, request, case_id):
        case = self.operator_case(request, case_id)
        extraction = getattr(case, "ai_extraction", None) if case else None
        if extraction is None:
            return self.nothing()
        data, problem = self.parsed(serializers.ExtractionReviewSerializer, request)
        if problem:
            return problem
        reviewed = ai.review_extraction(extraction, data["accept"], data["corrections"], request.user)
        matching.find_matches(case)
        return ok(serializers.ExtractionSerializer(reviewed).data)
