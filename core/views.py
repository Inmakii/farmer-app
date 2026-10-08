import hashlib
import re

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.contrib.messages.views import SuccessMessageMixin
from django.core.cache import cache
from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
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
    CropForm,
    CultivationForm,
    ErrorReportForm,
    FieldForm,
    FieldWorkForm,
    HarvestForm,
    LoginForm,
    ProfileEditForm,
    RegistrationForm,
    SprayingForm,
)
from .models import (
    SEASON_YEAR_MAX,
    SEASON_YEAR_MIN,
    Crop,
    Cultivation,
    ErrorReport,
    Field,
    FieldWork,
    Harvest,
    Spraying,
)
from .services.reports import (
    calculate_totals,
    get_cultivation_report,
    get_cultivation_reports,
    get_field_report,
    get_user_report,
)


def home(request):
    """Home page: app description for guests, dashboard with a next-step hint for signed-in users."""
    if not request.user.is_authenticated:
        return render(request, "core/home.html")

    totals = get_user_report(request.user)["totals"]
    no_crops = not Crop.objects.exists()
    if totals["field_count"] == 0:
        next_step = {
            "title": "Dodaj swoje pierwsze pole",
            "text": "Pole to podstawa: na nim zapiszesz uprawy, prace, opryski i zbiory.",
            "button": "Dodaj pole",
            "url": reverse("core:field_create"),
        }
    elif totals["cultivation_count"] == 0:
        next_step = {
            "title": "Dodaj uprawę na swoim polu",
            "text": "Wybierz roślinę i rok sezonu, aby zacząć zapisywać zabiegi i zbiory.",
            "button": "Dodaj uprawę",
            "url": reverse("core:cultivation_create"),
        }
    elif totals["work_count"] + totals["spraying_count"] + totals["harvest_count"] == 0:
        next_step = {
            "title": "Zapisz pierwszą pracę lub zbiór",
            "text": "Dodaj wykonaną pracę, oprysk albo zbiór, a raport policzy koszty i zysk.",
            "button": "Zapisz pracę",
            "url": reverse("core:fieldwork_create"),
        }
    else:
        next_step = {
            "title": "Sprawdź wyniki gospodarstwa",
            "text": "Raport pokazuje koszty, przychody i zysk dla pól oraz upraw.",
            "button": "Zobacz raport",
            "url": reverse("core:report_dashboard"),
        }
    return render(
        request,
        "core/dashboard.html",
        {"totals": totals, "next_step": next_step, "no_crops": no_crops},
    )


SEASON_YEAR_PATTERN = re.compile(r"[0-9]{4}")


def parse_filter_date(value):
    try:
        return parse_date(value)
    except ValueError:
        return None


def parse_season_year(value):
    if not value:
        return None, True
    if SEASON_YEAR_PATTERN.fullmatch(value) and SEASON_YEAR_MIN <= int(value) <= SEASON_YEAR_MAX:
        return int(value), True
    return None, False


class RegisterView(FormView):
    template_name = "core/register.html"
    form_class = RegistrationForm
    success_url = reverse_lazy("core:login")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        messages.success(
            self.request,
            "Konto zostało utworzone. Możesz się teraz zalogować.",
        )
        return super().form_valid(form)


LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60


class LoginView(DjangoLoginView):
    """Login with a lockout after a series of failed attempts (per IP address and username)."""

    template_name = "core/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def _failure_cache_key(self):
        username = self.request.POST.get("username", "").strip().lower()
        identity = f"{self.request.META.get('REMOTE_ADDR', '')}|{username}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return f"login-failures:{digest}"

    def post(self, request, *args, **kwargs):
        self._locked_out = (
            cache.get(self._failure_cache_key(), 0) >= LOGIN_MAX_FAILURES
        )
        if self._locked_out:
            form = self.get_form()
            form.add_error(
                None,
                "Zbyt wiele nieudanych prób logowania. Spróbuj ponownie za kilka minut.",
            )
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        cache.delete(self._failure_cache_key())
        return super().form_valid(form)

    def form_invalid(self, form):
        if not self._locked_out:
            key = self._failure_cache_key()
            cache.add(key, 0, LOGIN_LOCKOUT_SECONDS)
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, LOGIN_LOCKOUT_SECONDS)
        return super().form_invalid(form)


class LogoutView(DjangoLogoutView):
    http_method_names = ["post", "options"]


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "core/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["error_report_count"] = self.request.user.error_reports.count()
        return context


class ProfileEditView(LoginRequiredMixin, FormView):
    template_name = "core/profile_edit.html"
    form_class = ProfileEditForm
    success_url = reverse_lazy("core:profile")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Dane profilu zostały zaktualizowane.")
        return super().form_valid(form)


