from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from .services import get_dashboard_metrics


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_dashboard_metrics())
        return context
