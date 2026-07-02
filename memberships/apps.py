from django.apps import AppConfig


class MembershipsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'memberships'
    verbose_name = 'Memberships'

    def ready(self):
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass
