from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import Crop, Cultivation, Field, FieldWork


class RegistrationForm(UserCreationForm):
    error_messages = {
        "password_mismatch": "Podane hasła nie są takie same.",
    }

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email")
        labels = {
            "username": "Nazwa użytkownika",
            "first_name": "Imię",
            "last_name": "Nazwisko",
            "email": "Adres e-mail",
        }
        error_messages = {
            "username": {
                "required": "Nazwa użytkownika jest wymagana.",
                "unique": "Użytkownik o tej nazwie już istnieje.",
            },
            "first_name": {"required": "Imię jest wymagane."},
            "last_name": {"required": "Nazwisko jest wymagane."},
            "email": {
                "required": "Adres e-mail jest wymagany.",
                "invalid": "Podaj poprawny adres e-mail.",
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        required_fields = {
            "username": "Nazwa użytkownika",
            "first_name": "Imię",
            "last_name": "Nazwisko",
            "email": "Adres e-mail",
            "password1": "Hasło",
            "password2": "Powtórz hasło",
        }
        for field_name, label in required_fields.items():
            self.fields[field_name].required = True
            self.fields[field_name].label = label
            self.fields[field_name].error_messages["required"] = (
                f"Pole „{label}” jest wymagane."
            )

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        user_model = get_user_model()
        if user_model._default_manager.filter(email__iexact=email).exists():
            raise ValidationError(
                "Użytkownik z tym adresem e-mail już istnieje."
            )
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
            "name": "Nazwa pola",
            "area_ha": "Powierzchnia (ha)",
            "soil_type": "Rodzaj gleby",
            "parcel_identifier": "Identyfikator działki",
            "location_method": "Sposób określenia lokalizacji",
            "address": "Adres",
            "latitude": "Szerokość geograficzna",
            "longitude": "Długość geograficzna",
            "description": "Opis",
        }
        help_texts = {
            "name": "Nazwa musi być unikalna wśród Twoich pól.",
            "area_ha": "Podaj dodatnią powierzchnię w hektarach.",
            "parcel_identifier": "Wymagany przy lokalizacji według działki.",
            "address": "Wymagany przy lokalizacji według adresu.",
            "latitude": "Wymagana dla GPS i punktu na mapie; zakres od -90 do 90.",
            "longitude": "Wymagana dla GPS i punktu na mapie; zakres od -180 do 180.",
        }
        error_messages = {
            "name": {"required": "Nazwa pola jest wymagana."},
            "area_ha": {
                "required": "Powierzchnia pola jest wymagana.",
                "invalid": "Podaj poprawną powierzchnię pola.",
            },
            "soil_type": {"required": "Wybierz rodzaj gleby."},
            "location_method": {"required": "Wybierz sposób lokalizacji."},
            "latitude": {"invalid": "Podaj poprawną szerokość geograficzną."},
            "longitude": {"invalid": "Podaj poprawną długość geograficzną."},
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
                raise ValidationError("Masz już pole o tej nazwie.")
        return name

    def clean_area_ha(self):
        area_ha = self.cleaned_data["area_ha"]
        if area_ha <= 0:
            raise ValidationError("Powierzchnia pola musi być większa od zera.")
        return area_ha

    def clean(self):
        cleaned_data = super().clean()
        location_method = cleaned_data.get("location_method")
        address = cleaned_data.get("address")
        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")
        parcel_identifier = cleaned_data.get("parcel_identifier")

        if location_method == Field.LocationMethod.ADDRESS and not address:
            self.add_error("address", "Adres jest wymagany dla tej metody lokalizacji.")
        if location_method in (Field.LocationMethod.GPS, Field.LocationMethod.MAP):
            if latitude is None:
                self.add_error(
                    "latitude", "Szerokość geograficzna jest wymagana dla tej lokalizacji."
                )
            if longitude is None:
                self.add_error(
                    "longitude", "Długość geograficzna jest wymagana dla tej lokalizacji."
                )
        if location_method == Field.LocationMethod.PARCEL and not parcel_identifier:
            self.add_error(
                "parcel_identifier",
                "Identyfikator działki jest wymagany dla tej metody lokalizacji.",
            )

        return cleaned_data


class CultivationForm(forms.ModelForm):
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
            "field": "Pole",
            "crop": "Rodzaj uprawy",
            "season_year": "Rok sezonu",
            "status": "Status",
            "sowing_date": "Data siewu",
            "planned_harvest_date": "Planowana data zbioru",
            "notes": "Notatki",
        }
        help_texts = {
            "field": "Możesz wybrać wyłącznie jedno ze swoich pól.",
            "season_year": "Dozwolony zakres lat: 2000–2100.",
            "sowing_date": "Opcjonalna data rozpoczęcia siewu.",
            "planned_harvest_date": "Nie może być wcześniejsza od daty siewu.",
        }
        error_messages = {
            "field": {
                "required": "Wybierz pole.",
                "invalid_choice": "Wybrane pole jest niedostępne.",
            },
            "crop": {
                "required": "Wybierz rodzaj uprawy.",
                "invalid_choice": "Wybrany rodzaj uprawy jest niedostępny.",
            },
            "season_year": {
                "required": "Rok sezonu jest wymagany.",
                "invalid": "Podaj poprawny rok sezonu.",
            },
            "status": {"required": "Wybierz status uprawy."},
            "sowing_date": {"invalid": "Podaj poprawną datę siewu."},
            "planned_harvest_date": {
                "invalid": "Podaj poprawną planowaną datę zbioru."
            },
        }
        widgets = {
            "sowing_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "planned_harvest_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
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
        self.fields["sowing_date"].input_formats = ["%Y-%m-%d"]
        self.fields["planned_harvest_date"].input_formats = ["%Y-%m-%d"]

    def clean_season_year(self):
        season_year = self.cleaned_data["season_year"]
        if not 2000 <= season_year <= 2100:
            raise ValidationError("Rok sezonu musi mieścić się w zakresie 2000–2100.")
        return season_year

    def clean(self):
        cleaned_data = super().clean()
        field = cleaned_data.get("field")
        crop = cleaned_data.get("crop")
        season_year = cleaned_data.get("season_year")
        sowing_date = cleaned_data.get("sowing_date")
        planned_harvest_date = cleaned_data.get("planned_harvest_date")

        if (
            sowing_date
            and planned_harvest_date
            and planned_harvest_date < sowing_date
        ):
            self.add_error(
                "planned_harvest_date",
                "Planowana data zbioru nie może być wcześniejsza od daty siewu.",
            )

        if field and crop and season_year:
            duplicates = Cultivation.objects.filter(
                field=field, crop=crop, season_year=season_year
            )
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise ValidationError(
                    "Taka uprawa jest już przypisana do tego pola i sezonu."
                )

        return cleaned_data


class CultivationChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, cultivation):
        return (
            f"{cultivation.field.name} — {cultivation.crop.name} "
            f"({cultivation.season_year})"
        )


class FieldWorkForm(forms.ModelForm):
    cultivation = CultivationChoiceField(
        queryset=Cultivation.objects.none(),
        label="Uprawa",
        help_text="Wybierz uprawę prowadzoną na jednym ze swoich pól.",
        error_messages={
            "required": "Wybierz uprawę.",
            "invalid_choice": "Wybrana uprawa jest niedostępna.",
        },
    )

    class Meta:
        model = FieldWork
        fields = ("cultivation", "work_type", "work_date", "cost", "description")
        labels = {
            "work_type": "Rodzaj pracy",
            "work_date": "Data wykonania",
            "cost": "Koszt",
            "description": "Opis",
        }
        help_texts = {
            "work_date": "Podaj datę wykonania pracy.",
            "cost": "Koszt nie może być ujemny.",
            "description": "Opcjonalny opis wykonanej pracy.",
        }
        error_messages = {
            "work_type": {"required": "Wybierz rodzaj pracy."},
            "work_date": {
                "required": "Data wykonania jest wymagana.",
                "invalid": "Podaj poprawną datę wykonania.",
            },
            "cost": {
                "required": "Koszt jest wymagany.",
                "invalid": "Podaj poprawny koszt.",
            },
        }
        widgets = {
            "work_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
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
        self.fields["work_date"].input_formats = ["%Y-%m-%d"]

    def clean_cost(self):
        cost = self.cleaned_data["cost"]
        if cost < 0:
            raise ValidationError("Koszt nie może być ujemny.")
        return cost
