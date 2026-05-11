from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'level', 'status', 'created_at', 'task_name')
    list_filter = ('status', 'level', 'created_at')
    search_fields = ('title', 'message', 'user__login_id', 'task_name')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
