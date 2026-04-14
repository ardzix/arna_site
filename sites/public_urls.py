from django.urls import path
from sites.views import PublicSiteView

urlpatterns = [
    path("site/",          PublicSiteView.as_view(), name="public-site"),
    path("site/<slug:slug>/", PublicSiteView.as_view(), name="public-site-page"),
]
