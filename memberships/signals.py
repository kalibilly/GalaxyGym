from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.db import transaction

from .models import Membership


@receiver(pre_save, sender=Membership)
def membership_status_change(sender, instance, **kwargs):
    """When a membership transitions to EXPIRED, trigger biometric re-evaluation for the member.

    Uses transaction.on_commit to ensure the DB change is persisted first.
    """
    if not instance.pk:
        return

    try:
        old = Membership.objects.get(pk=instance.pk)
    except Membership.DoesNotExist:
        return

    old_status = getattr(old, "status", None)
    new_status = getattr(instance, "status", None)

    if old_status != new_status and new_status == Membership.STATUS_EXPIRED:
        def _push():
            from attendance.models import BiometricDevice
            from attendance.biometric import BiometricSyncService

            devices = BiometricDevice.objects.filter(device_type=BiometricDevice.DeviceType.AIFACE, is_active=True)
            member = instance.member
            for device in devices:
                service = BiometricSyncService(device)
                try:
                    service.push_enrollment(member, member.member_id)
                except Exception:
                    pass

        transaction.on_commit(_push)