class PasswordChangeView(LoginRequiredMixin, FormView):
    template_name = "core/password_change.html"
    form_class = PasswordChangeForm
    success_url = reverse_lazy("core:profile")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = form.save()
        update_session_auth_hash(self.request, user)
        messages.success(self.request, "Hasło zostało zmienione.")
        return super().form_valid(form)


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
        context["has_crops"] = Crop.objects.exists()
        return context


class CropListView(LoginRequiredMixin, ListView):
    template_name = "core/crop_list.html"
    context_object_name = "crops"
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        return Crop.objects.order_by(Lower("name"), "name")


class CropCreateView(LoginRequiredMixin, CreateView):
    model = Crop
    form_class = CropForm
    template_name = "core/crop_form.html"
    success_url = reverse_lazy("core:crop_list")
    http_method_names = ["get", "post", "head", "options"]

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, f"Rodzaj uprawy „{self.object.name}” został dodany."
        )
        return response


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
        season_year, _ = parse_season_year(self.request.GET.get("season_year", ""))

        if field_id.isdigit():
            queryset = queryset.filter(field_id=field_id)
        if crop_id.isdigit():
            queryset = queryset.filter(crop_id=crop_id)
        if status in Cultivation.Status.values:
            queryset = queryset.filter(status=status)
        if season_year is not None:
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


class CultivationEventOwnerMixin(LoginRequiredMixin):
    """Limit cultivation events (works, sprayings, harvests) to fields of the signed-in owner."""

    def get_queryset(self):
        return self.model.objects.filter(
            cultivation__field__owner=self.request.user
        ).select_related("cultivation", "cultivation__field", "cultivation__crop")


class CultivationEventFormMixin:
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


class CultivationEventListView(CultivationEventOwnerMixin, ListView):
    """List with search and filters shared by works, sprayings and harvests.

    Subclasses set ``date_field``, ``search_fields`` (extra text fields)
    and ``choice_filters`` as tuples ``(parameter, context_choices_name, enum)``.
    """

    paginate_by = 10
    date_field = None
    search_fields = ()
    choice_filters = ()

    def get_queryset(self):
        queryset = super().get_queryset().order_by(f"-{self.date_field}", "-id")
        params = self.request.GET
        query = params.get("q", "").strip()
        cultivation_id = params.get("cultivation", "")
        field_id = params.get("field", "")
        date_from = parse_filter_date(params.get("date_from", ""))
        date_to = parse_filter_date(params.get("date_to", ""))

        if query:
            condition = (
                Q(cultivation__field__name__icontains=query)
                | Q(cultivation__crop__name__icontains=query)
            )
            for name in self.search_fields:
                condition |= Q(**{f"{name}__icontains": query})
            queryset = queryset.filter(condition)
        if cultivation_id.isdigit():
            queryset = queryset.filter(cultivation_id=cultivation_id)
        if field_id.isdigit():
            queryset = queryset.filter(cultivation__field_id=field_id)
        for param, _context_name, choices in self.choice_filters:
            value = params.get(param, "")
            if value in choices.values:
                queryset = queryset.filter(**{param: value})
        if date_from:
            queryset = queryset.filter(**{f"{self.date_field}__gte": date_from})
        if date_to:
            queryset = queryset.filter(**{f"{self.date_field}__lte": date_to})
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET
        query_parameters = params.copy()
        query_parameters.pop("page", None)
        context.update(
            {
                "user_fields": Field.objects.filter(
                    owner=self.request.user
                ).order_by("name"),
                "user_cultivations": Cultivation.objects.filter(
                    field__owner=self.request.user
                ).select_related("field", "crop").order_by(
                    "-season_year", "field__name", "crop__name"
                ),
                "selected_cultivation": params.get("cultivation", ""),
                "selected_field": params.get("field", ""),
                "selected_date_from": params.get("date_from", ""),
                "selected_date_to": params.get("date_to", ""),
                "query": params.get("q", ""),
                "querystring": query_parameters.urlencode(),
            }
        )
        for param, context_name, choices in self.choice_filters:
            context[context_name] = choices.choices
            context[f"selected_{param}"] = params.get(param, "")
        return context


class CultivationEventCreateView(
    LoginRequiredMixin, CultivationEventFormMixin, SuccessMessageMixin, CreateView
):
    detail_url_name = None

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

    def get_success_url(self):
        return reverse(self.detail_url_name, kwargs={"pk": self.object.pk})


class CultivationEventUpdateView(
    CultivationEventOwnerMixin,
    CultivationEventFormMixin,
    SuccessMessageMixin,
    UpdateView,
):
    detail_url_name = None

    def get_success_url(self):
        return reverse(self.detail_url_name, kwargs={"pk": self.object.pk})


