from django.urls import path

from .views import (
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
]
