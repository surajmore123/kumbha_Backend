"""
Where administrators run volunteer accounts. Roles live on `SafetyHelper`, so the
existing admin for it is extended here rather than a second one being added.

A volunteer never gets `is_staff`, so none of this is reachable by them. Setup
codes are shown once and stored hashed, and phone numbers are masked in lists.
"""

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.utils.html import format_html

from apps.crowd.models.Zone import Zone
from apps.operations import services
from apps.operations.models import CaseAssignment, OperationsAudit
from apps.operations.services import OperationsError
from apps.operations.views import _phone
from apps.safety.models import SafetyHelper

admin.site.unregister(SafetyHelper)

_COLOURS = {"pending": "#b26a00", "active": "#1b7f3b", "suspended": "#b3261e", "deactivated": "#666666"}


class VolunteerCreateForm(forms.ModelForm):
    """Makes the person's account, or attaches to the one they already use."""

    phone_number = forms.CharField(max_length=15, help_text="Their own 10-digit mobile number.")
    full_name = forms.CharField(max_length=255)

    class Meta:
        model = SafetyHelper
        fields = ("role", "zones")

    def clean_phone_number(self):
        phone = _phone(self.cleaned_data["phone_number"])
        if phone is None:
            raise forms.ValidationError("Enter a valid 10-digit Indian mobile number.")
        user = get_user_model().objects.filter(phone_number=phone).first()
        if user is not None and (user.is_staff or user.is_superuser):
            raise forms.ValidationError("This account is an administrator.")
        if SafetyHelper.objects.filter(user__phone_number=phone).exists():
            raise forms.ValidationError("This person already has an operations account.")
        return phone


class VolunteerEditForm(forms.ModelForm):
    class Meta:
        model = SafetyHelper
        fields = ("role", "zones", "expires_at")


