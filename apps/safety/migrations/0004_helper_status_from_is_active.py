"""Helpers who were already switched off stay off. Everyone else stays active."""

from django.db import migrations


def carry_over(apps, schema_editor):
    helper = apps.get_model("safety", "SafetyHelper")
    helper.objects.filter(is_active=False).update(status="deactivated")


class Migration(migrations.Migration):
    dependencies = [("safety", "0003_safetyhelper_availability_and_more")]

    operations = [migrations.RunPython(carry_over, migrations.RunPython.noop)]