class CultivationEventDeleteView(
    CultivationEventOwnerMixin, SuccessMessageMixin, DeleteView
):
    http_method_names = ["get", "post", "head", "options"]

    def get_success_url(self):
        return reverse(
            "core:cultivation_detail", kwargs={"pk": self.object.cultivation_id}
        )


class FieldWorkListView(CultivationEventListView):
    model = FieldWork
    template_name = "core/fieldwork_list.html"
    context_object_name = "works"
    date_field = "work_date"
    search_fields = ("description",)
    choice_filters = (("work_type", "work_type_choices", FieldWork.WorkType),)


class FieldWorkDetailView(CultivationEventOwnerMixin, DetailView):
    model = FieldWork
    template_name = "core/fieldwork_detail.html"
    context_object_name = "work"


class FieldWorkCreateView(CultivationEventCreateView):
    model = FieldWork
    form_class = FieldWorkForm
    template_name = "core/fieldwork_form.html"
    detail_url_name = "core:fieldwork_detail"
    success_message = "Praca została utworzona."


class FieldWorkUpdateView(CultivationEventUpdateView):
    model = FieldWork
    form_class = FieldWorkForm
    template_name = "core/fieldwork_form.html"
    context_object_name = "work"
    detail_url_name = "core:fieldwork_detail"
    success_message = "Praca została zaktualizowana."


class FieldWorkDeleteView(CultivationEventDeleteView):
    model = FieldWork
    template_name = "core/fieldwork_confirm_delete.html"
    context_object_name = "work"
    success_message = "Praca została usunięta."


class SprayingListView(CultivationEventListView):
    model = Spraying
    template_name = "core/spraying_list.html"
    context_object_name = "sprayings"
    date_field = "spraying_date"
    search_fields = ("product_name", "description")
    choice_filters = (("unit", "unit_choices", Spraying.Unit),)


class SprayingDetailView(CultivationEventOwnerMixin, DetailView):
    model = Spraying
    template_name = "core/spraying_detail.html"
    context_object_name = "spraying"


class SprayingCreateView(CultivationEventCreateView):
    model = Spraying
    form_class = SprayingForm
    template_name = "core/spraying_form.html"
    detail_url_name = "core:spraying_detail"
    success_message = "Oprysk został utworzony."


class SprayingUpdateView(CultivationEventUpdateView):
    model = Spraying
    form_class = SprayingForm
    template_name = "core/spraying_form.html"
    context_object_name = "spraying"
    detail_url_name = "core:spraying_detail"
    success_message = "Oprysk został zaktualizowany."


class SprayingDeleteView(CultivationEventDeleteView):
    model = Spraying
    template_name = "core/spraying_confirm_delete.html"
    context_object_name = "spraying"
    success_message = "Oprysk został usunięty."


class HarvestListView(CultivationEventListView):
    model = Harvest
    template_name = "core/harvest_list.html"
    context_object_name = "harvests"
    date_field = "harvest_date"
    search_fields = ("notes",)
    choice_filters = (
        ("unit", "unit_choices", Harvest.Unit),
        ("disposition", "disposition_choices", Harvest.Disposition),
    )


class HarvestDetailView(CultivationEventOwnerMixin, DetailView):
    model = Harvest
    template_name = "core/harvest_detail.html"
    context_object_name = "harvest"


class HarvestCreateView(CultivationEventCreateView):
    model = Harvest
    form_class = HarvestForm
    template_name = "core/harvest_form.html"
    detail_url_name = "core:harvest_detail"
    success_message = "Zbiór został utworzony."


class HarvestUpdateView(CultivationEventUpdateView):
    model = Harvest
    form_class = HarvestForm
    template_name = "core/harvest_form.html"
    context_object_name = "harvest"
    detail_url_name = "core:harvest_detail"
    success_message = "Zbiór został zaktualizowany."


class HarvestDeleteView(CultivationEventDeleteView):
    model = Harvest
    template_name = "core/harvest_confirm_delete.html"
    context_object_name = "harvest"
    success_message = "Zbiór został usunięty."


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

    def get_source_page(self):
        """Address of the page the report was opened from (only a path within this app)."""
        source = self.request.GET.get("from", "")
        if source.startswith("/") and url_has_allowed_host_and_scheme(
            source, allowed_hosts={self.request.get_host()}
        ):
            return source
        return ""

    def get_initial(self):
        initial = super().get_initial()
        source = self.get_source_page()
        if source:
            initial["description"] = f"Strona: {source}\n\n"
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["source_page"] = self.get_source_page()
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.status = ErrorReport.Status.NEW
        response = super().form_valid(form)
        messages.success(self.request, "Zgłoszenie błędu zostało utworzone.")
        return response

    def get_success_url(self):
        return reverse("core:error_report_detail", kwargs={"pk": self.object.pk})
