from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_date
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from .forms import (
    CultivationForm,
    ErrorReportForm,
    FieldForm,
    FieldWorkForm,
    HarvestForm,
    RegistrationForm,
    SprayingForm,
)
from .models import Crop, Cultivation, ErrorReport, Field, FieldWork, Harvest, Spraying
from .services.reports import (
    calculate_totals,
    get_cultivation_report,
    get_cultivation_reports,
    get_field_report,
    get_user_report,
)


def parse_filter_date(value):
    try:
        return parse_date(value)
    except ValueError:
        return None


def parse_season_year(value):
    if not value:
        return None, True
    if value.isdigit() and 2000 <= int(value) <= 2100:
        return int(value), True
    return None, False


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["error_report_count"] = self.request.user.error_reports.count()
        return context


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
                "works": self.object.works.order_by("-work_date", "-id"),
                "sprayings": self.object.sprayings.order_by(
                    "-spraying_date", "-id"
                ),
                "harvests": self.object.harvests.order_by("-harvest_date", "-id"),
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


class FieldWorkOwnerQuerysetMixin(LoginRequiredMixin):
    model = FieldWork

    def get_queryset(self):
        return FieldWork.objects.filter(
            cultivation__field__owner=self.request.user
        ).select_related("cultivation", "cultivation__field", "cultivation__crop")


class FieldWorkFormUserMixin:
    form_class = FieldWorkForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_cultivations"] = Cultivation.objects.filter(
            field__owner=self.request.user
        ).exists()
        return context


