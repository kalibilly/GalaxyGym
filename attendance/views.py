import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.models import UserAccount
from members.models import Member
from staffs.models import Staff

from .forms import AttendanceLogForm
from .models import (
    AttendanceLog,
    BiometricDevice,
    BiometricDeviceCommand,
    BiometricRawEvent,
    BiometricSyncLog,
    DeviceUserLink,
    MemberBiometricDeviceStatus,
    StaffBiometricDeviceStatus,
)

logger = logging.getLogger("biometric")


class AttendanceAccessMixin(LoginRequiredMixin):
    def get_member_profile(self):
        return getattr(self.request.user, "member_profile", None)

    def get_staff_profile(self):
        return getattr(self.request.user, "staff_profile", None)

    def is_owner(self):
        return getattr(self.request.user, "role", None) == UserAccount.ROLE_OWNER

    def is_member(self):
        return getattr(self.request.user, "role", None) == UserAccount.ROLE_MEMBER

    def is_staff_user(self):
        return getattr(self.request.user, "role", None) == UserAccount.ROLE_STAFF

    def get_allowed_attendance_queryset(self, queryset):
        if self.is_owner():
            return queryset
        if self.is_member():
            member = self.get_member_profile()
            return queryset.filter(member=member) if member else queryset.none()
        if self.is_staff_user():
            staff = self.get_staff_profile()
            return queryset.filter(staff=staff) if staff else queryset.none()
        return queryset.none()

    def ensure_attendance_access(self, attendance):
        if self.is_owner():
            return attendance
        if self.is_member() and attendance.member == self.get_member_profile():
            return attendance
        if self.is_staff_user() and attendance.staff == self.get_staff_profile():
            return attendance
        raise PermissionDenied("You are not authorized to access this attendance record.")


