from django.urls import path

from .views import (
    CultivationCreateView,
    CultivationDeleteView,
    CultivationDetailView,
    CultivationListView,
    CultivationUpdateView,
    FieldCreateView,
    FieldDeleteView,
    FieldDetailView,
    FieldListView,
    FieldUpdateView,
    LoginView,
    LogoutView,
    ProfileView,
    RegisterView,
)

app_name = "core"

urlpatterns = [
    path("accounts/register/", RegisterView.as_view(), name="register"),
    path("accounts/login/", LoginView.as_view(), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/profile/", ProfileView.as_view(), name="profile"),
    path("fields/", FieldListView.as_view(), name="field_list"),
    path("fields/add/", FieldCreateView.as_view(), name="field_create"),
    path("fields/<int:pk>/", FieldDetailView.as_view(), name="field_detail"),
    path("fields/<int:pk>/edit/", FieldUpdateView.as_view(), name="field_update"),
    path("fields/<int:pk>/delete/", FieldDeleteView.as_view(), name="field_delete"),
    path("cultivations/", CultivationListView.as_view(), name="cultivation_list"),
    path("cultivations/add/", CultivationCreateView.as_view(), name="cultivation_create"),
    path(
        "cultivations/<int:pk>/",
        CultivationDetailView.as_view(),
        name="cultivation_detail",
    ),
    path(
        "cultivations/<int:pk>/edit/",
        CultivationUpdateView.as_view(),
        name="cultivation_update",
    ),
    path(
        "cultivations/<int:pk>/delete/",
        CultivationDeleteView.as_view(),
        name="cultivation_delete",
    ),
]
