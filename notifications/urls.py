from __future__ import annotations
from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.list_view, name="list"),
    path("all/", views.list_view, name="list_all"),  # alias
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/mark-read/", views.mark_read, name="mark_read"),
    path("mark-all-read/", views.mark_all_read, name="mark_all_read"),
    path("<int:pk>/delete/", views.delete, name="delete"),
    path("delete-all/", views.delete_all, name="delete_all"),

    # --- API ---
    path("api/unread-count", views.api_unread_count, name="api_unread_count"),
    path("api/recent", views.api_recent, name="api_recent"),
    path("api/<int:pk>/mark-read", views.api_mark_read, name="api_mark_read"),
]
