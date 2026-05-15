from django.urls import path
from ai_helper.views import (
    AITemplateOptionListView,
    AISessionListCreateView,
    AISessionDetailView,
    AISessionMessageCreateView,
    AISessionGenerateView,
    AISessionDraftListView,
    AISessionPublishView,
    AISessionFEGuideView,
    AISessionTemplateDraftView,
    AISessionSiteContentDraftView,
    AIJobStatusView,
)

urlpatterns = [
    path('template-options/', AITemplateOptionListView.as_view(), name='ai-template-options'),
    path('sessions/', AISessionListCreateView.as_view(), name='ai-session-list-create'),
    path('sessions/<uuid:session_id>/', AISessionDetailView.as_view(), name='ai-session-detail'),
    path('sessions/<uuid:session_id>/messages/', AISessionMessageCreateView.as_view(), name='ai-session-message-create'),
    path('sessions/<uuid:session_id>/generate/', AISessionGenerateView.as_view(), name='ai-session-generate'),
    path('sessions/<uuid:session_id>/drafts/', AISessionDraftListView.as_view(), name='ai-session-drafts'),
    path('sessions/<uuid:session_id>/template-draft/', AISessionTemplateDraftView.as_view(), name='ai-session-template-draft'),
    path('sessions/<uuid:session_id>/site-content-draft/', AISessionSiteContentDraftView.as_view(), name='ai-session-site-content-draft'),
    path('sessions/<uuid:session_id>/publish/', AISessionPublishView.as_view(), name='ai-session-publish'),
    path('sessions/<uuid:session_id>/fe-guide/', AISessionFEGuideView.as_view(), name='ai-session-fe-guide'),
    path('jobs/<uuid:job_id>/status/', AIJobStatusView.as_view(), name='ai-job-status'),
]