class AttendanceListView(AttendanceAccessMixin, ListView):
    model = AttendanceLog
    template_name = "attendance/attendance_list.html"
    context_object_name = "attendance_list"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("member", "staff", "device")
            .order_by("-date", "-check_in_time")
        )

        person_type = self.request.GET.get("person_type")
        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")
        query = self.request.GET.get("q")

        if person_type:
            queryset = queryset.filter(person_type=person_type)
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        if query:
            queryset = queryset.filter(
                Q(member__full_name__icontains=query)
                | Q(member__member_id__icontains=query)
                | Q(staff__full_name__icontains=query)
                | Q(staff__staff_id__icontains=query)
                | Q(device_user_id__icontains=query)
                | Q(device_identifier__icontains=query)
                | Q(device__serial_number__icontains=query)
                | Q(device__device_name__icontains=query)
            )

        return self.get_allowed_attendance_queryset(queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["person_type"] = self.request.GET.get("person_type", "")
        context["start_date"] = self.request.GET.get("start_date", "")
        context["end_date"] = self.request.GET.get("end_date", "")
        context["q"] = self.request.GET.get("q", "")
        return context


class AttendanceCreateView(LoginRequiredMixin, CreateView):
    model = AttendanceLog
    form_class = AttendanceLogForm
    template_name = "attendance/attendance_form.html"
    success_url = reverse_lazy("attendance:attendance_list")


class AttendanceUpdateView(LoginRequiredMixin, UpdateView):
    model = AttendanceLog
    form_class = AttendanceLogForm
    template_name = "attendance/attendance_form.html"
    success_url = reverse_lazy("attendance:attendance_list")


class AttendanceDetailView(AttendanceAccessMixin, DetailView):
    model = AttendanceLog
    template_name = "attendance/attendance_detail.html"
    context_object_name = "attendance"

    def get_object(self, queryset=None):
        attendance = super().get_object(queryset=queryset)
        return self.ensure_attendance_access(attendance)


class MemberAttendanceHistoryView(AttendanceAccessMixin, DetailView):
    model = Member
    template_name = "attendance/member_history.html"
    context_object_name = "member"

    def get_object(self):
        member = get_object_or_404(Member, pk=self.kwargs["member_pk"])
        if self.is_owner():
            return member
        if self.is_member() and member == self.get_member_profile():
            return member
        raise PermissionDenied("You do not have permission to view this member's attendance history.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attendance_list"] = (
            self.object.attendance_logs.select_related("device").order_by("-date", "-check_in_time")
        )
        return context


class StaffAttendanceHistoryView(AttendanceAccessMixin, DetailView):
    model = Staff
    template_name = "attendance/staff_history.html"
    context_object_name = "staff"

    def get_object(self):
        staff = get_object_or_404(Staff, pk=self.kwargs["staff_pk"])
        if self.is_owner():
            return staff
        if self.is_staff_user() and staff == self.get_staff_profile():
            return staff
        raise PermissionDenied("You do not have permission to view this staff attendance history.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attendance_list"] = (
            self.object.attendance_logs.select_related("device").order_by("-date", "-check_in_time")
        )
        return context


def extract_headers(request):
    headers = {}
    for key, value in request.META.items():
        if key.startswith("HTTP_") or key in {"CONTENT_TYPE", "CONTENT_LENGTH", "REMOTE_ADDR"}:
            headers[key] = value
    return headers


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def parse_xml(raw_body):
    parsed = {}
    if not raw_body or not raw_body.strip().startswith("<"):
        return parsed

    try:
        root = ET.fromstring(raw_body)
        for element in root.iter():
            if element.tag and element.text:
                parsed[element.tag.lower()] = element.text.strip()
    except ET.ParseError:
        logger.warning("Unable to parse XML biometric payload.")

    return parsed


def looks_like_datetime(value):
    return parse_device_timestamp(value) is not None


def parse_plain_text_rows(raw_body):
    rows = []
    if not raw_body:
        return rows

    for line in raw_body.splitlines():
        line = line.strip()
        if not line:
            continue

        parsed = {"_raw": line}

        if "=" in line and "\t" not in line:
            parts = line.replace("\t", " ").split()
            for part in parts:
                if "=" in part:
                    key, value = part.split("=", 1)
                    parsed[key.lower()] = value.strip()
            rows.append(parsed)
            continue

        cols = [col.strip() for col in line.split("\t") if col.strip() != ""]
        if not cols:
            cols = [col.strip() for col in line.split() if col.strip()]

        parsed["_cols"] = cols

        if cols:
            parsed["id"] = cols[0]
            parsed["pin"] = cols[0]

        if len(cols) >= 2 and looks_like_datetime(cols[1]):
            parsed["checktime"] = cols[1]
        elif len(cols) >= 3:
            candidate = f"{cols[1]} {cols[2]}"
            if looks_like_datetime(candidate):
                parsed["checktime"] = candidate

        if len(cols) >= 3:
            parsed["status"] = cols[2]
        if len(cols) >= 4:
            parsed["verify"] = cols[3]
        if len(cols) >= 5:
            parsed["workcode"] = cols[4]
        if len(cols) >= 6:
            parsed["reserved_1"] = cols[5]
        if len(cols) >= 7:
            parsed["reserved_2"] = cols[6]

        rows.append(parsed)

    return rows


def parse_device_timestamp(value):
    if not value:
        return None

    value = str(value).strip()
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y%m%d%H%M%S",
        "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
    )

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(value)
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    except ValueError:
        return None


def render_device_response(request, text="OK"):
    raw_body = request.body.decode("utf-8", errors="ignore")
    if "xml" in (request.content_type or "") or raw_body.strip().startswith("<"):
        return HttpResponse(f"<Response>{text}</Response>", content_type="application/xml")
    return HttpResponse(text, content_type="text/plain")


def normalize_request_payload(request):
    raw_body = request.body.decode("utf-8", errors="ignore")
    payload = {
        "method": request.method,
        "path": request.path,
        "headers": extract_headers(request),
        "query_data": {k.lower(): v for k, v in request.GET.items()},
        "post_data": {k.lower(): v for k, v in request.POST.items()},
        "raw_body": raw_body,
        "xml_fields": parse_xml(raw_body),
        "plain_text_rows": parse_plain_text_rows(raw_body),
        "json_payload": None,
    }

    if "json" in (request.content_type or "") and raw_body:
        try:
            payload["json_payload"] = json.loads(raw_body)
        except json.JSONDecodeError:
            payload["json_payload"] = None

    return payload


def log_biometric_request(payload):
    logger.info("Biometric request: %s", json.dumps(payload, default=str))


def get_primary_payload(payload):
    if payload["plain_text_rows"]:
        return payload["plain_text_rows"][0]
    if payload["post_data"]:
        return payload["post_data"]
    if payload["xml_fields"]:
        return payload["xml_fields"]
    if payload["json_payload"]:
        return payload["json_payload"]
    return payload["query_data"]


def extract_device_serial(*sources):
    keys = ["sn", "serial", "serial_number", "device_sn"]
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value:
                return str(value).strip()
    return ""


