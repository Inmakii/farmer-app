from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from .forms import CultivationForm, FieldForm, RegistrationForm
from .models import Crop, Cultivation, Field


class RegisterView(FormView):
    template_name = "core/register.html"
    form_class = RegistrationForm
    success_url = reverse_lazy("core:login")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:profile")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        messages.success(
            self.request,
            "Konto zostało utworzone. Możesz się teraz zalogować.",
        )
        return super().form_valid(form)


class LoginView(DjangoLoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True


class LogoutView(DjangoLogoutView):
    http_method_names = ["post", "options"]


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "core/profile.html"


class FieldOwnerQuerysetMixin(LoginRequiredMixin):
    model = Field

    def get_queryset(self):
        return Field.objects.filter(owner=self.request.user)


class FieldFormUserMixin:
    form_class = FieldForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class FieldListView(FieldOwnerQuerysetMixin, ListView):
    template_name = "core/field_list.html"
    context_object_name = "fields"
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset().order_by("name")
        query = self.request.GET.get("q", "").strip()
        soil_type = self.request.GET.get("soil_type", "")
        location_method = self.request.GET.get("location_method", "")

        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(parcel_identifier__icontains=query)
                | Q(address__icontains=query)
            )
        if soil_type:
            queryset = queryset.filter(soil_type=soil_type)
        if location_method:
            queryset = queryset.filter(location_method=location_method)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_parameters = self.request.GET.copy()
        query_parameters.pop("page", None)
        context.update(
            {
                "query": self.request.GET.get("q", ""),
                "selected_soil_type": self.request.GET.get("soil_type", ""),
                "selected_location_method": self.request.GET.get(
                    "location_method", ""
                ),
                "soil_type_choices": Field.SoilType.choices,
                "location_method_choices": Field.LocationMethod.choices,
                "querystring": query_parameters.urlencode(),
            }
        )
        return context


class FieldDetailView(FieldOwnerQuerysetMixin, DetailView):
    template_name = "core/field_detail.html"
    context_object_name = "field"


class FieldCreateView(LoginRequiredMixin, FieldFormUserMixin, CreateView):
    model = Field
    template_name = "core/field_form.html"

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "Pole zostało utworzone.")
        return response

    def get_success_url(self):
        return reverse("core:field_detail", kwargs={"pk": self.object.pk})


class FieldUpdateView(FieldOwnerQuerysetMixin, FieldFormUserMixin, UpdateView):
    template_name = "core/field_form.html"
    context_object_name = "field"

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "Pole zostało zaktualizowane.")
        return response

    def get_success_url(self):
        return reverse("core:field_detail", kwargs={"pk": self.object.pk})


class FieldDeleteView(FieldOwnerQuerysetMixin, DeleteView):
    template_name = "core/field_confirm_delete.html"
    context_object_name = "field"
    success_url = reverse_lazy("core:field_list")
    http_method_names = ["get", "post", "head", "options"]

    def form_valid(self, form):
        messages.success(self.request, "Pole zostało usunięte.")
        return super().form_valid(form)


class CultivationOwnerQuerysetMixin(LoginRequiredMixin):
    model = Cultivation

    def get_queryset(self):
        return Cultivation.objects.filter(
            field__owner=self.request.user
        ).select_related("field", "crop")


class CultivationFormUserMixin:
    form_class = CultivationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_fields"] = Field.objects.filter(owner=self.request.user).exists()
        return context


class CultivationListView(CultivationOwnerQuerysetMixin, ListView):
    template_name = "core/cultivation_list.html"
    context_object_name = "cultivations"
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset().order_by(
            "-season_year", "field__name", "crop__name"
        )
        field_id = self.request.GET.get("field", "")
        crop_id = self.request.GET.get("crop", "")
        status = self.request.GET.get("status", "")
        season_year = self.request.GET.get("season_year", "")

        if field_id.isdigit():
            queryset = queryset.filter(field_id=field_id)
        if crop_id.isdigit():
            queryset = queryset.filter(crop_id=crop_id)
        if status:
            queryset = queryset.filter(status=status)
        if season_year.isdigit():
            queryset = queryset.filter(season_year=season_year)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_parameters = self.request.GET.copy()
        query_parameters.pop("page", None)
        user_fields = Field.objects.filter(owner=self.request.user).order_by("name")
        context.update(
            {
                "user_fields": user_fields,
                "has_fields": user_fields.exists(),
                "crops": Crop.objects.order_by("name"),
                "status_choices": Cultivation.Status.choices,
                "selected_field": self.request.GET.get("field", ""),
                "selected_crop": self.request.GET.get("crop", ""),
                "selected_status": self.request.GET.get("status", ""),
                "selected_season_year": self.request.GET.get("season_year", ""),
                "querystring": query_parameters.urlencode(),
            }
        )
        return context


class CultivationDetailView(CultivationOwnerQuerysetMixin, DetailView):
    template_name = "core/cultivation_detail.html"
    context_object_name = "cultivation"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "work_count": self.object.works.count(),
                "spraying_count": self.object.sprayings.count(),
                "harvest_count": self.object.harvests.count(),
            }
        )
        return context


class CultivationCreateView(LoginRequiredMixin, CultivationFormUserMixin, CreateView):
    model = Cultivation
    template_name = "core/cultivation_form.html"

    def get_initial(self):
        initial = super().get_initial()
        field_id = self.request.GET.get("field", "")
        if field_id.isdigit():
            field = Field.objects.filter(
                pk=field_id, owner=self.request.user
            ).first()
            if field is not None:
                initial["field"] = field
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Uprawa została utworzona.")
        return response

    def get_success_url(self):
        return reverse("core:cultivation_detail", kwargs={"pk": self.object.pk})


class CultivationUpdateView(
    CultivationOwnerQuerysetMixin, CultivationFormUserMixin, UpdateView
):
    template_name = "core/cultivation_form.html"
    context_object_name = "cultivation"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Uprawa została zaktualizowana.")
        return response

    def get_success_url(self):
        return reverse("core:cultivation_detail", kwargs={"pk": self.object.pk})


class CultivationDeleteView(CultivationOwnerQuerysetMixin, DeleteView):
    template_name = "core/cultivation_confirm_delete.html"
    context_object_name = "cultivation"
    success_url = reverse_lazy("core:cultivation_list")
    http_method_names = ["get", "post", "head", "options"]

    def form_valid(self, form):
        messages.success(self.request, "Uprawa została usunięta.")
        return super().form_valid(form)
