import os
from celery import Celery
from celery.signals import task_failure

from utils.observability import log_task_failure

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.local"
)

app = Celery("kumbha_Backend")

app.config_from_object(
    "django.conf:settings",
    namespace="CELERY"
)

app.autodiscover_tasks()

task_failure.connect(log_task_failure)

app.conf.beat_scheduler = "django_celery_beat.schedulers:DatabaseScheduler"