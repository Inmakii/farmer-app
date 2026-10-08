import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils.text import format_lazy
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

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
            "parcel_identifier",
            "location_method",
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
            "parcel_identifier": _("Required when the location is a parcel."),
            "address": _("Required when the location is an address."),
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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

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

    def clean(self):
        cleaned_data = super().clean()
        location_method = cleaned_data.get("location_method")
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
        # SQLite compares case-insensitively only for ASCII, so Polish letters
        # (e.g. "Łubin" / "łubin") are compared in Python with casefold().
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


class ErrorReportForm(forms.ModelForm):
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
