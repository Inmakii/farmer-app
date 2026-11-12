import os
import re

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.template.defaultfilters import filesizeformat
from django.utils.text import format_lazy
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from .models import (
    SEASON_YEAR_MAX,
    SEASON_YEAR_MIN,
    Crop,
    Cultivation,
    ATTACHMENT_EXTENSIONS,
    ErrorReport,
    ErrorReportAttachment,
    Field,
    FieldWork,
    Harvest,
    Spraying,
)
from .services import geodata


class SkipDuplicateModelErrorsMixin:
    """Skip Model.clean() errors that the form has already reported for this field."""

    def _update_errors(self, errors):
        if hasattr(errors, "error_dict"):
            error_dict = {}
            for field, field_errors in errors.error_dict.items():
                new_errors = [
                    error
                    for error in field_errors
                    if next(iter(error)) not in self._errors.get(field, [])
                ]
                if new_errors:
                    error_dict[field] = new_errors
            errors = ValidationError(error_dict)
        super()._update_errors(errors)


class RegistrationForm(UserCreationForm):
    error_messages = {
        "password_mismatch": _("The passwords do not match."),
    }

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email")
        labels = {
            "username": _("Username"),
            "first_name": _("First name"),
            "last_name": _("Last name"),
            "email": _("Email address"),
        }
        error_messages = {
            "username": {
                "required": _("Username is required."),
                "unique": _("A user with this name already exists."),
            },
            "first_name": {"required": _("First name is required.")},
            "last_name": {"required": _("Last name is required.")},
            "email": {
                "required": _("Email address is required."),
                "invalid": _("Enter a valid email address."),
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        required_fields = {
            "username": gettext("Username"),
            "first_name": gettext("First name"),
            "last_name": gettext("Last name"),
            "email": gettext("Email address"),
            "password1": gettext("Password"),
            "password2": gettext("Repeat password"),
        }
        for field_name, label in required_fields.items():
            self.fields[field_name].required = True
            self.fields[field_name].label = label
            self.fields[field_name].error_messages["required"] = gettext(
                "The field “%(label)s” is required."
            ) % {"label": label}
        # First name is the first field of the form, so the cursor does not jump to the username.
        self.fields["username"].widget.attrs.pop("autofocus", None)
        self.fields["username"].widget.attrs["spellcheck"] = "false"
        self.fields["username"].help_text = gettext(
            "You will use it to log in, e.g. jan.kowalski. "
            "Letters, digits and @ . + - _ characters, no spaces."
        )
        self.fields["first_name"].widget.attrs["autocomplete"] = "given-name"
        self.fields["last_name"].widget.attrs["autocomplete"] = "family-name"
        self.fields["email"].widget.attrs.update(
            {"autocomplete": "email", "autocapitalize": "none", "spellcheck": "false"}
        )
        self.fields["password1"].help_text = gettext(
            "At least 8 characters. The password cannot be all digits, resemble "
            "your username or name, or be a common password like “qwerty123”."
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        user_model = get_user_model()
        if user_model._default_manager.filter(email__iexact=email).exists():
            raise ValidationError(gettext("A user with this email address already exists."))
        return email


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _(
            "The username or password is incorrect. Check that Caps Lock is off, "
            "because letter case matters."
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["spellcheck"] = "false"


class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name", "email")
        labels = {
            "first_name": _("First name"),
            "last_name": _("Last name"),
            "email": _("Email address"),
        }
        error_messages = {
            "email": {
                "required": _("Email address is required."),
                "invalid": _("Enter a valid email address."),
            }
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        users = get_user_model()._default_manager.filter(email__iexact=email)
        if self.instance.pk:
            users = users.exclude(pk=self.instance.pk)
        if users.exists():
            raise ValidationError(gettext("A user with this email address already exists."))
        return email


class FieldForm(forms.ModelForm):
    class Meta:
        model = Field
        fields = (
            "name",
            "area_ha",
            "soil_type",
            # The method comes first; the page then shows only its own fields.
            "location_method",
            "parcel_identifier",
            "address",
            "latitude",
            "longitude",
            "description",
        )
        labels = {
            "name": _("Field name"),
            "area_ha": _("Area (ha)"),
            "soil_type": _("Soil type"),
            "parcel_identifier": _("Parcel identifier"),
            "location_method": _("How the location is given"),
            "address": _("Address"),
            "latitude": _("Latitude"),
            "longitude": _("Longitude"),
            "description": _("Description"),
        }
        help_texts = {
            "name": _("The name must be unique among your fields."),
            "area_ha": _("Enter a positive area in hectares."),
            "parcel_identifier": _(
                "Filled in after choosing the locality and parcel number. You can also "
                "enter the full identifier, e.g. 040306_2.0008.100/1."
            ),
            "address": _(
                "Filled in after choosing the locality, street and number. You can also "
                "type the address yourself."
            ),
            "latitude": _("Required for GPS and a point on a map; range -90 to 90."),
            "longitude": _("Required for GPS and a point on a map; range -180 to 180."),
        }
        error_messages = {
            "name": {"required": _("Field name is required.")},
            "area_ha": {
                "required": _("Field area is required."),
                "invalid": _("Enter a valid field area."),
            },
            "soil_type": {"required": _("Choose the soil type.")},
            "location_method": {"required": _("Choose how the location is given.")},
            "latitude": {"invalid": _("Enter a valid latitude.")},
            "longitude": {"invalid": _("Enter a valid longitude.")},
        }

    # Helper fields (not stored): the locality, street and house number or parcel
    # number are looked up in the national registers (core.services.geodata) and
    # fill in the address or parcel identifier and the coordinates.
    locality = forms.CharField(
        label=_("Locality"), required=False, max_length=200,
        help_text=_("Start typing and choose the locality from the list."),
    )
    street = forms.CharField(
        label=_("Street"), required=False, max_length=200,
        help_text=_("Leave empty in a village without street names."),
    )
    house_number = forms.CharField(label=_("House number"), required=False, max_length=20)
    parcel_number = forms.CharField(
        label=_("Parcel number"), required=False, max_length=30,
        help_text=_("The number from the land register, e.g. 100/1."),
    )
    locality_sym = forms.CharField(required=False, widget=forms.HiddenInput, max_length=7)
    locality_name = forms.CharField(required=False, widget=forms.HiddenInput, max_length=100)
    locality_commune = forms.CharField(required=False, widget=forms.HiddenInput, max_length=100)
    street_sym = forms.CharField(required=False, widget=forms.HiddenInput, max_length=5)

    # Location method -> fields that belong to it. core/static/core/forms.js shows
    # only these fields (plus fields that already hold a value).
    LOCATION_FIELDS = {
        "locality": (Field.LocationMethod.ADDRESS, Field.LocationMethod.PARCEL),
        "street": (Field.LocationMethod.ADDRESS,),
        "house_number": (Field.LocationMethod.ADDRESS,),
        "parcel_number": (Field.LocationMethod.PARCEL,),
        "parcel_identifier": (Field.LocationMethod.PARCEL,),
        "address": (Field.LocationMethod.ADDRESS,),
        "latitude": (Field.LocationMethod.GPS, Field.LocationMethod.MAP),
        "longitude": (Field.LocationMethod.GPS, Field.LocationMethod.MAP),
    }
    # Inputs that get hints from core/geo_views.py.
    HINT_INPUTS = {"locality": "locality", "street": "street", "house_number": "number"}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.order_fields([
            "name", "area_ha", "soil_type", "location_method",
            "locality", "street", "house_number", "parcel_number",
            "parcel_identifier", "address", "latitude", "longitude", "description",
        ])
        self.fields["location_method"].widget.attrs["data-location-method"] = ""
        for name, methods in self.LOCATION_FIELDS.items():
            self.fields[name].widget.attrs["data-location-for"] = " ".join(methods)
        for name, kind in self.HINT_INPUTS.items():
            self.fields[name].widget.attrs.update({"data-geo": kind, "autocomplete": "off"})

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if self.user is not None:
            duplicates = Field.objects.filter(owner=self.user, name__iexact=name)
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise ValidationError(gettext("You already have a field with this name."))
        return name

    def clean_area_ha(self):
        area_ha = self.cleaned_data["area_ha"]
        if area_ha <= 0:
            raise ValidationError(gettext("Field area must be greater than zero."))
        return area_ha

    def _set_coordinates(self, found):
        # Coordinates follow the address or parcel unless the user typed them.
        if "latitude" in self.changed_data or "longitude" in self.changed_data:
            return
        self.cleaned_data["latitude"] = found["latitude"]
        self.cleaned_data["longitude"] = found["longitude"]

    def _lookup_address(self):
        data = self.cleaned_data
        sym = data.get("locality_sym", "")
        number = data.get("house_number", "").strip()
        typed_address = data.get("address", "")
        if sym and number:
            try:
                found = geodata.find_address(sym, data.get("street_sym", ""), number)
            except geodata.GeoServiceError:
                if not typed_address:
                    self.add_error("address", gettext(
                        "The address register is not available right now. "
                        "Type the address yourself."
                    ))
                return
            if found is None:
                self.add_error("house_number", gettext(
                    "This address was not found in the address register."
                ))
                return
            data["address"] = found["address"]
            self._set_coordinates(found)
        elif not typed_address and (data.get("locality") or number):
            field = "house_number" if sym else "locality"
            message = (
                gettext("Enter the house number.") if sym
                else gettext("Choose the locality from the list.")
            )
            self.add_error(field, message)
        elif typed_address and "address" in self.changed_data:
            try:
                found = geodata.geocode_address(typed_address)
            except geodata.GeoServiceError:
                return
            if found:
                self._set_coordinates(found)

    def _lookup_parcel(self):
        data = self.cleaned_data
        number = data.get("parcel_number", "").strip()
        typed_id = data.get("parcel_identifier", "")
        if number:
            if not geodata.PARCEL_NUMBER_RE.match(number):
                self.add_error("parcel_number", gettext("Enter a parcel number such as 100 or 100/1."))
                return
            name = data.get("locality_name", "")
            if not name:
                self.add_error("locality", gettext("Choose the locality from the list."))
                return
            try:
                region = geodata.find_region(name, data.get("locality_commune", ""))
                parcel = geodata.get_parcel(f"{region}.{number}") if region else None
            except geodata.GeoServiceError:
                if not typed_id:
                    self.add_error("parcel_number", gettext(
                        "The parcel register is not available right now. "
                        "Enter the full parcel identifier yourself."
                    ))
                return
            if region is None:
                self.add_error("locality", gettext(
                    "No cadastral region with this name was found in this commune. "
                    "Enter the full parcel identifier yourself."
                ))
                return
            if parcel is None:
                self.add_error("parcel_number", gettext(
                    "There is no parcel with this number in %(region)s."
                ) % {"region": name})
                return
            data["parcel_identifier"] = parcel["id"]
            self._set_coordinates(parcel)
        elif typed_id and "parcel_identifier" in self.changed_data:
            if not geodata.PARCEL_ID_RE.match(typed_id):
                return  # a free-form identifier is kept as it is
            try:
                parcel = geodata.get_parcel(typed_id)
            except geodata.GeoServiceError:
                return
            if parcel is None:
                self.add_error("parcel_identifier", gettext(
                    "This parcel was not found in the land register."
                ))
                return
            self._set_coordinates(parcel)

    def clean(self):
        cleaned_data = super().clean()
        location_method = cleaned_data.get("location_method")
        errors_before = len(self.errors)
        if settings.GEODATA_ENABLED:
            if location_method == Field.LocationMethod.ADDRESS:
                self._lookup_address()
            elif location_method == Field.LocationMethod.PARCEL:
                self._lookup_parcel()
        if len(self.errors) > errors_before:
            # The lookup already explained what is missing; no second "required" error.
            return cleaned_data
        address = cleaned_data.get("address")
        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")
        parcel_identifier = cleaned_data.get("parcel_identifier")

        if location_method == Field.LocationMethod.ADDRESS and not address:
            self.add_error(
                "address", gettext("Address is required for this location method.")
            )
        if location_method in (Field.LocationMethod.GPS, Field.LocationMethod.MAP):
            if latitude is None:
                self.add_error(
                    "latitude", gettext("Latitude is required for this location.")
                )
            if longitude is None:
                self.add_error(
                    "longitude", gettext("Longitude is required for this location.")
                )
        if location_method == Field.LocationMethod.PARCEL and not parcel_identifier:
            self.add_error(
                "parcel_identifier",
                gettext("Parcel identifier is required for this location method."),
            )

        return cleaned_data


SEASON_YEAR_RANGE_ERROR = format_lazy(
    _("The season year must be between {min} and {max}."),
    min=SEASON_YEAR_MIN,
    max=SEASON_YEAR_MAX,
)


class CultivationForm(SkipDuplicateModelErrorsMixin, forms.ModelForm):
    class Meta:
        model = Cultivation
        fields = (
            "field",
            "crop",
            "season_year",
            "status",
            "sowing_date",
            "planned_harvest_date",
            "notes",
        )
        labels = {
            "field": _("Field"),
            "crop": _("Crop type"),
            "season_year": _("Season year"),
            "status": _("Status"),
            "sowing_date": _("Sowing date"),
            "planned_harvest_date": _("Planned harvest date"),
            "notes": _("Notes"),
        }
        help_texts = {
            "field": _("You can only choose one of your own fields."),
            "season_year": format_lazy(
                _("Allowed years: {min}–{max}."), min=SEASON_YEAR_MIN, max=SEASON_YEAR_MAX
            ),
            "sowing_date": _("Optional date when sowing started."),
            "planned_harvest_date": _("Cannot be earlier than the sowing date."),
        }
        error_messages = {
            "field": {
                "required": _("Choose a field."),
                "invalid_choice": _("The chosen field is not available."),
            },
            "crop": {
                "required": _("Choose a crop type."),
                "invalid_choice": _("The chosen crop type is not available."),
            },
            "season_year": {
                "required": _("Season year is required."),
                "invalid": _("Enter a valid season year."),
                "min_value": SEASON_YEAR_RANGE_ERROR,
                "max_value": SEASON_YEAR_RANGE_ERROR,
            },
            "status": {"required": _("Choose the cultivation status.")},
            "sowing_date": {"invalid": _("Enter a valid sowing date.")},
            "planned_harvest_date": {
                "invalid": _("Enter a valid planned harvest date.")
            },
        }
        widgets = {
            "sowing_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "min": f"{SEASON_YEAR_MIN}-01-01",
                    "max": f"{SEASON_YEAR_MAX}-12-31",
                },
                format="%Y-%m-%d",
            ),
            "planned_harvest_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "min": f"{SEASON_YEAR_MIN}-01-01",
                    "max": f"{SEASON_YEAR_MAX + 1}-12-31",
                },
                format="%Y-%m-%d",
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["field"].queryset = (
            Field.objects.filter(owner=user).order_by("name")
            if user is not None
            else Field.objects.none()
        )
        self.fields["crop"].queryset = Crop.objects.order_by("name")
        self.fields["season_year"].widget.attrs.update(
            {"min": SEASON_YEAR_MIN, "max": SEASON_YEAR_MAX}
        )
        self.fields["sowing_date"].input_formats = ["%Y-%m-%d"]
        self.fields["planned_harvest_date"].input_formats = ["%Y-%m-%d"]

    def clean_season_year(self):
        season_year = self.cleaned_data["season_year"]
        if not SEASON_YEAR_MIN <= season_year <= SEASON_YEAR_MAX:
            raise ValidationError(SEASON_YEAR_RANGE_ERROR)
        return season_year

    def clean(self):
        cleaned_data = super().clean()
        field = cleaned_data.get("field")
        crop = cleaned_data.get("crop")
        season_year = cleaned_data.get("season_year")
        sowing_date = cleaned_data.get("sowing_date")
        planned_harvest_date = cleaned_data.get("planned_harvest_date")

        if sowing_date and season_year and sowing_date.year != season_year:
            self.add_error(
                "sowing_date",
                gettext("The sowing date year must match the season year."),
            )

        if (
            sowing_date
            and planned_harvest_date
            and planned_harvest_date < sowing_date
        ):
            self.add_error(
                "planned_harvest_date",
                gettext("The planned harvest date cannot be earlier than the sowing date."),
            )

        if field and crop and season_year:
            duplicates = Cultivation.objects.filter(
                field=field, crop=crop, season_year=season_year
            )
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise ValidationError(
                    gettext("This crop is already assigned to this field and season.")
                )

        return cleaned_data


class CultivationChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, cultivation):
        return (
            f"{cultivation.field.name} — {cultivation.crop.name} "
            f"({cultivation.season_year})"
        )


class FieldWorkForm(SkipDuplicateModelErrorsMixin, forms.ModelForm):
    season_year = forms.TypedChoiceField(
        label=_("Season year"),
        choices=(),
        coerce=int,
        empty_value=None,
        help_text=_("Choose the season that matches the chosen cultivation."),
        error_messages={
            "required": _("Choose the season year."),
            "invalid_choice": _("The chosen season is not available."),
        },
    )
    cultivation = CultivationChoiceField(
        queryset=Cultivation.objects.none(),
        label=_("Cultivation"),
        help_text=_("Choose a cultivation grown on one of your fields."),
        error_messages={
            "required": _("Choose a cultivation."),
            "invalid_choice": _("The chosen cultivation is not available."),
        },
    )

    class Meta:
        model = FieldWork
        fields = (
            "season_year",
            "cultivation",
            "work_type",
            "work_date",
            "cost",
            "description",
        )
        labels = {
            "work_type": _("Work type"),
            "work_date": _("Work date"),
            "cost": _("Cost"),
            "description": _("Description"),
        }
        help_texts = {
            "work_date": _("Enter the date the work was done."),
            "cost": _("Cost cannot be negative."),
            "description": _("Optional description of the work."),
        }
        error_messages = {
            "work_type": {"required": _("Choose the work type.")},
            "work_date": {
                "required": _("Work date is required."),
                "invalid": _("Enter a valid work date."),
            },
            "cost": {
                "required": _("Cost is required."),
                "invalid": _("Enter a valid cost."),
            },
        }
        widgets = {
            "work_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        cultivations = (
            Cultivation.objects.filter(field__owner=user)
            .select_related("field", "crop")
            .order_by("-season_year", "field__name", "crop__name")
            if user is not None
            else Cultivation.objects.none()
        )
        self.fields["cultivation"].queryset = cultivations
        years = cultivations.order_by("-season_year").values_list(
            "season_year", flat=True
        ).distinct()
        self.fields["season_year"].choices = [(year, year) for year in years]
        initial_cultivation = self.initial.get("cultivation")
        if self.instance.pk:
            self.initial.setdefault(
                "season_year", self.instance.cultivation.season_year
            )
        elif isinstance(initial_cultivation, Cultivation):
            self.initial.setdefault("season_year", initial_cultivation.season_year)
        self.fields["work_date"].input_formats = ["%Y-%m-%d"]

    def clean(self):
        cleaned_data = super().clean()
        cultivation = cleaned_data.get("cultivation")
        season_year = cleaned_data.get("season_year")
        if (
            cultivation is not None
            and season_year is not None
            and cultivation.season_year != season_year
        ):
            self.add_error(
                "season_year",
                gettext("The chosen season does not match the season of the chosen cultivation."),
            )
        work_type = cleaned_data.get("work_type")
        work_date = cleaned_data.get("work_date")
        if (
            cultivation is not None
            and work_type == FieldWork.WorkType.SOWING
            and work_date is not None
            and work_date.year != cultivation.season_year
        ):
            self.add_error(
                "work_date",
                gettext("The sowing date year must match the cultivation season year."),
            )
        return cleaned_data

    def clean_cost(self):
        cost = self.cleaned_data["cost"]
        if cost < 0:
            raise ValidationError(gettext("Cost cannot be negative."))
        return cost


class SprayingForm(forms.ModelForm):
    cultivation = CultivationChoiceField(
        queryset=Cultivation.objects.none(),
        label=_("Cultivation"),
        help_text=_("Choose a cultivation grown on one of your fields."),
        error_messages={
            "required": _("Choose a cultivation."),
            "invalid_choice": _("The chosen cultivation is not available."),
        },
    )

    class Meta:
        model = Spraying
        fields = (
            "cultivation",
            "spraying_date",
            "product_name",
            "quantity",
            "unit",
            "cost",
            "description",
        )
        labels = {
            "spraying_date": _("Spraying date"),
            "product_name": _("Product name"),
            "quantity": _("Quantity"),
            "unit": _("Unit"),
            "cost": _("Cost"),
            "description": _("Description"),
        }
        help_texts = {
            "spraying_date": _("Enter the date of the spraying."),
            "product_name": _("Name of the product used, up to 150 characters."),
            "quantity": _("Quantity must be greater than zero."),
            "cost": _("Cost cannot be negative."),
            "description": _("Optional description of the spraying."),
        }
        error_messages = {
            "spraying_date": {
                "required": _("Spraying date is required."),
                "invalid": _("Enter a valid spraying date."),
            },
            "product_name": {
                "required": _("Product name is required."),
                "max_length": _("Product name can have at most 150 characters."),
            },
            "quantity": {
                "required": _("Product quantity is required."),
                "invalid": _("Enter a valid product quantity."),
            },
            "unit": {"required": _("Choose a unit.")},
            "cost": {
                "required": _("Cost is required."),
                "invalid": _("Enter a valid cost."),
            },
        }
        widgets = {
            "spraying_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            )
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cultivation"].queryset = (
            Cultivation.objects.filter(field__owner=user)
            .select_related("field", "crop")
            .order_by("-season_year", "field__name", "crop__name")
            if user is not None
            else Cultivation.objects.none()
        )
        self.fields["spraying_date"].input_formats = ["%Y-%m-%d"]

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity <= 0:
            raise ValidationError(gettext("Product quantity must be greater than zero."))
        return quantity

    def clean_cost(self):
        cost = self.cleaned_data["cost"]
        if cost < 0:
            raise ValidationError(gettext("Cost cannot be negative."))
        return cost


class HarvestForm(forms.ModelForm):
    cultivation = CultivationChoiceField(
        queryset=Cultivation.objects.none(),
        label=_("Cultivation"),
        help_text=_("Choose a cultivation grown on one of your fields."),
        error_messages={
            "required": _("Choose a cultivation."),
            "invalid_choice": _("The chosen cultivation is not available."),
        },
    )

    class Meta:
        model = Harvest
        fields = (
            "cultivation",
            "harvest_date",
            "quantity",
            "unit",
            "disposition",
            "revenue",
            "harvest_cost",
            "notes",
        )
        labels = {
            "harvest_date": _("Harvest date"),
            "quantity": _("Quantity"),
            "unit": _("Unit"),
            "disposition": _("Harvest disposition"),
            "revenue": _("Revenue"),
            "harvest_cost": _("Harvest cost"),
            "notes": _("Notes"),
        }
        help_texts = {
            "harvest_date": _("Enter the date of the harvest."),
            "quantity": _("Quantity must be greater than zero."),
            "disposition": _(
                "Say whether the harvest was sold, put into storage "
                "or discarded as a loss."
            ),
            "revenue": _("Revenue cannot be negative."),
            "harvest_cost": _("Harvest cost cannot be negative."),
            "notes": _("Optional notes about the harvest."),
        }
        error_messages = {
            "harvest_date": {
                "required": _("Harvest date is required."),
                "invalid": _("Enter a valid harvest date."),
            },
            "quantity": {
                "required": _("Harvest quantity is required."),
                "invalid": _("Enter a valid harvest quantity."),
            },
            "unit": {"required": _("Choose a unit.")},
            "disposition": {"required": _("Choose the harvest disposition.")},
            "revenue": {
                "required": _("Revenue is required."),
                "invalid": _("Enter a valid revenue."),
            },
            "harvest_cost": {
                "required": _("Harvest cost is required."),
                "invalid": _("Enter a valid harvest cost."),
            },
        }
        widgets = {
            "harvest_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            )
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cultivation"].queryset = (
            Cultivation.objects.filter(field__owner=user)
            .select_related("field", "crop")
            .order_by("-season_year", "field__name", "crop__name")
            if user is not None
            else Cultivation.objects.none()
        )
        self.fields["harvest_date"].input_formats = ["%Y-%m-%d"]

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity <= 0:
            raise ValidationError(gettext("Harvest quantity must be greater than zero."))
        return quantity

    def clean_revenue(self):
        revenue = self.cleaned_data["revenue"]
        if revenue < 0:
            raise ValidationError(gettext("Revenue cannot be negative."))
        return revenue

    def clean_harvest_cost(self):
        harvest_cost = self.cleaned_data["harvest_cost"]
        if harvest_cost < 0:
            raise ValidationError(gettext("Harvest cost cannot be negative."))
        return harvest_cost

    def clean(self):
        cleaned_data = super().clean()
        disposition = cleaned_data.get("disposition")
        revenue = cleaned_data.get("revenue")
        if (
            disposition
            and disposition != Harvest.Disposition.SOLD
            and revenue not in (None, 0)
        ):
            self.add_error(
                "revenue",
                gettext("Revenue must be 0 if the harvest was not sold."),
            )
        return cleaned_data


class CropForm(forms.ModelForm):
    DESCRIPTION_MAX_LENGTH = 1000

    class Meta:
        model = Crop
        fields = ("name", "description")
        labels = {
            "name": _("Crop type name"),
            "description": _("Description"),
        }
        help_texts = {
            "name": _(
                "Crop types are shared by all users. "
                "The name cannot be repeated."
            ),
            "description": _("Optional short description (up to 1000 characters)."),
        }
        error_messages = {
            "name": {
                "required": _("Crop type name is required."),
                "max_length": _("The name can have at most 100 characters."),
                "unique": _("A crop type with this name already exists."),
            },
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise ValidationError(gettext("Crop type name is required."))
        # Names are compared in Python with casefold(), so the check for Polish
        # letters (e.g. "Łubin" / "łubin") does not depend on database collation.
        normalized = name.casefold()
        existing_names = Crop.objects.values_list("name", flat=True)
        if any(existing.casefold() == normalized for existing in existing_names):
            raise ValidationError(gettext("A crop type with this name already exists."))
        return name

    def clean_description(self):
        description = self.cleaned_data.get("description", "").strip()
        if len(description) > self.DESCRIPTION_MAX_LENGTH:
            raise ValidationError(gettext("The description can have at most 1000 characters."))
        return description


# First line of a report prefilled with the page address, e.g. "Page: /fields/4/".
SOURCE_PAGE_LINE = re.compile(r"^[^\s:]+: /\S*")


ATTACHMENT_MAX_FILES = 3
ATTACHMENT_MAX_SIZE = 5 * 1024 * 1024
# Extensions a user may send, mapped to the file type their content must have.
ATTACHMENT_TYPES_BY_EXTENSION = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
}


def detect_attachment_type(uploaded_file):
    """File type read from the first bytes of the file, not from its name or the browser."""
    uploaded_file.seek(0)
    head = uploaded_file.read(16)
    uploaded_file.seek(0)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    return None


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A file field that accepts several files and returns them as a list."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleFileField, self).clean(item, initial) for item in files]


class ErrorReportForm(forms.ModelForm):
    attachments = MultipleFileField(
        label=_("Screenshots or PDF"),
        required=False,
        help_text=format_lazy(
            _("Optional. Up to {count} files: PNG, JPG, WEBP, GIF or PDF, each up to {size}."),
            count=ATTACHMENT_MAX_FILES, size="5 MB",
        ),
        widget=MultipleFileInput(attrs={
            "accept": ",".join(sorted(ATTACHMENT_TYPES_BY_EXTENSION)),
        }),
    )

    class Meta:
        model = ErrorReport
        fields = ("category", "description")
        labels = {
            "category": _("Report category"),
            "description": _("Problem description"),
        }
        help_texts = {
            "description": _("Describe the problem in at least 10 and at most 5000 characters."),
        }
        error_messages = {
            "category": {"required": _("Choose the report category.")},
            "description": {"required": _("Problem description is required.")},
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 8})}

    def clean_description(self):
        description = self.cleaned_data["description"].strip()
        # The page address filled in automatically is not a description on its own.
        own_text = SOURCE_PAGE_LINE.sub("", description).strip()
        if len(own_text) < 10:
            raise ValidationError(gettext("The description must have at least 10 characters."))
        if len(description) > 5000:
            raise ValidationError(gettext("The description cannot have more than 5000 characters."))
        return description

    def clean_attachments(self):
        files = self.cleaned_data.get("attachments") or []
        if len(files) > ATTACHMENT_MAX_FILES:
            raise ValidationError(
                gettext("You can attach at most %(count)s files.") % {"count": ATTACHMENT_MAX_FILES}
            )
        checked = []
        for uploaded in files:
            name = os.path.basename(uploaded.name or "")[:255] or "file"
            if uploaded.size > ATTACHMENT_MAX_SIZE:
                raise ValidationError(
                    gettext("The file %(name)s is larger than %(size)s.")
                    % {"name": name, "size": filesizeformat(ATTACHMENT_MAX_SIZE)}
                )
            extension = os.path.splitext(name)[1].lower()
            content_type = detect_attachment_type(uploaded)
            if (content_type is None
                    or ATTACHMENT_TYPES_BY_EXTENSION.get(extension) != content_type):
                raise ValidationError(
                    gettext("The file %(name)s is not a PNG, JPG, WEBP, GIF or PDF file.")
                    % {"name": name}
                )
            checked.append((uploaded, name, content_type))
        return checked

    def save(self, commit=True):
        if not commit:
            return super().save(commit=False)
        with transaction.atomic():
            report = super().save()
            for uploaded, name, content_type in self.cleaned_data.get("attachments", []):
                attachment = ErrorReportAttachment(
                    report=report, original_name=name, content_type=content_type,
                    size=uploaded.size,
                )
                attachment.file.save(ATTACHMENT_EXTENSIONS[content_type], uploaded, save=False)
                attachment.save()
        return report
