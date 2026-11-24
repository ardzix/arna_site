from django.urls import include, path
urlpatterns = [path("domains/", include("core.domain_urls"))]