def extract_device_user_id(*sources):
    keys = ["pin", "uid", "userid", "user_id", "device_user_id", "id"]
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value:
                return str(value).strip()
    return ""


def extract_punch_timestamp(*sources):
    keys = ["checktime", "timestamp", "datetime", "time", "punch_time"]
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value:
                dt = parse_device_timestamp(value)
                if dt:
                    return dt

        cols = source.get("_cols") if isinstance(source, dict) else None
        if cols:
            if len(cols) >= 2:
                dt = parse_device_timestamp(cols[1])
                if dt:
                    return dt
            if len(cols) >= 3:
                dt = parse_device_timestamp(f"{cols[1]} {cols[2]}")
                if dt:
                    return dt

    return timezone.now()


def extract_event_type(*sources):
    keys = ["table", "event", "event_type", "op"]
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value:
                return str(value).strip().lower()
    return ""


def is_attendance_event(payload, event_name=""):
    event_name = (event_name or "").strip().lower()
    if event_name in {"attlog", "attendance", "checkin"}:
        return True

    table_name = (
        payload["query_data"].get("table")
        or payload["post_data"].get("table")
        or payload["xml_fields"].get("table")
        or ""
    ).strip().lower()
    if table_name == "attlog":
        return True

    for row in payload["plain_text_rows"]:
        if row.get("checktime") and row.get("pin"):
            return True
        cols = row.get("_cols") or []
        if len(cols) >= 2 and parse_device_timestamp(cols[1]):
            return True

    return False


def get_or_create_device(device_serial, raw_body="", request=None):
    if not device_serial:
        return None

    device, _ = BiometricDevice.objects.get_or_create(
        serial_number=device_serial,
        defaults={"device_name": device_serial},
    )

    if hasattr(device, "touch_heartbeat"):
        device.touch_heartbeat(
            raw_body or "",
            remote_ip=get_client_ip(request) if request else None,
        )

    return device


def create_raw_event(device, event_type, request, raw_body, device_user_id="", parsed_ok=False, notes=""):
    return BiometricRawEvent.objects.create(
        device=device,
        event_type=event_type,
        remote_ip=get_client_ip(request),
        device_user_id=device_user_id or "",
        event_time=timezone.now(),
        payload=raw_body or "",
        parsed_ok=parsed_ok,
        notes=notes,
    )


def log_sync_event(
    action,
    device=None,
    member=None,
    staff=None,
    device_user_id="",
    success=True,
    payload="",
    response="",
    notes="",
):
    BiometricSyncLog.objects.create(
        device=device,
        member=member,
        staff=staff,
        action=action,
        device_user_id=device_user_id or "",
        success=success,
        payload=payload or "",
        response=response or "",
        notes=notes or "",
    )


def get_target_by_device_user_id(device_user_id):
    if not device_user_id:
        return None

    link = (
        DeviceUserLink.objects.select_related("member", "staff")
        .filter(device_user_id=device_user_id, is_active=True)
        .first()
    )
    if link:
        return link.member or link.staff

    member = Member.objects.filter(
        Q(device_user_id=device_user_id) | Q(member_id=device_user_id)
    ).first()
    if member:
        return member

    staff = Staff.objects.filter(
        Q(device_user_id=device_user_id) | Q(staff_id=device_user_id)
    ).first()
    if staff:
        return staff

    return None


def ensure_device_user_link(target, device_user_id):
    if not target or not device_user_id:
        return None

    if isinstance(target, Member):
        obj, _ = DeviceUserLink.objects.get_or_create(
            device_user_id=device_user_id,
            defaults={
                "member": target,
                "person_type": DeviceUserLink.PersonType.MEMBER,
                "is_active": True,
            },
        )
        if obj.member_id != target.id or obj.staff_id is not None or not obj.is_active:
            obj.member = target
            obj.staff = None
            obj.person_type = DeviceUserLink.PersonType.MEMBER
            obj.is_active = True
            obj.save(update_fields=["member", "staff", "person_type", "is_active"])
        return obj

    if isinstance(target, Staff):
        obj, _ = DeviceUserLink.objects.get_or_create(
            device_user_id=device_user_id,
            defaults={
                "staff": target,
                "person_type": DeviceUserLink.PersonType.STAFF,
                "is_active": True,
            },
        )
        if obj.staff_id != target.id or obj.member_id is not None or not obj.is_active:
            obj.staff = target
            obj.member = None
            obj.person_type = DeviceUserLink.PersonType.STAFF
            obj.is_active = True
            obj.save(update_fields=["staff", "member", "person_type", "is_active"])
        return obj

    return None


