import json
import logging
from typing import Any, Dict, Optional
import requests
from django.db import transaction
from django.utils import timezone

from members.models import Member
from staffs.models import Staff

from .models import (
    AttendanceLog,
    BiometricDevice,
    BiometricDeviceCommand,
    BiometricSyncLog,
    DeviceUserLink,
    MemberBiometricDeviceStatus,
    StaffBiometricDeviceStatus,
)

logger = logging.getLogger('biometric')


class BiometricSyncError(Exception):
    pass


class BiometricSyncService:
    def __init__(self, device: BiometricDevice):
        self.device = device

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
            person_type = AttendanceLog.PersonType.MEMBER
        elif isinstance(target, Staff):
            person_type = AttendanceLog.PersonType.STAFF

        return BiometricSyncLog.objects.create(
            device=self.device,
            member=target if isinstance(target, Member) else None,
            staff=target if isinstance(target, Staff) else None,
            person_type=person_type,
            action=action,
            device_user_id=device_user_id or '',
            success=success,
            payload=json.dumps(payload, default=str) if payload is not None else '',
            response=json.dumps(response, default=str) if response is not None else '',
            notes=notes or '',
        )
    
    def push_to_ebioserver(self, member):
    try:
        payload = {
            "UserName": "admin",
            "Password": "admin",
            "EmployeeCode": member.member_id,
            "EmployeeName": member.full_name,
            "EmployeeLocation": "GYM",
            "EmployeeRole": "Normal User",
            "EmployeeVerificationType": "0",
        }

        response = requests.post(
            "http://localhost:85/iclock/webservice.asmx/UpdateEmployee",
            data=payload,
            timeout=20,
        )

        if "success" in response.text.lower():
            return {
                "ok": True,
                "message": "Member synced through eBioServer.",
            }

        return {
            "ok": False,
            "message": response.text,
        }

    except Exception as exc:
        return {
            "ok": False,
            "message": str(exc),
        }

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
            raise BiometricSyncError('Both target and reported_device_user_id are required.')

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

    def _get_member_status(self, member: Member):
        status_obj, _ = MemberBiometricDeviceStatus.objects.get_or_create(
            member=member,
            device=self.device,
            defaults={'device_user_id': member.device_user_id or member.member_id},
        )
        expected_id = member.device_user_id or member.member_id
        if expected_id and status_obj.device_user_id != expected_id:
            status_obj.device_user_id = expected_id
            status_obj.save(update_fields=['device_user_id'])
        return status_obj

    def _get_staff_status(self, staff: Staff):
        status_obj, _ = StaffBiometricDeviceStatus.objects.get_or_create(
            staff=staff,
            device=self.device,
            defaults={'device_user_id': staff.device_user_id or staff.staff_id},
        )
        expected_id = staff.device_user_id or staff.staff_id
        if expected_id and status_obj.device_user_id != expected_id:
            status_obj.device_user_id = expected_id
            status_obj.save(update_fields=['device_user_id'])
        return status_obj

    def _ensure_link(self, target: Any, device_user_id: str):
        if not device_user_id:
            return None

        if isinstance(target, Member):
            link, _ = DeviceUserLink.objects.get_or_create(
                device_user_id=device_user_id,
                defaults={
                    'member': target,
                    'person_type': DeviceUserLink.PersonType.MEMBER,
                    'is_active': True,
                },
            )
            if link.member_id != target.id or link.staff_id is not None or not link.is_active:
                link.member = target
                link.staff = None
                link.person_type = DeviceUserLink.PersonType.MEMBER
                link.is_active = True
                link.save(update_fields=['member', 'staff', 'person_type', 'is_active'])
            return link

        if isinstance(target, Staff):
            link, _ = DeviceUserLink.objects.get_or_create(
                device_user_id=device_user_id,
                defaults={
                    'staff': target,
                    'person_type': DeviceUserLink.PersonType.STAFF,
                    'is_active': True,
                },
            )
            if link.staff_id != target.id or link.member_id is not None or not link.is_active:
                link.staff = target
                link.member = None
                link.person_type = DeviceUserLink.PersonType.STAFF
                link.is_active = True
                link.save(update_fields=['staff', 'member', 'person_type', 'is_active'])
            return link

        return None

    def push_enrollment(self, target: Any, device_user_id: str) -> Dict[str, Any]:
        if (
            self.device.device_type
            == BiometricDevice.DeviceType.AIFACE
        ):
    return self.push_to_ebioserver(target)

        if not target or not device_user_id:
            return {'ok': False, 'message': 'Target and device_user_id are required.'}

        try:
            assignment = self.reconcile_device_user(target, device_user_id)
        except BiometricSyncError as exc:
            return {'ok': False, 'message': str(exc)}

        if not assignment.get('ok'):
            self.create_sync_log(
                action=BiometricSyncLog.Action.CONFLICT,
                payload={'target': str(target), 'device_user_id': device_user_id},
                response=assignment,
                target=target,
                device_user_id=device_user_id,
                success=False,
                notes='Conflict while reconciling device user mapping.',
            )
            return assignment

        if isinstance(target, Member):
            status_obj = self._get_member_status(target)
        else:
            status_obj = self._get_staff_status(target)

        payload = {
            'target': str(target),
            'device_user_id': device_user_id,
            'device_serial': self.device.serial_number,
            'device_name': self.device.device_name,
        }

        command = BiometricDeviceCommand.objects.create(
            device=self.device,
            member=target if isinstance(target, Member) else None,
            staff=target if isinstance(target, Staff) else None,
            person_type=AttendanceLog.PersonType.MEMBER if isinstance(target, Member) else AttendanceLog.PersonType.STAFF,
            command=BiometricDeviceCommand.CommandType.SYNC_USER,
            device_user_id=device_user_id,
            payload=json.dumps(payload, default=str),
            status=BiometricDeviceCommand.Status.PENDING,
            queued_at=timezone.now(),
            notes='Queued for device polling.',
        )

        status_obj.sync_status = status_obj.SyncStatus.PENDING
        status_obj.last_status_checked_at = timezone.now()
        status_obj.last_error = ''
        status_obj.notes = 'Enrollment queued and waiting for device poll.'
        status_obj.save(update_fields=['sync_status', 'last_status_checked_at', 'last_error', 'notes'])

        self._ensure_link(target, device_user_id)

        result = {
            'ok': True,
            'queued': True,
            'message': 'Enrollment command queued successfully.',
            'command_id': command.pk,
            'device_serial': self.device.serial_number,
            'device_user_id': device_user_id,
        }

        self.create_sync_log(
            action=BiometricSyncLog.Action.ENROLLMENT,
            payload=payload,
            response=result,
            target=target,
            device_user_id=device_user_id,
            success=True,
            notes='Enrollment queued for device polling.',
        )
        return result

    def probe(self) -> Dict[str, Any]:
        result = {
            'ok': True,
            'device_type': self.device.device_type,
            'serial_number': self.device.serial_number,
            'device_name': self.device.device_name,
            'last_seen_at': self.device.last_seen_at.isoformat() if self.device.last_seen_at else None,
            'last_known_ip': self.device.last_known_ip,
            'message': 'Device record is available. Use heartbeat timestamps to verify communication.',
        }
        self.device.last_sync_at = timezone.now()
        self.device.save(update_fields=['last_sync_at'])
        self.create_sync_log(
            action=BiometricSyncLog.Action.DEVICE_HEARTBEAT,
            payload={'status_check': True},
            response=result,
            success=True,
        )
        return result

    @transaction.atomic
    def synchronize_device(self) -> Dict[str, Any]:
        result = {
            'ok': True,
            'message': 'Synchronization uses queued commands and device callbacks in this integration.',
            'device_serial': self.device.serial_number,
        }
        self.create_sync_log(
            action=BiometricSyncLog.Action.DEVICE_SYNC,
            payload={'mode': 'queued-command-polling'},
            response=result,
            success=True,
        )
        return result
