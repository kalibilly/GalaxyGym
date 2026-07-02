from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.db import transaction

from .models import Invoice


@receiver(pre_save, sender=Invoice)
def invoice_status_change(sender, instance, **kwargs):
    """When an invoice transitions to OVERDUE, trigger biometric re-evaluation for the member.

    Uses transaction.on_commit to ensure the DB change is persisted first.
    """
    if not instance.pk:
        return

    try:
        old = Invoice.objects.get(pk=instance.pk)
    except Invoice.DoesNotExist:
        return

    old_status = getattr(old, "status", None)
    new_status = getattr(instance, "status", None)

    if old_status != new_status and new_status == Invoice.STATUS_OVERDUE:
        def _push():
            # Import locally to avoid import-time cycles
            from attendance.models import BiometricDevice
            from attendance.biometric import BiometricSyncService

            devices = BiometricDevice.objects.filter(device_type=BiometricDevice.DeviceType.AIFACE, is_active=True)
            for device in devices:
                service = BiometricSyncService(device)
                try:
                    service.push_enrollment(instance.member, instance.member.member_id)
                except Exception:
                    # swallow errors; they will be logged by the service
                    pass

        transaction.on_commit(_push)
