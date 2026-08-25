from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", views.health),
    path("v1/terminals/register", views.register),
    path("v1/terminals", views.terminal_list),
    path("v1/terminals/<uuid:terminal_id>", views.terminal_detail),
    path("v1/terminals/<uuid:terminal_id>/heartbeat", views.heartbeat),
    path("v1/terminals/<uuid:terminal_id>/inventory", views.inventory),
    path("v1/terminals/<uuid:terminal_id>/commands", views.commands),
    path(
        "v1/terminals/<uuid:terminal_id>/commands/<str:command_id>/result",
        views.command_result,
    ),
]