class FieldWorkListView(FieldWorkOwnerQuerysetMixin, ListView):
    template_name = "core/fieldwork_list.html"
    context_object_name = "works"
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset().order_by("-work_date", "-id")
        query = self.request.GET.get("q", "").strip()
        cultivation_id = self.request.GET.get("cultivation", "")
        field_id = self.request.GET.get("field", "")
        work_type = self.request.GET.get("work_type", "")
        date_from = parse_filter_date(self.request.GET.get("date_from", ""))
        date_to = parse_filter_date(self.request.GET.get("date_to", ""))

        if query:
            queryset = queryset.filter(
                Q(description__icontains=query)
                | Q(cultivation__field__name__icontains=query)
                | Q(cultivation__crop__name__icontains=query)
            )
        if cultivation_id.isdigit():
            queryset = queryset.filter(cultivation_id=cultivation_id)
        if field_id.isdigit():
            queryset = queryset.filter(cultivation__field_id=field_id)
        if work_type:
            queryset = queryset.filter(work_type=work_type)
        if date_from:
            queryset = queryset.filter(work_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(work_date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_parameters = self.request.GET.copy()
        query_parameters.pop("page", None)
        context.update(
            {
                "user_fields": Field.objects.filter(owner=self.request.user).order_by("name"),
                "user_cultivations": Cultivation.objects.filter(
                    field__owner=self.request.user
                ).select_related("field", "crop").order_by(
                    "-season_year", "field__name", "crop__name"
                ),
                "work_type_choices": FieldWork.WorkType.choices,
                "selected_cultivation": self.request.GET.get("cultivation", ""),
                "selected_field": self.request.GET.get("field", ""),
                "selected_work_type": self.request.GET.get("work_type", ""),
                "selected_date_from": self.request.GET.get("date_from", ""),
                "selected_date_to": self.request.GET.get("date_to", ""),
                "query": self.request.GET.get("q", ""),
                "querystring": query_parameters.urlencode(),
            }
        )
        return context


class FieldWorkDetailView(FieldWorkOwnerQuerysetMixin, DetailView):
    template_name = "core/fieldwork_detail.html"
    context_object_name = "work"


class FieldWorkCreateView(LoginRequiredMixin, FieldWorkFormUserMixin, CreateView):
    model = FieldWork
    template_name = "core/fieldwork_form.html"

    def get_initial(self):
        initial = super().get_initial()
        cultivation_id = self.request.GET.get("cultivation", "")
        if cultivation_id.isdigit():
            cultivation = Cultivation.objects.filter(
                pk=cultivation_id, field__owner=self.request.user
            ).select_related("field", "crop").first()
            if cultivation:
                initial["cultivation"] = cultivation
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Praca została utworzona.")
        return response

    def get_success_url(self):
        return reverse("core:fieldwork_detail", kwargs={"pk": self.object.pk})


class FieldWorkUpdateView(
    FieldWorkOwnerQuerysetMixin, FieldWorkFormUserMixin, UpdateView
):
    template_name = "core/fieldwork_form.html"
    context_object_name = "work"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Praca została zaktualizowana.")
        return response

    def get_success_url(self):
        return reverse("core:fieldwork_detail", kwargs={"pk": self.object.pk})


class FieldWorkDeleteView(FieldWorkOwnerQuerysetMixin, DeleteView):
    template_name = "core/fieldwork_confirm_delete.html"
    context_object_name = "work"
    http_method_names = ["get", "post", "head", "options"]

    def get_success_url(self):
        cultivation_id = self.object.cultivation_id
        if Cultivation.objects.filter(
            pk=cultivation_id, field__owner=self.request.user
        ).exists():
            return reverse("core:cultivation_detail", kwargs={"pk": cultivation_id})
        return reverse("core:fieldwork_list")

    def form_valid(self, form):
        messages.success(self.request, "Praca została usunięta.")
        return super().form_valid(form)


class SprayingOwnerQuerysetMixin(LoginRequiredMixin):
    model = Spraying

    def get_queryset(self):
        return Spraying.objects.filter(
            cultivation__field__owner=self.request.user
        ).select_related("cultivation", "cultivation__field", "cultivation__crop")


class SprayingFormUserMixin:
    form_class = SprayingForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_cultivations"] = Cultivation.objects.filter(
            field__owner=self.request.user
        ).exists()
        return context


class SprayingListView(SprayingOwnerQuerysetMixin, ListView):
    template_name = "core/spraying_list.html"
    context_object_name = "sprayings"
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset().order_by("-spraying_date", "-id")
        query = self.request.GET.get("q", "").strip()
        cultivation_id = self.request.GET.get("cultivation", "")
        field_id = self.request.GET.get("field", "")
        unit = self.request.GET.get("unit", "")
        date_from = parse_filter_date(self.request.GET.get("date_from", ""))
        date_to = parse_filter_date(self.request.GET.get("date_to", ""))

        if query:
            queryset = queryset.filter(
                Q(product_name__icontains=query)
                | Q(description__icontains=query)
                | Q(cultivation__field__name__icontains=query)
                | Q(cultivation__crop__name__icontains=query)
            )
        if cultivation_id.isdigit():
            queryset = queryset.filter(cultivation_id=cultivation_id)
        if field_id.isdigit():
            queryset = queryset.filter(cultivation__field_id=field_id)
        if unit:
            queryset = queryset.filter(unit=unit)
        if date_from:
            queryset = queryset.filter(spraying_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(spraying_date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_parameters = self.request.GET.copy()
        query_parameters.pop("page", None)
        context.update(
            {
                "user_fields": Field.objects.filter(owner=self.request.user).order_by("name"),
                "user_cultivations": Cultivation.objects.filter(
                    field__owner=self.request.user
                ).select_related("field", "crop").order_by(
                    "-season_year", "field__name", "crop__name"
                ),
                "unit_choices": Spraying.Unit.choices,
                "selected_cultivation": self.request.GET.get("cultivation", ""),
                "selected_field": self.request.GET.get("field", ""),
                "selected_unit": self.request.GET.get("unit", ""),
                "selected_date_from": self.request.GET.get("date_from", ""),
                "selected_date_to": self.request.GET.get("date_to", ""),
                "query": self.request.GET.get("q", ""),
                "querystring": query_parameters.urlencode(),
            }
        )
        return context


class SprayingDetailView(SprayingOwnerQuerysetMixin, DetailView):
    template_name = "core/spraying_detail.html"
    context_object_name = "spraying"


class SprayingCreateView(LoginRequiredMixin, SprayingFormUserMixin, CreateView):
    model = Spraying
    template_name = "core/spraying_form.html"

    def get_initial(self):
        initial = super().get_initial()
        cultivation_id = self.request.GET.get("cultivation", "")
        if cultivation_id.isdigit():
            cultivation = Cultivation.objects.filter(
                pk=cultivation_id, field__owner=self.request.user
            ).select_related("field", "crop").first()
            if cultivation:
                initial["cultivation"] = cultivation
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Oprysk został utworzony.")
        return response

    def get_success_url(self):
        return reverse("core:spraying_detail", kwargs={"pk": self.object.pk})


class SprayingUpdateView(
    SprayingOwnerQuerysetMixin, SprayingFormUserMixin, UpdateView
):
    template_name = "core/spraying_form.html"
    context_object_name = "spraying"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Oprysk został zaktualizowany.")
        return response

    def get_success_url(self):
        return reverse("core:spraying_detail", kwargs={"pk": self.object.pk})


class SprayingDeleteView(SprayingOwnerQuerysetMixin, DeleteView):
    template_name = "core/spraying_confirm_delete.html"
    context_object_name = "spraying"
    http_method_names = ["get", "post", "head", "options"]

    def get_success_url(self):
        return reverse(
            "core:cultivation_detail",
            kwargs={"pk": self.object.cultivation_id},
        )

    def form_valid(self, form):
        messages.success(self.request, "Oprysk został usunięty.")
        return super().form_valid(form)


class HarvestOwnerQuerysetMixin(LoginRequiredMixin):
    model = Harvest

    def get_queryset(self):
        return Harvest.objects.filter(
            cultivation__field__owner=self.request.user
        ).select_related("cultivation", "cultivation__field", "cultivation__crop")


class HarvestFormUserMixin:
    form_class = HarvestForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_cultivations"] = Cultivation.objects.filter(
            field__owner=self.request.user
        ).exists()
        return context


class HarvestListView(HarvestOwnerQuerysetMixin, ListView):
    template_name = "core/harvest_list.html"
    context_object_name = "harvests"
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset().order_by("-harvest_date", "-id")
        query = self.request.GET.get("q", "").strip()
        cultivation_id = self.request.GET.get("cultivation", "")
        field_id = self.request.GET.get("field", "")
        unit = self.request.GET.get("unit", "")
        date_from = parse_filter_date(self.request.GET.get("date_from", ""))
        date_to = parse_filter_date(self.request.GET.get("date_to", ""))

        if query:
            queryset = queryset.filter(
                Q(notes__icontains=query)
                | Q(cultivation__field__name__icontains=query)
                | Q(cultivation__crop__name__icontains=query)
            )
        if cultivation_id.isdigit():
            queryset = queryset.filter(cultivation_id=cultivation_id)
        if field_id.isdigit():
            queryset = queryset.filter(cultivation__field_id=field_id)
        if unit:
            queryset = queryset.filter(unit=unit)
        if date_from:
            queryset = queryset.filter(harvest_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(harvest_date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_parameters = self.request.GET.copy()
        query_parameters.pop("page", None)
        context.update(
            {
                "user_fields": Field.objects.filter(owner=self.request.user).order_by("name"),
                "user_cultivations": Cultivation.objects.filter(
                    field__owner=self.request.user
                ).select_related("field", "crop").order_by(
                    "-season_year", "field__name", "crop__name"
                ),
                "unit_choices": Harvest.Unit.choices,
                "selected_cultivation": self.request.GET.get("cultivation", ""),
                "selected_field": self.request.GET.get("field", ""),
                "selected_unit": self.request.GET.get("unit", ""),
                "selected_date_from": self.request.GET.get("date_from", ""),
                "selected_date_to": self.request.GET.get("date_to", ""),
                "query": self.request.GET.get("q", ""),
                "querystring": query_parameters.urlencode(),
            }
        )
        return context


class HarvestDetailView(HarvestOwnerQuerysetMixin, DetailView):
    template_name = "core/harvest_detail.html"
    context_object_name = "harvest"


class HarvestCreateView(LoginRequiredMixin, HarvestFormUserMixin, CreateView):
    model = Harvest
    template_name = "core/harvest_form.html"

    def get_initial(self):
        initial = super().get_initial()
        cultivation_id = self.request.GET.get("cultivation", "")
        if cultivation_id.isdigit():
            cultivation = Cultivation.objects.filter(
                pk=cultivation_id, field__owner=self.request.user
            ).select_related("field", "crop").first()
            if cultivation:
                initial["cultivation"] = cultivation
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Zbiór został utworzony.")
        return response

    def get_success_url(self):
        return reverse("core:harvest_detail", kwargs={"pk": self.object.pk})


class HarvestUpdateView(HarvestOwnerQuerysetMixin, HarvestFormUserMixin, UpdateView):
    template_name = "core/harvest_form.html"
    context_object_name = "harvest"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Zbiór został zaktualizowany.")
        return response

    def get_success_url(self):
        return reverse("core:harvest_detail", kwargs={"pk": self.object.pk})


class HarvestDeleteView(HarvestOwnerQuerysetMixin, DeleteView):
    template_name = "core/harvest_confirm_delete.html"
    context_object_name = "harvest"
    http_method_names = ["get", "post", "head", "options"]

    def get_success_url(self):
        return reverse(
            "core:cultivation_detail", kwargs={"pk": self.object.cultivation_id}
        )

    def form_valid(self, form):
        messages.success(self.request, "Zbiór został usunięty.")
        return super().form_valid(form)


class ReportDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/report_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_fields = Field.objects.filter(owner=self.request.user).order_by("name")
        field_value = self.request.GET.get("field", "")
        season_value = self.request.GET.get("season_year", "")
        season_year, valid_year = parse_season_year(season_value)
        selected_field = None
        valid_field = not field_value
        if field_value.isdigit():
            selected_field = user_fields.filter(pk=field_value).first()
            valid_field = selected_field is not None

        if valid_field and valid_year:
            report = get_user_report(
                self.request.user,
                field=selected_field,
                season_year=season_year,
            )
        else:
            empty_queryset = Cultivation.objects.none()
            report = {
                "totals": calculate_totals(empty_queryset),
                "cultivation_reports": get_cultivation_reports(empty_queryset),
            }
            report["totals"]["field_count"] = 0

        context.update(
            {
                **report,
                "user_fields": user_fields,
                "selected_field": field_value,
                "selected_season_year": season_value,
                "invalid_filters": not (valid_field and valid_year),
            }
        )
        return context


class FieldReportView(LoginRequiredMixin, DetailView):
    model = Field
    template_name = "core/field_report.html"
    context_object_name = "field"

    def get_queryset(self):
        return Field.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        season_value = self.request.GET.get("season_year", "")
        season_year, valid_year = parse_season_year(season_value)
        if valid_year:
            report = get_field_report(self.object, season_year=season_year)
        else:
            empty_queryset = Cultivation.objects.none()
            report = {
                "field": self.object,
                "totals": calculate_totals(empty_queryset),
                "cultivation_reports": [],
            }
            report["totals"]["field_count"] = 1
        context.update(
            {
                **report,
                "selected_season_year": season_value,
                "invalid_filter": not valid_year,
            }
        )
        return context


class CultivationReportView(LoginRequiredMixin, DetailView):
    model = Cultivation
    template_name = "core/cultivation_report.html"
    context_object_name = "cultivation"

    def get_queryset(self):
        return Cultivation.objects.filter(
            field__owner=self.request.user
        ).select_related("field", "crop")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["report"] = get_cultivation_report(self.object)
        return context


class ErrorReportOwnerQuerysetMixin(LoginRequiredMixin):
    model = ErrorReport

    def get_queryset(self):
        return ErrorReport.objects.filter(user=self.request.user)


class ErrorReportListView(ErrorReportOwnerQuerysetMixin, ListView):
    template_name = "core/error_report_list.html"
    context_object_name = "error_reports"
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset().order_by("-created_at")
        category = self.request.GET.get("category", "")
        status = self.request.GET.get("status", "")
        if category in ErrorReport.Category.values:
            queryset = queryset.filter(category=category)
        if status in ErrorReport.Status.values:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "category_choices": ErrorReport.Category.choices,
                "status_choices": ErrorReport.Status.choices,
                "selected_category": self.request.GET.get("category", ""),
                "selected_status": self.request.GET.get("status", ""),
            }
        )
        return context


class ErrorReportDetailView(ErrorReportOwnerQuerysetMixin, DetailView):
    template_name = "core/error_report_detail.html"
    context_object_name = "error_report"


class ErrorReportCreateView(LoginRequiredMixin, CreateView):
    model = ErrorReport
    form_class = ErrorReportForm
    template_name = "core/error_report_form.html"

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.status = ErrorReport.Status.NEW
        response = super().form_valid(form)
        messages.success(self.request, "Zgłoszenie błędu zostało utworzone.")
        return response

    def get_success_url(self):
        return reverse("core:error_report_detail", kwargs={"pk": self.object.pk})