def get_member_device_status(member, device):
    if not member or not device:
        return None

    status, _ = MemberBiometricDeviceStatus.objects.get_or_create(
        member=member,
        device=device,
        defaults={"device_user_id": member.device_user_id or member.member_id},
    )

    expected_id = member.device_user_id or member.member_id
    if expected_id and status.device_user_id != expected_id:
        status.device_user_id = expected_id
        status.save(update_fields=["device_user_id"])

    return status


def get_staff_device_status(staff, device):
    if not staff or not device:
        return None

    status, _ = StaffBiometricDeviceStatus.objects.get_or_create(
        staff=staff,
        device=device,
        defaults={"device_user_id": staff.device_user_id or staff.staff_id},
    )

    expected_id = staff.device_user_id or staff.staff_id
    if expected_id and status.device_user_id != expected_id:
        status.device_user_id = expected_id
        status.save(update_fields=["device_user_id"])

    return status


def is_member_allowed(member):
    status_ok = getattr(member, "status", "") == Member.STATUS_ACTIVE
    user_ok = True
    if hasattr(member, "user") and member.user:
        user_ok = bool(member.user.is_active)
    return status_ok and user_ok


def is_staff_allowed(staff):
    if hasattr(staff, "user") and staff.user:
        return bool(staff.user.is_active)
    if hasattr(staff, "is_active"):
        return bool(staff.is_active)
    return True


def create_attendance_entry(target, device, device_user_id, check_in_time, granted, remarks=""):
    date_value = (
        timezone.localtime(check_in_time).date()
        if timezone.is_aware(check_in_time)
        else check_in_time.date()
    )

    filters = {
        "date": date_value,
        "device_user_id": device_user_id or "",
    }

    if isinstance(target, Member):
        filters["member"] = target
        person_type = AttendanceLog.PersonType.MEMBER
    else:
        filters["staff"] = target
        person_type = AttendanceLog.PersonType.STAFF

    existing = AttendanceLog.objects.filter(**filters).first()
    if existing:
        return existing, True

    attendance = AttendanceLog.objects.create(
        member=target if isinstance(target, Member) else None,
        staff=target if isinstance(target, Staff) else None,
        person_type=person_type,
        date=date_value,
        check_in_time=check_in_time,
        source=AttendanceLog.Source.DEVICE,
        verification_mode=AttendanceLog.VerificationMode.BIOMETRIC,
        device=device,
        device_identifier=device.serial_number if device else "",
        device_user_id=device_user_id or "",
        status=AttendanceLog.Status.PRESENT if granted else AttendanceLog.Status.ABSENT,
        remarks=remarks,
    )
    return attendance, False


def build_device_command_text(command):
    command_id = command.pk
    user_id = command.device_user_id

    mapping = {
        BiometricDeviceCommand.CommandType.DELETE_USER: f"C:{command_id}:DATA DEL_USER PIN={user_id}",
        BiometricDeviceCommand.CommandType.DISABLE_USER: f"C:{command_id}:DATA UPDATE USERINFO PIN={user_id}\tActive=0",
        BiometricDeviceCommand.CommandType.ENABLE_USER: f"C:{command_id}:DATA UPDATE USERINFO PIN={user_id}\tActive=1",
        BiometricDeviceCommand.CommandType.SYNC_FACE: f"C:{command_id}:DATA UPDATE FACE PIN={user_id}",
        BiometricDeviceCommand.CommandType.SYNC_FINGERPRINT: f"C:{command_id}:DATA UPDATE FINGERTMP PIN={user_id}",
        BiometricDeviceCommand.CommandType.SYNC_PASSWORD: f"C:{command_id}:DATA UPDATE USERINFO PIN={user_id}",
        BiometricDeviceCommand.CommandType.REFRESH_USER: f"C:{command_id}:DATA UPDATE USERINFO PIN={user_id}",
        BiometricDeviceCommand.CommandType.SYNC_USER: f"C:{command_id}:DATA UPDATE USERINFO PIN={user_id}",
    }
    return mapping.get(command.command, f"C:{command_id}:DATA UPDATE USERINFO PIN={user_id}")


