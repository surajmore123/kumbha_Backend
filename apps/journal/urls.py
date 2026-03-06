from django.urls import path
from .views import AIPromptView, AIReflectionView, JournalEntryCreateView, JournalEntryListView,JournalEntryDetailView

app_name = 'journal'


urlpatterns = [
     path('ai-reflection/', AIReflectionView.as_view(), name='ai-reflection'),
     path("ai-prompt/", AIPromptView.as_view(), name="ai-prompt"),
     path("create-entry/", JournalEntryCreateView.as_view(), name="create-entry"),
     path("entries/", JournalEntryListView.as_view(), name="journal-entries"),
     path("entries/<int:pk>/", JournalEntryDetailView.as_view()),
     path("entries/<int:pk>/", JournalEntryDetailView.as_view()),


]