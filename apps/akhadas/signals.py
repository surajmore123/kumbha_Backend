"""Editing content in admin refreshes the public API's cache straight away."""

from django.db.models.signals import m2m_changed, post_delete, post_save

from apps.akhadas import cache as content_cache, models


def _changed(sender, **kwargs):
    content_cache.invalidate()


_TRACKED = [
    models.ContentSource, models.Tradition, models.TraditionTranslation,
    models.SpiritualTitle, models.SpiritualTitleTranslation, models.Akhada,
    models.AkhadaTranslation, models.SadhuProfile, models.SadhuProfileTranslation,
    models.SpiritualArticle, models.SpiritualArticleTranslation,
    models.AkhadaActivity, models.AkhadaActivityTranslation,
]
_RELATIONS = [
    models.Akhada.sources.through, models.SadhuProfile.sources.through,
    models.SpiritualArticle.sources.through, models.AkhadaActivity.sources.through,
    models.Tradition.sources.through, models.SpiritualTitle.sources.through,
    models.SpiritualTitle.traditions.through, models.SpiritualArticle.related_akhadas.through,
    models.SpiritualArticle.related_saints.through, models.AkhadaActivity.akhadas.through,
]

for model in _TRACKED:
    post_save.connect(_changed, sender=model, dispatch_uid=f"akhadas_save_{model.__name__}")
    post_delete.connect(_changed, sender=model, dispatch_uid=f"akhadas_delete_{model.__name__}")
for through in _RELATIONS:
    m2m_changed.connect(_changed, sender=through, dispatch_uid=f"akhadas_m2m_{through.__name__}")
