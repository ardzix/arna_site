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
    path("<uuid:pk>/",        file_detail, name="file-detail"),
    path("<uuid:pk>/presign/",   MediaReferenceViewSet.as_view({'post': 'presign'}),      name="file-presign"),
    path("<uuid:pk>/complete/",  MediaReferenceViewSet.as_view({'post': 'complete_upload'}), name="file-complete"),
    path("<uuid:pk>/abort/",     MediaReferenceViewSet.as_view({'post': 'abort'}),         name="file-abort"),
]
