from django.db import models
from apps.authentication.models import User

class BaseModel(models.Model):
    """
    Common base model used across all tables.
    Contains:
    - del_flag (soft delete)
    - created_at
    - updated_at
    - user_id_updated_by
    """

    del_flag = models.SmallIntegerField(default=0, help_text="Soft delete flag")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    user_id_updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_%(class)s_records"
    )

    class Meta:
        abstract = True