def mark_related_status_sent(command):
    if command.member_id:
        status = get_member_device_status(command.member, command.device)
        if status and hasattr(status, "mark_sync_sent"):
            status.mark_sync_sent()
    elif command.staff_id:
        status = get_staff_device_status(command.staff, command.device)
        if status and hasattr(status, "mark_sync_sent"):
            status.mark_sync_sent()


def queue_member_device_command(member, device, command_type, notes=""):
    command = BiometricDeviceCommand.objects.create(
        device=device,
        member=member,
        command=command_type,
        device_user_id=member.device_user_id or member.member_id,
        notes=notes,
    )
    mark_related_status_sent(command)
    return command


def queue_staff_device_command(staff, device, command_type, notes=""):
    command = BiometricDeviceCommand.objects.create(
        device=device,
        staff=staff,
        command=command_type,
        device_user_id=staff.device_user_id or staff.staff_id,
        notes=notes,
    )
    mark_related_status_sent(command)
    return command


def process_attendance_row(request, payload, device, row):
    device_user_id = extract_device_user_id(
        row,
        payload["query_data"],
        payload["post_data"],
        payload["xml_fields"],
    )
    check_in_time = extract_punch_timestamp(
        row,
        payload["query_data"],
        payload["post_data"],
        payload["xml_fields"],
    )

    create_raw_event(
        device=device,
        event_type=BiometricRawEvent.EventType.ATTENDANCE,
        request=request,
        raw_body=row.get("_raw", payload["raw_body"]),
        device_user_id=device_user_id,
        parsed_ok=bool(device_user_id),
        notes="Attendance or access event received from device.",
    )

    target = get_target_by_device_user_id(device_user_id)
    if not target:
        log_sync_event(
            action=BiometricSyncLog.Action.ACCESS_ATTEMPT,
            device=device,
            device_user_id=device_user_id,
            success=False,
            payload=json.dumps({"row": row, "request": payload}, default=str),
            response="ERR_USER_NOT_FOUND",
            notes="No member or staff matched the received device user ID.",
        )
        return False, "ERR_USER_NOT_FOUND"

    ensure_device_user_link(target, device_user_id)

    if isinstance(target, Member):
        allowed = is_member_allowed(target)
        device_status = get_member_device_status(target, device)
    else:
        allowed = is_staff_allowed(target)
        device_status = get_staff_device_status(target, device)

    remarks = "Biometric attendance recorded." if allowed else "Access denied by software rules."
    attendance, duplicate = create_attendance_entry(
        target=target,
        device=device,
        device_user_id=device_user_id,
        check_in_time=check_in_time,
        granted=allowed,
        remarks=remarks,
    )

    if device_status:
        if hasattr(device_status, "last_status_checked_at"):
            device_status.last_status_checked_at = timezone.now()
        if hasattr(device_status, "is_enabled_on_device"):
            device_status.is_enabled_on_device = allowed
        if hasattr(device_status, "notes"):
            device_status.notes = remarks

        update_fields = []
        if hasattr(device_status, "last_status_checked_at"):
            update_fields.append("last_status_checked_at")
        if hasattr(device_status, "is_enabled_on_device"):
            update_fields.append("is_enabled_on_device")
        if hasattr(device_status, "notes"):
            update_fields.append("notes")
        if update_fields:
            device_status.save(update_fields=update_fields)

    log_sync_event(
        action=BiometricSyncLog.Action.ACCESS_ATTEMPT,
        device=device,
        member=target if isinstance(target, Member) else None,
        staff=target if isinstance(target, Staff) else None,
        device_user_id=device_user_id,
        success=allowed,
        payload=json.dumps({"row": row, "request": payload}, default=str),
        response="OK" if allowed else "DENY",
        notes="Duplicate attendance ignored." if duplicate else remarks,
    )

    return allowed, "OK" if allowed else "DENY"


def handle_access_event(request, payload):
    primary = get_primary_payload(payload)

    device_serial = extract_device_serial(
        primary,
        payload["query_data"],
        payload["post_data"],
        payload["xml_fields"],
    )
    device = get_or_create_device(device_serial, payload["raw_body"], request)

    if payload["plain_text_rows"]:
        any_success = False
        last_response = "OK"
        for row in payload["plain_text_rows"]:
            allowed, response_text = process_attendance_row(request, payload, device, row)
            any_success = any_success or allowed
            last_response = response_text
        return render_device_response(request, "OK" if any_success else last_response)

    allowed, response_text = process_attendance_row(request, payload, device, primary)
    return render_device_response(request, response_text if response_text else ("OK" if allowed else "DENY"))


