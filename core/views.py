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

from .forms import FieldForm, RegistrationForm
from .models import Field


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
