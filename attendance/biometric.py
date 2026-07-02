import base64
import json
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

import requests
from django.conf import settings
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

logger = logging.getLogger("biometric")


class BiometricSyncError(Exception):
    pass


class BiometricSyncService:
    """Service for syncing users with eBioServer (SOAP 1.1).

    Uses settings.EBIOSERVER_BASE_URL, settings.EBIOSERVER_USER and
    settings.EBIOSERVER_PASSWORD to authenticate. Constructs SOAP XML
    for UpdateEmployeeEx and DeleteEmployee endpoints.
    """

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
        notes: str = "",
    ) -> BiometricSyncLog:
        person_type = ""
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
            device_user_id=device_user_id or "",
            success=success,
            payload=json.dumps(payload, default=str) if payload is not None else "",
            response=json.dumps(response, default=str) if response is not None else "",
            notes=notes or "",
        )

    def push_to_ebioserver(self, member):
        # Deprecated convenience method retained for compatibility.
        return {
            "ok": False,
            "message": "Use update_employee_ex or delete_employee instead.",
        }

    def _employee_code(self, target: Any) -> str:
        if not target:
            return ""
        return (
            getattr(target, "device_user_id", None)
            or getattr(target, "member_id", None)
            or getattr(target, "staff_id", "")
        )

    def _employee_location(self, target: Any) -> str:
        try:
            if (
                hasattr(target, "assigned_staff")
                and target.assigned_staff
                and getattr(target.assigned_staff, "department", None)
            ):
                dept = target.assigned_staff.department
                return getattr(dept, "name", "Main Gym") or "Main Gym"

            if hasattr(target, "department") and getattr(target, "department", None):
                return getattr(target.department, "name", "Main Gym") or "Main Gym"
        except Exception:
            pass
        return "Main Gym"

    def _employee_role(self, target: Any) -> str:
        return "Member" if isinstance(target, Member) else "Staff"

    def _employee_verification_type(self) -> str:
        return "1"

    def _format_date(self, d):
        if not d:
            return timezone.localdate().strftime("%Y-%m-%d")
        return d.strftime("%Y-%m-%d")

    def _employee_expiry_range(self, target: Any):
        today = timezone.localdate()
        expiry_from = today
        expiry_to = today

        active = getattr(target, "active_membership", None)
        if active:
            try:
                expiry_from = active.start_date or today
                expiry_to = active.end_date or today
            except Exception:
                expiry_from = today
                expiry_to = today

        if not active or expiry_to < today:
            expiry_to = today - timedelta(days=1)

        return self._format_date(expiry_from), self._format_date(expiry_to)

    def _employee_card_number(self, target: Any) -> str:
        return getattr(target, "card_number", "") or ""

    def _employee_photo_b64(self, target: Any) -> str:
        if not hasattr(target, "photo") or not getattr(target, "photo"):
            return ""
        try:
            f = target.photo.open("rb")
            data = f.read()
            f.close()
            return base64.b64encode(data).decode("ascii")
        except Exception:
            return ""

    def _soap_post(
        self,
        op_path: str,
        soap_action: str,
        body_xml: str,
        timeout: int = 20,
    ) -> Dict[str, Any]:
        base = getattr(settings, "EBIOSERVER_BASE_URL", "").rstrip("/")
        if not base:
            raise BiometricSyncError(
                "EBIOSERVER_BASE_URL is not configured in settings."
            )

        url = f"{base}{op_path}"
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": soap_action,
        }

        try:
            resp = requests.post(
                url,
                data=body_xml.encode("utf-8"),
                headers=headers,
                timeout=timeout,
            )
            return {
                "ok": True,
                "status_code": resp.status_code,
                "text": resp.text,
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def _build_updateemployeeex_xml(self, target: Any) -> str:
        user = getattr(settings, "EBIOSERVER_USER", "")
        pwd = getattr(settings, "EBIOSERVER_PASSWORD", "")

        emp_code = self._employee_code(target)
        emp_name = getattr(target, "full_name", "") or ""
        emp_loc = self._employee_location(target)
        emp_role = self._employee_role(target)
        ver_type = self._employee_verification_type()
        expiry_from, expiry_to = self._employee_expiry_range(target)
        card = self._employee_card_number(target)
        group_id = "1"
        photo_b64 = self._employee_photo_b64(target)

        xml = f"""<?xml version='1.0' encoding='utf-8'?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <UpdateEmployeeEx xmlns="http://tempuri.org/">
      <UserName>{user}</UserName>
      <Password>{pwd}</Password>
      <EmployeeCode>{emp_code}</EmployeeCode>
      <EmployeeName>{emp_name}</EmployeeName>
      <EmployeeLocation>{emp_loc}</EmployeeLocation>
      <EmployeeRole>{emp_role}</EmployeeRole>
      <EmployeeVerificationType>{ver_type}</EmployeeVerificationType>
      <EmployeeExpiryFrom>{expiry_from}</EmployeeExpiryFrom>
      <EmployeeExpiryTo>{expiry_to}</EmployeeExpiryTo>
      <EmployeeCardNumber>{card}</EmployeeCardNumber>
      <GroupId>{group_id}</GroupId>
      <EmployeePhoto>{photo_b64}</EmployeePhoto>
    </UpdateEmployeeEx>
  </soap:Body>
</soap:Envelope>"""
        return xml

    def _build_deleteemployee_xml(self, employee_code: str) -> str:
        user = getattr(settings, "EBIOSERVER_USER", "")
        pwd = getattr(settings, "EBIOSERVER_PASSWORD", "")

        xml = f"""<?xml version='1.0' encoding='utf-8'?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <DeleteEmployee xmlns="http://tempuri.org/">
      <UserName>{user}</UserName>
      <Password>{pwd}</Password>
      <EmployeeCode>{employee_code}</EmployeeCode>
    </DeleteEmployee>
  </soap:Body>
</soap:Envelope>"""
        return xml

    def update_employee_ex(self, target: Any) -> Dict[str, Any]:
        xml = self._build_updateemployeeex_xml(target)
        op_path = "/iclock/webservice.asmx?op=UpdateEmployeeEx"
        soap_action = "http://tempuri.org/UpdateEmployeeEx"
        result = self._soap_post(op_path, soap_action, xml)

        self.create_sync_log(
            action=BiometricSyncLog.Action.ENROLLMENT,
            payload=xml,
            response=result,
            target=target,
            device_user_id=self._employee_code(target),
            success=bool(result.get("ok")),
        )
        return result

    def delete_employee(
        self,
        target_or_code,
        target: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if isinstance(target_or_code, str):
            employee_code = target_or_code
        else:
            employee_code = self._employee_code(target_or_code)
            if not target:
                target = target_or_code

        xml = self._build_deleteemployee_xml(employee_code)
        op_path = "/iclock/webservice.asmx?op=DeleteEmployee"
        soap_action = "http://tempuri.org/DeleteEmployee"
        result = self._soap_post(op_path, soap_action, xml)

        self.create_sync_log(
            action=BiometricSyncLog.Action.DELETE,
            payload=xml,
            response=result,
            target=target,
            device_user_id=employee_code,
            success=bool(result.get("ok")),
        )
        return result

    def push_enrollment(
        self,
        target: Any,
        device_user_id: str = None,
    ) -> Dict[str, Any]:
        if not target:
            return {"ok": False, "message": "Target is required."}

        try:
            return self.update_employee_ex(target)
        except BiometricSyncError as exc:
            return {"ok": False, "message": str(exc)}

    def push_delete(
        self,
        target: Any = None,
        device_user_id: str = None,
    ) -> Dict[str, Any]:
        code = device_user_id or (self._employee_code(target) if target else "")
        if not code:
            return {"ok": False, "message": "EmployeeCode required for delete."}

        try:
            return self.delete_employee(code, target=target)
        except BiometricSyncError as exc:
            return {"ok": False, "message": str(exc)}

    def probe(self) -> Dict[str, Any]:
        result = {
            "ok": True,
            "device_type": self.device.device_type,
            "serial_number": self.device.serial_number,
            "device_name": self.device.device_name,
            "last_seen_at": (
                self.device.last_seen_at.isoformat()
                if self.device.last_seen_at
                else None
            ),
            "last_known_ip": self.device.last_known_ip,
            "message": "Device record is available.",
        }

        self.device.last_sync_at = timezone.now()
        self.device.save(update_fields=["last_sync_at"])
        self.create_sync_log(
            action=BiometricSyncLog.Action.DEVICE_HEARTBEAT,
            payload={"status_check": True},
            response=result,
            success=True,
        )
        return result

    @transaction.atomic
    def synchronize_device(self) -> Dict[str, Any]:
        result = {
            "ok": True,
            "message": "Synchronization is handled via eBioServer SOAP calls.",
            "device_serial": self.device.serial_number,
        }

        self.create_sync_log(
            action=BiometricSyncLog.Action.DEVICE_SYNC,
            payload={"mode": "ebioserver-soap"},
            response=result,
            success=True,
        )
        return result
