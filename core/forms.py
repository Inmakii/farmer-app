from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError


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