@require_http_methods(["GET", "POST"])
@csrf_exempt
def biometric_device_listener(request):
    payload = normalize_request_payload(request)
    log_biometric_request(payload)

    primary = get_primary_payload(payload)
    device_serial = extract_device_serial(
        primary,
        payload["query_data"],
        payload["post_data"],
        payload["xml_fields"],
    )
    event_name = extract_event_type(
        primary,
        payload["query_data"],
        payload["post_data"],
        payload["xml_fields"],
    )

    device = get_or_create_device(device_serial, payload["raw_body"], request)

    if request.method == "GET":
        if "getrequest" in request.path.lower():
            return biometric_device_getrequest(request)

        create_raw_event(
            device=device,
            event_type=BiometricRawEvent.EventType.HEARTBEAT,
            request=request,
            raw_body=payload["raw_body"],
            parsed_ok=True,
            notes="Device heartbeat or poll request.",
        )
        log_sync_event(
            action=BiometricSyncLog.Action.DEVICE_HEARTBEAT,
            device=device,
            success=True,
            payload=json.dumps(payload, default=str),
            response="OK",
            notes="Device heartbeat received.",
        )
        return render_device_response(request, "OK")

    if is_attendance_event(payload, event_name):
        return handle_access_event(request, payload)

    create_raw_event(
        device=device,
        event_type=BiometricRawEvent.EventType.UNKNOWN,
        request=request,
        raw_body=payload["raw_body"],
        parsed_ok=False,
        notes="Unclassified biometric payload.",
    )
    log_sync_event(
        action=BiometricSyncLog.Action.RAW_EVENT,
        device=device,
        success=True,
        payload=json.dumps(payload, default=str),
        response="OK",
        notes="Unclassified payload stored as raw event.",
    )
    return render_device_response(request, "OK")


@require_http_methods(["GET"])
@csrf_exempt
def biometric_device_getrequest(request):
    payload = normalize_request_payload(request)
    primary = get_primary_payload(payload)

    device_serial = extract_device_serial(
        primary,
        payload["query_data"],
        payload["post_data"],
        payload["xml_fields"],
    )
    device = get_or_create_device(device_serial, payload["raw_body"], request)

    create_raw_event(
        device=device,
        event_type=BiometricRawEvent.EventType.COMMAND_POLL,
        request=request,
        raw_body=payload["raw_body"],
        parsed_ok=True,
        notes="Device polled for pending command.",
    )

    command = (
        BiometricDeviceCommand.objects.filter(
            device=device,
            status=BiometricDeviceCommand.Status.PENDING,
        )
        .order_by("queued_at", "pk")
        .first()
    )

    if not command:
        return HttpResponse("OK", content_type="text/plain")

    command_text = build_device_command_text(command)

    if hasattr(command, "mark_sent"):
        command.mark_sent(response_payload=command_text)
    else:
        command.status = BiometricDeviceCommand.Status.SENT
        if hasattr(command, "sent_at"):
            command.sent_at = timezone.now()
        if hasattr(command, "response_payload"):
            command.response_payload = command_text
        update_fields = ["status"]
        if hasattr(command, "sent_at"):
            update_fields.append("sent_at")
        if hasattr(command, "response_payload"):
            update_fields.append("response_payload")
        command.save(update_fields=update_fields)

    log_sync_event(
        action=BiometricSyncLog.Action.COMMAND,
        device=device,
        member=getattr(command, "member", None),
        staff=getattr(command, "staff", None),
        device_user_id=command.device_user_id,
        success=True,
        payload=getattr(command, "payload", ""),
        response=command_text,
        notes=f"Command sent to device: {command.command}",
    )
    return HttpResponse(command_text, content_type="text/plain")


def detect_command_ack_row(rows, device):
    if not rows:
        return None, ""

    first_row = rows[0]
    stamp_value = str(first_row.get("id") or first_row.get("stamp") or "").strip()
    if not stamp_value.isdigit():
        return None, ""

    command = (
        BiometricDeviceCommand.objects.filter(
            pk=int(stamp_value),
            device=device,
        ).first()
    )
    if not command:
        return None, ""

    raw_text = "\n".join(row.get("_raw", "") for row in rows).lower()
    return command, raw_text


