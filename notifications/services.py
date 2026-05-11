from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import UserAccount
from .models import Notification


def create_notification_for_user(user, title, message, link=None, level=Notification.LEVEL_INFO, task_name=None):
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        link=link or '',
        level=level,
        status=Notification.STATUS_UNREAD,
        task_name=task_name or '',
    )


def notify_owners(title, message, link=None, level=Notification.LEVEL_INFO, task_name=None):
    owner_users = UserAccount.objects.filter(role=UserAccount.ROLE_OWNER, is_active=True)
    notifications = []
    for owner in owner_users:
        notifications.append(
            Notification(
                user=owner,
                title=title,
                message=message,
                link=link or '',
                level=level,
                status=Notification.STATUS_UNREAD,
                task_name=task_name or '',
            )
        )
    if notifications:
        with transaction.atomic():
            Notification.objects.bulk_create(notifications)
    return notifications


def task_started(user, title, message, link=None, task_name=None):
    return create_notification_for_user(
        user,
        title=f'Started: {title}',
        message=message,
        link=link,
        level=Notification.LEVEL_INFO,
        task_name=task_name,
    )


def task_completed(user, title, message, link=None, task_name=None):
    return create_notification_for_user(
        user,
        title=f'Completed: {title}',
        message=message,
        link=link,
        level=Notification.LEVEL_SUCCESS,
        task_name=task_name,
    )


def task_failed(user, title, message, link=None, task_name=None):
    return create_notification_for_user(
        user,
        title=f'Failed: {title}',
        message=message,
        link=link,
        level=Notification.LEVEL_DANGER,
        task_name=task_name,
    )
