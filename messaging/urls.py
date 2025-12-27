from django.urls import path

from . import views

app_name = "messaging"

urlpatterns = [
	path("", views.inbox, name="inbox"),
	path("new/", views.new_thread, name="new"),
	path("<int:thread_id>/", views.thread_detail, name="thread"),
]