@require_http_methods(["POST"])
@csrf_exempt
def biometric_device_cdata(request):
    payload = normalize_request_payload(request)
    primary = get_primary_payload(payload)

    device_serial = extract_device_serial(
        primary,
        payload["query_data"],
        payload["post_data"],
        payload["xml_fields"],
    )
    device = get_or_create_device(device_serial, payload["raw_body"], request)

    if is_attendance_event(payload, extract_event_type(primary, payload["query_data"], payload["post_data"], payload["xml_fields"])):
        return handle_access_event(request, payload)

    rows = payload["plain_text_rows"]
    raw_body = payload["raw_body"]

    command, ack_text = detect_command_ack_row(rows, device)

    if command:
        create_raw_event(
            device=device,
            event_type=BiometricRawEvent.EventType.COMMAND_ACK,
            request=request,
            raw_body=raw_body,
            device_user_id=command.device_user_id,
            parsed_ok=True,
            notes="Command acknowledgement received.",
        )

        success = "ok" in ack_text or "success" in ack_text

        if success:
            if hasattr(command, "mark_success"):
                command.mark_success(response_payload=raw_body)
            else:
                command.status = BiometricDeviceCommand.Status.SUCCESS
                if hasattr(command, "response_payload"):
                    command.response_payload = raw_body
                command.save()

            if command.member_id:
                status = get_member_device_status(command.member, command.device)
                if status:
                    if hasattr(status, "mark_sync_success"):
                        status.mark_sync_success()
                    if (
                        command.command == BiometricDeviceCommand.CommandType.SYNC_FACE
                        and hasattr(status, "set_face_added")
                    ):
                        status.set_face_added(True)
                    elif (
                        command.command == BiometricDeviceCommand.CommandType.SYNC_FINGERPRINT
                        and hasattr(status, "set_fingerprint_added")
                    ):
                        status.set_fingerprint_added(True)
                    elif (
                        command.command == BiometricDeviceCommand.CommandType.SYNC_PASSWORD
                        and hasattr(status, "set_password_added")
                    ):
                        status.set_password_added(True)

            elif command.staff_id:
                status = get_staff_device_status(command.staff, command.device)
                if status and hasattr(status, "mark_sync_success"):
                    status.mark_sync_success()

            log_sync_event(
                action=BiometricSyncLog.Action.COMMAND,
                device=device,
                member=command.member,
                staff=command.staff,
                device_user_id=command.device_user_id,
                success=True,
                payload=getattr(command, "payload", ""),
                response=raw_body,
                notes="Device command completed successfully.",
            )
            return render_device_response(request, "OK")

        if hasattr(command, "mark_failed"):
            command.mark_failed("Device reported failure.", response_payload=raw_body)
        else:
            command.status = BiometricDeviceCommand.Status.FAILED
            if hasattr(command, "response_payload"):
                command.response_payload = raw_body
            command.save()

        if command.member_id:
            status = get_member_device_status(command.member, command.device)
            if status and hasattr(status, "mark_sync_failed"):
                status.mark_sync_failed("Device reported failure.")
        elif command.staff_id:
            status = get_staff_device_status(command.staff, command.device)
            if status and hasattr(status, "mark_sync_failed"):
                status.mark_sync_failed("Device reported failure.")

        log_sync_event(
            action=BiometricSyncLog.Action.COMMAND,
            device=device,
            member=command.member,
            staff=command.staff,
            device_user_id=command.device_user_id,
            success=False,
            payload=getattr(command, "payload", ""),
            response=raw_body,
            notes="Device command failed.",
        )
        return render_device_response(request, "OK")

    return handle_access_event(request, payload)


@require_http_methods(["GET"])
@login_required
def device_sync_status(request):
    serial_number = (
        request.GET.get("device_serial")
        or request.GET.get("sn")
        or request.GET.get("serial")
    )
    if not serial_number:
        return JsonResponse(
            {"ok": False, "error": "device_serial query parameter is required."},
            status=400,
        )

    device = BiometricDevice.objects.filter(serial_number=serial_number).first()
    if not device:
        return JsonResponse({"ok": False, "error": "Unknown device serial."}, status=404)

    pending_commands = BiometricDeviceCommand.objects.filter(
        device=device,
        status=BiometricDeviceCommand.Status.PENDING,
    ).count()

    return JsonResponse(
        {
            "ok": True,
            "device": {
                "serial_number": device.serial_number,
                "device_name": device.device_name,
                "device_type": getattr(device, "device_type", ""),
                "firmware_version": getattr(device, "firmware_version", ""),
                "is_active": getattr(device, "is_active", True),
                "last_seen_at": (
                    device.last_seen_at.isoformat()
                    if getattr(device, "last_seen_at", None)
                    else None
                ),
                "last_sync_at": (
                    device.last_sync_at.isoformat()
                    if getattr(device, "last_sync_at", None)
                    else None
                ),
                "last_known_ip": getattr(device, "last_known_ip", ""),
                "pending_commands": pending_commands,
            },
        }
    )


