from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views.generic import FormView

from .forms import LoginForm, SignupRequestForm, UserProfileForm
from .models import UserAccount


class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        role = getattr(self.request.user, 'role', None)
        if role == UserAccount.ROLE_OWNER:
            return reverse_lazy('dashboard')
        if role == UserAccount.ROLE_STAFF:
            return reverse_lazy('dashboard')
        return reverse_lazy('dashboard')


class SignupRequestView(FormView):
    """
    View for users to submit a signup request.
    Request is saved but account is not created until admin approval.
    """
    template_name = 'registration/signup.html'
    form_class = SignupRequestForm
    success_url = reverse_lazy('signup_success')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        messages.success(
            self.request,
            'Your signup request has been submitted successfully. '
            'The gym will verify your details and notify you on WhatsApp within 1-2 business days.'
        )
        return super().form_valid(form)


def signup_success_view(request):
    """
    Success page after signup request submission.
    """
    return render(request, 'registration/signup_success.html')


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('home')


@login_required(login_url='login')
def profile_view(request):
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile was updated successfully.')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)

    return render(request, 'registration/profile.html', {'form': form})

