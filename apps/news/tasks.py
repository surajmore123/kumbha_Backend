from celery import shared_task

from apps.news.sync import sync_all


@shared_task
def sync_news_sources():
    """Scheduled every 6 hours by `manage.py setup_news_sync`. Each source also
    enforces its own minimum interval, and backs off after failures."""
    return len(sync_all())
