"""Module for storage.urls."""
from django.urls import path

from storage.views import MediaReferenceViewSet

files = MediaReferenceViewSet.as_view({
    'get':  'list',
    'post': 'create',
})
file_detail = MediaReferenceViewSet.as_view({
    'get':    'retrieve',
    'patch':  'partial_update',
    'delete': 'destroy',
})

urlpatterns = [
    path("",                  files,       name="file-list"),
    path("init-upload/",      MediaReferenceViewSet.as_view({'post': 'init_upload'}),   name="file-init-upload"),
    path("fm/<uuid:file_id>/", MediaReferenceViewSet.as_view({'get': 'fm_read'}), name="file-fm-read"),
    path("fm/<uuid:file_id>/presign/", MediaReferenceViewSet.as_view({'post': 'fm_presign'}), name="file-fm-presign"),
    path("fm/<uuid:file_id>/complete/", MediaReferenceViewSet.as_view({'post': 'fm_complete'}), name="file-fm-complete"),
    path("fm/<uuid:file_id>/abort/", MediaReferenceViewSet.as_view({'post': 'fm_abort'}), name="file-fm-abort"),
    path("<uuid:pk>/",        file_detail, name="file-detail"),
    path("<uuid:pk>/presign/",   MediaReferenceViewSet.as_view({'post': 'presign'}),      name="file-presign"),
    path("<uuid:pk>/complete/",  MediaReferenceViewSet.as_view({'post': 'complete_upload'}), name="file-complete"),
    path("<uuid:pk>/abort/",     MediaReferenceViewSet.as_view({'post': 'abort'}),         name="file-abort"),
]
