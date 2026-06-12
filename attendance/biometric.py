import abc
import logging
from typing import Any, Dict, Optional

from django.db import transaction
from django.utils import timezone

from members.models import Member
from staffs.models import Staff

from .models import (
    BiometricDevice,
    BiometricSyncLog,
    MemberBiometricDeviceStatus,
    StaffBiometricDeviceStatus,
)

logger = logging.getLogger('biometric')


class BiometricSyncError(Exception):
    pass


class BiometricAdapter(abc.ABC):
    device_type = BiometricDevice.DeviceType.UNKNOWN

    def __init__(self, device: BiometricDevice):
        self.device = device

    @classmethod
    def supports_device(cls, device: BiometricDevice) -> bool:
        return cls.device_type == device.device_type

    @classmethod
    def identify_from_device(cls, device: BiometricDevice) -> bool:
        return cls.supports_device(device)

    def probe_status(self) -> Dict[str, Any]:
        return {
            'ok': False,
            'device_type': self.device.device_type,
            'serial_number': self.device.serial_number,
            'message': 'Adapter implementation unavailable.',
        }

    def fetch_enrolled_users(self) -> Dict[str, Any]:
        return {
            'ok': False,
            'message': 'Fetch enrolled users not implemented for this device adapter.',
        }

    def push_enrollment(self, target: Any, device_user_id: str) -> Dict[str, Any]:
        return {
            'ok': False,
            'message': 'Enrollment push is not implemented for this device adapter.',
        }

    def delete_enrollment(self, target: Any, device_user_id: str) -> Dict[str, Any]:
        return {
            'ok': False,
            'message': 'Enrollment delete is not implemented for this device adapter.',
        }


class MB20Adapter(BiometricAdapter):
    device_type = BiometricDevice.DeviceType.MB20

    @classmethod
    def identify_from_device(cls, device: BiometricDevice) -> bool:
        normalized = (device.device_name or device.serial_number or '').lower()
        return 'mb20' in normalized or normalized.startswith('mb')

    def probe_status(self) -> Dict[str, Any]:
        return {
            'ok': True,
            'device_type': self.device.device_type,
            'serial_number': self.device.serial_number,
            'model': 'MB20',
            'message': 'MB20 device adapter is available. Implement device-specific communication for production use.',
        }


class AiFaceAdapter(BiometricAdapter):
    device_type = BiometricDevice.DeviceType.AIFACE

    @classmethod
    def identify_from_device(cls, device: BiometricDevice) -> bool:
        normalized = (device.device_name or device.serial_number or '').lower()
        return 'aiface' in normalized or normalized.startswith('af')

    def probe_status(self) -> Dict[str, Any]:
        return {
            'ok': True,
            'device_type': self.device.device_type,
            'serial_number': self.device.serial_number,
            'model': 'AiFace',
            'message': 'AiFace device adapter is available. Implement device-specific communication for production use.',
        }


class UnknownDeviceAdapter(BiometricAdapter):
    def probe_status(self) -> Dict[str, Any]:
        return {
            'ok': False,
            'device_type': self.device.device_type,
            'serial_number': self.device.serial_number,
            'message': 'Unknown biometric device type. Verify the device serial and device_name metadata.',
        }


def get_adapter_for_device(device: BiometricDevice) -> BiometricAdapter:
    if device.device_type == BiometricDevice.DeviceType.MB20 or MB20Adapter.identify_from_device(device):
        return MB20Adapter(device)
    if device.device_type == BiometricDevice.DeviceType.AIFACE or AiFaceAdapter.identify_from_device(device):
        return AiFaceAdapter(device)
    return UnknownDeviceAdapter(device)


