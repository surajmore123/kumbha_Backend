from django.apps import AppConfig


class NewsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.news"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from apps.akhadas import cache as content_cache
        from apps.news import models

        def changed(sender, **kwargs):
            content_cache.invalidate()

        for model in (
            models.NewsArticle, models.NewsArticleTranslation, models.NewsCategory,
            models.NewsCategoryTranslation, models.NewsSource,
        ):
            post_save.connect(changed, sender=model, weak=False, dispatch_uid=f"news_save_{model.__name__}")
            post_delete.connect(changed, sender=model, weak=False, dispatch_uid=f"news_delete_{model.__name__}")
