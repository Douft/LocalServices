from django.urls import path

from .views import contact_provider, dashboard, live_search, provider_out, public_search

urlpatterns = [
    path("dashboard/", dashboard, name="dashboard"),
    path("search/", public_search, name="public_search"),
    path("search/live/", live_search, name="live_search"),
    path("provider/<int:provider_id>/contact/", contact_provider, name="provider_contact"),
    path("out/provider/<int:provider_id>/", provider_out, name="provider_out"),
]