class BiometricSyncService:
    def __init__(self, device: BiometricDevice):
        self.device = device
        self.adapter = get_adapter_for_device(device)

    def create_sync_log(
        self,
        action: str,
        payload: Any = None,
        response: Any = None,
        target: Optional[Any] = None,
        device_user_id: Optional[str] = None,
        success: bool = True,
        notes: str = '',
    ) -> BiometricSyncLog:
        person_type = ''
        if isinstance(target, Member):
            person_type = BiometricSyncLog.person_type.field.choices[0][0] if False else 'member'
        elif isinstance(target, Staff):
            person_type = 'staff'

        return BiometricSyncLog.objects.create(
            device=self.device,
            member=target if isinstance(target, Member) else None,
            staff=target if isinstance(target, Staff) else None,
            person_type=person_type,
            action=action,
            device_user_id=device_user_id or '',
            success=success,
            payload=str(payload) if payload is not None else '',
            response=str(response) if response is not None else '',
            notes=notes or '',
        )

    def resolve_software_target(self, device_user_id: str):
        if not device_user_id:
            return None

        member = Member.objects.filter(device_user_id=device_user_id).first()
        if member:
            return member

        staff = Staff.objects.filter(device_user_id=device_user_id).first()
        if staff:
            return staff

        return None

    def assign_device_user_id(self, target: Any, device_user_id: str) -> bool:
        if not device_user_id or not target:
            raise BiometricSyncError('Missing target or device_user_id for assignment.')

        existing_target = self.resolve_software_target(device_user_id)
        if existing_target and (
            existing_target.__class__ != target.__class__ or existing_target.pk != target.pk
        ):
            raise BiometricSyncError(
                f'Device user ID {device_user_id} is already assigned to another account.'
            )

        current_target_id = getattr(target, 'device_user_id', None)
        if current_target_id and current_target_id != device_user_id:
            raise BiometricSyncError(
                'Software master mapping conflict: target already has a different device_user_id.'
            )

        target.device_user_id = device_user_id
        target.save(update_fields=['device_user_id'])
        return True

    def reconcile_device_user(self, target: Any, reported_device_user_id: str) -> Dict[str, Any]:
        if not target or not reported_device_user_id:
            raise BiometricSyncError('Both target and reported device_user_id are required.')

        current_id = getattr(target, 'device_user_id', None)
        if not current_id:
            existing_target = self.resolve_software_target(reported_device_user_id)
            if existing_target and (
                existing_target.__class__ != target.__class__ or existing_target.pk != target.pk
            ):
                return {
                    'ok': False,
                    'reason': 'Reported device_user_id is already assigned to another software account.',
                }
            self.assign_device_user_id(target, reported_device_user_id)
            return {
                'ok': True,
                'action': 'assigned',
                'device_user_id': reported_device_user_id,
            }

        if current_id != reported_device_user_id:
            return {
                'ok': False,
                'reason': 'Software authoritatively owns the target mapping. Device-reported ID does not match the existing assignment.',
                'expected_device_user_id': current_id,
            }

        return {
            'ok': True,
            'action': 'verified',
            'device_user_id': current_id,
        }

    def _update_status_after_push(self, target: Any, result: Dict[str, Any], device_user_id: str):
        if isinstance(target, Member):
            status_obj, _ = MemberBiometricDeviceStatus.objects.get_or_create(
                member=target,
                device=self.device,
                defaults={'device_user_id': device_user_id},
            )
        elif isinstance(target, Staff):
            status_obj, _ = StaffBiometricDeviceStatus.objects.get_or_create(
                staff=target,
                device=self.device,
                defaults={'device_user_id': device_user_id},
            )
        else:
            return

        if not status_obj.device_user_id:
            status_obj.device_user_id = device_user_id

        status_obj.last_status_checked_at = timezone.now()

        if result.get('ok'):
            status_obj.sync_status = status_obj.SyncStatus.SUCCESS
            status_obj.is_enabled_on_device = True
            status_obj.last_synced_at = timezone.now()
            status_obj.last_error = ''
        else:
            status_obj.sync_status = status_obj.SyncStatus.FAILED
            status_obj.is_enabled_on_device = False
            status_obj.last_error = result.get('message', 'Enrollment failed.')

        if 'face_added' in result:
            status_obj.face_added = bool(result['face_added'])
        if 'fingerprint_added' in result:
            status_obj.fingerprint_added = bool(result['fingerprint_added'])
        if 'password_added' in result:
            status_obj.password_added = bool(result['password_added'])

        update_fields = [
            'device_user_id',
            'last_status_checked_at',
            'sync_status',
            'is_enabled_on_device',
            'last_synced_at',
            'last_error',
            'face_added',
            'fingerprint_added',
            'password_added',
        ]
        status_obj.save(update_fields=update_fields)

    def push_enrollment(self, target: Any, device_user_id: str) -> Dict[str, Any]:
        if isinstance(self.adapter, UnknownDeviceAdapter):
            result = self.adapter.push_enrollment(target, device_user_id)
            self.create_sync_log(
                action=BiometricSyncLog.Action.ENROLLMENT,
                payload={'target': str(target), 'device_user_id': device_user_id},
                response=result,
                target=target,
                device_user_id=device_user_id,
                success=result.get('ok', False),
                notes='Adapter does not support enrollment yet.',
            )
            self._update_status_after_push(target, result, device_user_id)
            return result

        assignment = self.reconcile_device_user(target, device_user_id)
        if not assignment['ok']:
            self.create_sync_log(
                action=BiometricSyncLog.Action.CONFLICT,
                payload={'target': str(target), 'reported_device_user_id': device_user_id},
                response=assignment,
                target=target,
                device_user_id=device_user_id,
                success=False,
                notes='Conflict while reconciling device user mapping.',
            )
            self._update_status_after_push(
                target,
                {'ok': False, 'message': assignment.get('reason', 'Conflict while reconciling mapping.')},
                device_user_id,
            )
            return assignment

        result = self.adapter.push_enrollment(target, device_user_id)
        self.create_sync_log(
            action=BiometricSyncLog.Action.ENROLLMENT,
            payload={'target': str(target), 'device_user_id': device_user_id},
            response=result,
            target=target,
            device_user_id=device_user_id,
            success=result.get('ok', False),
        )
        self._update_status_after_push(target, result, device_user_id)
        return result

    def probe(self) -> Dict[str, Any]:
        status = self.adapter.probe_status()
        self.device.last_sync_at = timezone.now()
        self.device.save(update_fields=['last_sync_at'])
        self.create_sync_log(
            action=BiometricSyncLog.Action.DEVICE_HEARTBEAT,
            payload={'status': status},
            response=status,
            device_user_id='',
        )
        return status

    @transaction.atomic
    def synchronize_device(self) -> Dict[str, Any]:
        if isinstance(self.adapter, UnknownDeviceAdapter):
            message = 'Unknown device adapter. No active sync available.'
            self.create_sync_log(
                action=BiometricSyncLog.Action.DEVICE_SYNC,
                payload={'reason': message},
                response={'ok': False, 'message': message},
                success=False,
            )
            return {'ok': False, 'message': message}

        enrolled = self.adapter.fetch_enrolled_users()
        self.create_sync_log(
            action=BiometricSyncLog.Action.DEVICE_SYNC,
            payload={'fetch_enrolled_users': enrolled},
            response=enrolled,
            success=enrolled.get('ok', False),
        )
        return enrolled
