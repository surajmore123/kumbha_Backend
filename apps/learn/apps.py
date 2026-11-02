from django.apps import AppConfig


class LearnConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.learn"

    def ready(self):
        from django.db.models.signals import m2m_changed, post_delete, post_save

        from apps.akhadas import cache as content_cache
        from apps.learn import models

        def changed(sender, **kwargs):
            content_cache.invalidate()

        for model in (
            models.LearningSection, models.LearningSectionTranslation, models.LearningArticle,
            models.LearningArticleTranslation, models.LearningImage, models.GlossaryTerm,
            models.GlossaryTermTranslation,
        ):
            post_save.connect(changed, sender=model, weak=False, dispatch_uid=f"learn_save_{model.__name__}")
            post_delete.connect(changed, sender=model, weak=False, dispatch_uid=f"learn_delete_{model.__name__}")
        for through in (
            models.LearningArticle.sources.through, models.LearningArticle.related_articles.through,
            models.LearningArticle.related_akhadas.through, models.LearningArticle.related_temples.through,
            models.GlossaryTerm.related_articles.through, models.GlossaryTerm.related_akhadas.through,
            models.GlossaryTerm.related_temples.through,
        ):
            m2m_changed.connect(changed, sender=through, weak=False, dispatch_uid=f"learn_m2m_{through.__name__}")