@require_http_methods(["POST"])
@csrf_exempt
def device_enrollment(request):
    payload = normalize_request_payload(request)
    primary = get_primary_payload(payload)

    device_serial = extract_device_serial(
        primary,
        payload["query_data"],
        payload["post_data"],
        payload["xml_fields"],
    )
    device_user_id = extract_device_user_id(
        primary,
        payload["query_data"],
        payload["post_data"],
        payload["xml_fields"],
    )

    device = get_or_create_device(device_serial, payload["raw_body"], request)
    target = get_target_by_device_user_id(device_user_id)

    event_type = getattr(
        BiometricRawEvent.EventType,
        "USER_SNAPSHOT",
        BiometricRawEvent.EventType.UNKNOWN,
    )
    action_type = getattr(
        BiometricSyncLog.Action,
        "ENROLLMENT",
        BiometricSyncLog.Action.RAW_EVENT,
    )

    create_raw_event(
        device=device,
        event_type=event_type,
        request=request,
        raw_body=payload["raw_body"],
        device_user_id=device_user_id,
        parsed_ok=bool(target),
        notes="Enrollment payload received.",
    )

    log_sync_event(
        action=action_type,
        device=device,
        member=target if isinstance(target, Member) else None,
        staff=target if isinstance(target, Staff) else None,
        device_user_id=device_user_id,
        success=bool(target),
        payload=json.dumps(payload, default=str),
        response="OK",
        notes="Enrollment data received from device.",
    )

    return render_device_response(request, "OK")


@require_http_methods(["POST"])
@csrf_exempt
def bridge_entry(request):
    payload = normalize_request_payload(request)
    log_biometric_request(payload)
    return handle_access_event(request, payload)


@require_http_methods(["GET", "POST"])
@csrf_exempt
def access_sync(request):
    if request.method == "GET":
        return device_sync_status(request)

    payload = normalize_request_payload(request)
    primary = get_primary_payload(payload)

    device_serial = extract_device_serial(
        primary,
        payload["query_data"],
        payload["post_data"],
        payload["xml_fields"],
    )
    device_user_id = extract_device_user_id(
        primary,
        payload["query_data"],
        payload["post_data"],
        payload["xml_fields"],
    )

    device = get_or_create_device(device_serial, payload["raw_body"], request)
    target = get_target_by_device_user_id(device_user_id)

    if not device:
        return JsonResponse({"ok": False, "error": "Unable to resolve device."}, status=400)
    if not target:
        return JsonResponse({"ok": False, "error": "Unable to resolve member or staff."}, status=404)

    refresh_command = getattr(
        BiometricDeviceCommand.CommandType,
        "REFRESH_USER",
        BiometricDeviceCommand.CommandType.SYNC_USER,
    )

    if isinstance(target, Member):
        command = queue_member_device_command(
            member=target,
            device=device,
            command_type=refresh_command,
            notes="Queued from access_sync endpoint.",
        )
    else:
        command = queue_staff_device_command(
            staff=target,
            device=device,
            command_type=refresh_command,
            notes="Queued from access_sync endpoint.",
        )

    action_type = getattr(
        BiometricSyncLog.Action,
        "DEVICE_SYNC",
        BiometricSyncLog.Action.COMMAND,
    )

    log_sync_event(
        action=action_type,
        device=device,
        member=target if isinstance(target, Member) else None,
        staff=target if isinstance(target, Staff) else None,
        device_user_id=device_user_id,
        success=True,
        payload=json.dumps(payload, default=str),
        response="QUEUED",
        notes=f"Queued command {command.command} for device sync.",
    )

    return JsonResponse(
        {
            "ok": True,
            "command_id": command.pk,
            "command": command.command,
            "device_serial": device.serial_number,
            "device_user_id": command.device_user_id,
            "status": command.status,
        }
    )


# Compatibility aliases used by existing URLConfs
biometric_endpoint = biometric_device_listener
biometric_get_request = biometric_device_getrequest
iclock_getrequest = biometric_device_getrequest
iclock_cdata = biometric_device_cdata
