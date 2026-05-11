from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, View

from .models import Notification


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def get_queryset(self):
        return (
            Notification.objects
            .filter(user=self.request.user)
            .order_by('-created_at')
        )


class NotificationMarkReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        notification.mark_read()
        return redirect(request.POST.get('next', reverse_lazy('notifications:list')))


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    def post(self, request):
        Notification.objects.filter(user=request.user, status=Notification.STATUS_UNREAD).update(status=Notification.STATUS_READ)
        return redirect(request.POST.get('next', reverse_lazy('notifications:list')))