class _ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SafetyHelper)
class VolunteerAdmin(admin.ModelAdmin):
    list_display = (
        "person", "masked_phone", "role", "status_tag", "availability", "zone_list", "open_cases", "credential_set_at",
    )
    list_filter = ("role", "status", "availability", "zones")
    search_fields = ("user__full_Name", "user__phone_number")
    filter_horizontal = ("zones",)
    readonly_fields = (
        "person", "masked_phone", "status_tag", "availability", "open_cases", "cases_completed", "credential_set_at",
        "activity", "approved_by", "created_at",
    )
    actions = ("activate", "suspend", "deactivate", "reset_credentials", "sign_out")

    def get_form(self, request, obj=None, **kwargs):
        kwargs["form"] = VolunteerEditForm if obj else VolunteerCreateForm
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("phone_number", "full_name", "role", "zones")
        return (
            "person", "masked_phone", "role", "zones", "status_tag", "availability", "expires_at", "open_cases",
            "cases_completed", "credential_set_at", "activity", "approved_by", "created_at",
        )

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields if obj else ()

    def has_delete_permission(self, request, obj=None):
        return False  # Deactivate instead: the audit trail must survive.

    @admin.display(description="Name")
    def person(self, obj):
        return obj.user.full_Name or "—"

    @admin.display(description="Phone")
    def masked_phone(self, obj):
        phone = obj.user.phone_number or ""
        return f"••••••{phone[-4:]}" if phone else "—"

    @admin.display(description="Status")
    def status_tag(self, obj):
        return format_html(
            '<strong style="color:{}">{}</strong>', _COLOURS.get(obj.status, "#666666"), obj.get_status_display(),
        )

    @admin.display(description="Zones")
    def zone_list(self, obj):
        return ", ".join(z.name for z in obj.zones.all()) or "—"

    @admin.display(description="Open cases")
    def open_cases(self, obj):
        return services.workload(obj.user)

    @admin.display(description="Completed cases")
    def cases_completed(self, obj):
        return CaseAssignment.objects.filter(volunteer=obj.user, status=CaseAssignment.Status.COMPLETED).count()

    @admin.display(description="Recent activity")
    def activity(self, obj):
        rows = OperationsAudit.objects.filter(target=obj.user)[:15]
        return format_html(
            "{}", "; ".join(f"{r.created_at:%d %b %H:%M} {r.action}" for r in rows) or "—",
        )

    def _show_code(self, request, helper, code):
        name = helper.user.full_Name or "the volunteer"
        self.message_user(
            request,
            f"Setup code for {name}: {code} . It's shown only this once. Give it to them in person; it expires soon.",
            messages.WARNING,
        )

    def save_model(self, request, obj, form, change):
        if change:
            before = SafetyHelper.objects.get(pk=obj.pk)
            super().save_model(request, obj, form, change)
            if before.role != obj.role:
                services.record(request.user, obj.user, "role_changed", previous=before.role, role=obj.role)
            return
        helper, code = services.create_volunteer(
            phone_number=form.cleaned_data["phone_number"], full_name=form.cleaned_data["full_name"],
            role=form.cleaned_data["role"], zones=form.cleaned_data["zones"], by=request.user,
        )
        obj.pk = helper.pk
        obj.user = helper.user
        self._show_code(request, helper, code)

    def save_related(self, request, form, formsets, change):
        if not change:
            return  # `create_volunteer` already set the zones.
        before = set(form.instance.zones.values_list("pk", flat=True))
        super().save_related(request, form, formsets, change)
        after = set(form.instance.zones.values_list("pk", flat=True))
        if before != after:
            services.record(request.user, form.instance.user, "zones_changed", zones=[str(z) for z in after])

    def _set(self, request, queryset, status):
        for helper in queryset.select_related("user"):
            services.set_status(helper, status, request.user)
        self.message_user(request, f"{queryset.count()} updated.")

    @admin.action(description="Activate")
    def activate(self, request, queryset):
        self._set(request, queryset, SafetyHelper.Status.ACTIVE)

    @admin.action(description="Suspend")
    def suspend(self, request, queryset):
        self._set(request, queryset, SafetyHelper.Status.SUSPENDED)

    @admin.action(description="Deactivate")
    def deactivate(self, request, queryset):
        self._set(request, queryset, SafetyHelper.Status.DEACTIVATED)

    @admin.action(description="Reset credentials (one volunteer at a time)")
    def reset_credentials(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Choose one volunteer: the code is shown once.", messages.ERROR)
            return
        helper = queryset.select_related("user").first()
        self._show_code(request, helper, services.issue_setup_code(helper, request.user))

    @admin.action(description="Sign out on all devices")
    def sign_out(self, request, queryset):
        for helper in queryset.select_related("user"):
            services.sign_out_everywhere(helper.user)
            services.record(request.user, helper.user, "signed_out")
        self.message_user(request, f"{queryset.count()} signed out.")


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = CaseAssignment
        fields = ("case", "volunteer", "notes")

    def clean(self):
        data = super().clean()
        case, volunteer = data.get("case"), data.get("volunteer")
        if case and volunteer:
            try:
                services.check_assignment(case, volunteer)
            except OperationsError as problem:
                raise forms.ValidationError(problem.message) from problem
        return data


@admin.register(CaseAssignment)
class CaseAssignmentAdmin(admin.ModelAdmin):
    """Assigning here goes through the same checks as the app. Existing rows are
    history, so they can't be edited."""

    form = AssignmentForm
    list_display = ("reference", "volunteer_name", "status", "assigned_by_name", "assigned_at", "completed_at")
    list_filter = ("status", "case__zone")
    search_fields = ("case__reference",)
    raw_id_fields = ("case", "volunteer")
    list_select_related = ("case", "volunteer", "assigned_by")

    @admin.display(description="Case")
    def reference(self, obj):
        return obj.case.reference

    @admin.display(description="Volunteer")
    def volunteer_name(self, obj):
        return obj.volunteer.full_Name or "—"

    @admin.display(description="Assigned by")
    def assigned_by_name(self, obj):
        return obj.assigned_by.full_Name if obj.assigned_by else "—"

    def has_change_permission(self, request, obj=None):
        return obj is None and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.pk = services.assign(obj.case, obj.volunteer, request.user, obj.notes).pk


@admin.register(OperationsAudit)
class OperationsAuditAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor_name", "target_name")
    list_filter = ("action",)
    date_hierarchy = "created_at"
    fields = ("created_at", "action", "actor_name", "target_name", "details")
    readonly_fields = fields

    @admin.display(description="By")
    def actor_name(self, obj):
        return obj.actor.full_Name if obj.actor else "System"

    @admin.display(description="For")
    def target_name(self, obj):
        return obj.target.full_Name if obj.target else "—"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


_ = Zone
