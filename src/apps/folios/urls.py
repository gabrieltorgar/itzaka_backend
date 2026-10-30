"""Folios URLs."""

from django.urls import path

from apps.folios.views import (
    FolioPreviewView,
    FolioSettingDetailView,
    FolioSettingsView,
)

app_name = "folios"

urlpatterns = [
    path("folio-settings/", FolioSettingsView.as_view(), name="settings"),
    path(
        "folio-settings/<str:document_type>/",
        FolioSettingDetailView.as_view(),
        name="setting",
    ),
    path(
        "folio-settings/<str:document_type>/preview/",
        FolioPreviewView.as_view(),
        name="preview",
    ),
]
