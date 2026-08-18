from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from .forms import RegistrationForm


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
