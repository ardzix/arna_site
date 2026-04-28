from django.urls import path
from ai_helper.views import (
    AISessionListCreateView,
    AISessionDetailView,
    AISessionMessageCreateView,
    AISessionGenerateView,
    AISessionDraftListView,
    AISessionPublishView,
    AISessionFEGuideView,
)

urlpatterns = [
    path('sessions/', AISessionListCreateView.as_view(), name='ai-session-list-create'),
    path('sessions/<uuid:session_id>/', AISessionDetailView.as_view(), name='ai-session-detail'),
    path('sessions/<uuid:session_id>/messages/', AISessionMessageCreateView.as_view(), name='ai-session-message-create'),
    path('sessions/<uuid:session_id>/generate/', AISessionGenerateView.as_view(), name='ai-session-generate'),
    path('sessions/<uuid:session_id>/drafts/', AISessionDraftListView.as_view(), name='ai-session-drafts'),
    path('sessions/<uuid:session_id>/publish/', AISessionPublishView.as_view(), name='ai-session-publish'),
    path('sessions/<uuid:session_id>/fe-guide/', AISessionFEGuideView.as_view(), name='ai-session-fe-guide'),
]
