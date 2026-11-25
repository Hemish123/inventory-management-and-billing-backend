from django.urls import path
from .views import (
    EntryFormStartSessionView,
    FeedbackSubmitView,
    SessionDetailView,
    SessionListView,
    FeedbackSummaryView,
)

app_name = 'expo_feedback'

urlpatterns = [
    path('entry/', EntryFormStartSessionView.as_view(), name='entry-start'),
    path('feedback/', FeedbackSubmitView.as_view(), name='feedback-submit'),
    path('sessions/', SessionListView.as_view(), name='session-list'),
    path('sessions/<str:session_id>/', SessionDetailView.as_view(), name='session-detail'),
    path('sessions/<str:session_id>/feedback/', FeedbackSubmitView.as_view(), name='session-feedback-submit'),
    path('summary/', FeedbackSummaryView.as_view(), name='feedback-summary'),
]
