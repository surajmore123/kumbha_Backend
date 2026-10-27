from django.db import models
import uuid
from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager,
)

class UserManager(BaseUserManager):
    def create_user(self, email=None, phone_number=None, password=None, **extra_fields):
        if not phone_number:
            raise ValueError("Phone number is required")

        if email:
            email = self.normalize_email(email)

        user = self.model(
            email=email,
            phone_number=phone_number,
            **extra_fields,
        )
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        return self.create_user(
            email=email,
            phone_number=phone_number,
            password=password,
            **extra_fields,
        )
    

class User(AbstractBaseUser,PermissionsMixin):
    user_id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,unique=True)

    full_Name = models.CharField(max_length=255,null=True,blank=True)
    email = models.EmailField(max_length=255,null=True,blank=True)
    # Stored as "+91XXXXXXXXXX". Optional: website users who sign in with Google may have no phone.
    phone_number = models.CharField(max_length=20,unique=True,null=True,blank=True)
    profile_pic_url = models.TextField(null=True,blank=True)
    otp_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  
    # Website (kumbhapath.in) fields; the website API lives in apps/website.
    role = models.CharField(max_length=16,choices=[("user","User"),("partner","Partner"),("admin","Admin")],default="user")
    preferred_language = models.CharField(max_length=12,default="en")

 
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    objects = UserManager()

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"
        constraints = [
            # enforce unique email only when not null
            models.UniqueConstraint(
                fields=["email"],
                name="users_unique_email_when_present",
                condition=Q(email__isnull=False),
            )
        ]

    def __str__(self):
        identifier = self.email or self.phone_number
        return f"{identifier} ({self.user_id})"
    
class Otp(models.Model):
    otp_id = models.BigAutoField(primary_key=True, unique=True)

    # FK -> users.user_id (UUID)
    user = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="otps",
    )

    otp_code = models.CharField(max_length=6)
    expiry_time = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    is_del = models.SmallIntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "otps"
        verbose_name = "OTP"
        verbose_name_plural = "OTPs"
        indexes = [
            models.Index(fields=["user", "otp_code", "is_used"]),
        ]

    def __str__(self):
        return f"OTP for {self.user.email or self.user.phone_number}"

    def is_expired(self):
        return timezone.now() > self.expiry_time

    @classmethod
    def create_static_otp(cls, user):
        """Helper for testing/dev; creates 111111 OTP valid for 5 minutes."""
        return cls.objects.create(
            user=user,
            otp_code="111111",
            expiry_time=timezone.now() + timedelta(minutes=5),
        )





class FCMDevice(models.Model):
    device_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="fcm_devices"
    )

    token = models.TextField(unique=True)
    device_type = models.CharField(
        max_length=10,
        choices=[("ANDROID", "Android"), ("IOS", "iOS"), ("WEB", "Web")]
    )

    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(auto_now=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fcm_devices"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.device_type}"




class NotificationPreference(models.Model):
    """
    Which push notifications a user wants. A missing row means "all on".
    Checked by utils.push_notifications before anything is sent.
    """

    CATEGORIES = (
        "event_reminders",   # before an event the user follows
        "event_updates",     # a followed event changed or was withdrawn
        "new_events",        # a new event was published
        "crowd_alerts",      # crowd level rising in a zone
        "safety_alerts",     # serious incidents (HIGH / CRITICAL)
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="notification_preference",
    )
    event_reminders = models.BooleanField(default=True)
    event_updates = models.BooleanField(default=True)
    new_events = models.BooleanField(default=True)
    crowd_alerts = models.BooleanField(default=True)
    safety_alerts = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notification_preferences"

    def __str__(self):
        return f"Notification preferences of {self.user_id}"
