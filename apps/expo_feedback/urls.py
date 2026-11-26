from django.urls import path
from .views import (
    EntryFormStartSessionView,
    FeedbackSubmitView,
    SessionDetailView,
    SessionListView,
    FeedbackSummaryView,
    ClaimTrialView,
    ClaimTrialDetailView,
    IndustryChoicesView,
    ExpoVoiceAgentListCreateView,
    ExpoVoiceAgentDetailView,
)

app_name = 'expo_feedback'

urlpatterns = [
    path('entry/', EntryFormStartSessionView.as_view(), name='entry-start'),
    path('feedback/', FeedbackSubmitView.as_view(), name='feedback-submit'),
    path('sessions/', SessionListView.as_view(), name='session-list'),
    path('sessions/<str:session_id>/', SessionDetailView.as_view(), name='session-detail'),
    path('sessions/<str:session_id>/feedback/', FeedbackSubmitView.as_view(), name='session-feedback-submit'),
    path('summary/', FeedbackSummaryView.as_view(), name='feedback-summary'),
    path('industries/', IndustryChoicesView.as_view(), name='industries'),
    path('claim_trial/', ClaimTrialView.as_view(), name='claim-trial'),
    path('claim_trial/industries/', IndustryChoicesView.as_view(), name='claim-trial-industries'),
    path('claim_trial/<str:claim_id>/', ClaimTrialDetailView.as_view(), name='claim-trial-detail'),
    path('agents/', ExpoVoiceAgentListCreateView.as_view(), name='agent-list-create'),
    path('agents/<str:agent_id>/', ExpoVoiceAgentDetailView.as_view(), name='agent-detail'),
]
