from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import FormView, TemplateView
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy

from .forms import UserAccountCreationForm


class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('dashboard')


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('login')


@login_required(login_url='login')
def profile_view(request):
    return render(request, 'registration/profile.html')
