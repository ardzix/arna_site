from django.urls import path, include
from rest_framework.routers import DefaultRouter
from storage.views import MediaReferenceViewSet

router = DefaultRouter()
router.register(r'files', MediaReferenceViewSet, basename='files')

urlpatterns = [
    path('', include(router.urls)),
]
