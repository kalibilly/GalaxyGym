from .models import Notification


def notification_context(request):
    if not request.user.is_authenticated:
        return {}

    unread_count = Notification.objects.filter(user=request.user, status=Notification.STATUS_UNREAD).count()
    recent_notifications = (
        Notification.objects.filter(user=request.user)
        .order_by('-created_at')[:5]
    )
    return {
        'notification_unread_count': unread_count,
        'notification_recent_notifications': recent_notifications,
    }
