import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

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
        status = self.request.GET.get("status")
        search = self.request.GET.get("search")

        if person_type in {AttendanceLog.PersonType.MEMBER, AttendanceLog.PersonType.STAFF}:
            queryset = queryset.filter(person_type=person_type)

        if status in {
            AttendanceLog.Status.PRESENT,
            AttendanceLog.Status.ABSENT,
            AttendanceLog.Status.LATE,
        }:
            queryset = queryset.filter(status=status)

        if start_date:
            queryset = queryset.filter(date__gte=start_date)

        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        if search:
            queryset = queryset.filter(
                Q(member__full_name__icontains=search)
                | Q(member__member_id__icontains=search)
                | Q(member__device_user_id__icontains=search)
                | Q(staff__full_name__icontains=search)
                | Q(staff__staff_id__icontains=search)
                | Q(staff__device_user_id__icontains=search)
                | Q(device_user_id__icontains=search)
                | Q(device_identifier__icontains=search)
            )

        return self.get_allowed_attendance_queryset(queryset)


class AttendanceDetailView(AttendanceAccessMixin, DetailView):
    model = AttendanceLog
    template_name = "attendance/attendance_detail.html"
    context_object_name = "attendance"

    def get_object(self, queryset=None):
        attendance = super().get_object(queryset)
        return self.ensure_attendance_access(attendance)


class AttendanceCreateView(AttendanceAccessMixin, CreateView):
    model = AttendanceLog
    form_class = AttendanceLogForm
    template_name = "attendance/attendance_form.html"
    success_url = reverse_lazy("attendance:list")

    def dispatch(self, request, *args, **kwargs):
        if not self.is_owner():
            raise PermissionDenied("Only owners can create attendance records.")
        return super().dispatch(request, *args, **kwargs)


class AttendanceUpdateView(AttendanceAccessMixin, UpdateView):
    model = AttendanceLog
    form_class = AttendanceLogForm
    template_name = "attendance/attendance_form.html"
    success_url = reverse_lazy("attendance:list")

    def dispatch(self, request, *args, **kwargs):
        if not self.is_owner():
            raise PermissionDenied("Only owners can update attendance records.")
        return super().dispatch(request, *args, **kwargs)


@login_required
def device_sync_status(request):
    if getattr(request.user, "role", None) != UserAccount.ROLE_OWNER:
        raise PermissionDenied("Only owners can view biometric sync status.")

    member_statuses = (
        MemberBiometricDeviceStatus.objects.select_related("member", "device")
        .order_by("device__device_name", "member__full_name")
    )
    staff_statuses = (
        StaffBiometricDeviceStatus.objects.select_related("staff", "device")
        .order_by("device__device_name", "staff__full_name")
    )

    data = {
        "member_statuses": [
            {
                "member": item.member.full_name,
                "device": str(item.device),
                "device_user_id": item.device_user_id,
                "sync_status": item.sync_status,
                "enabled": item.is_enabled_on_device,
                "last_synced_at": item.last_synced_at.isoformat() if item.last_synced_at else None,
                "last_error": item.last_error,
            }
            for item in member_statuses
        ],
        "staff_statuses": [
            {
                "staff": item.staff.full_name,
                "device": str(item.device),
                "device_user_id": item.device_user_id,
                "sync_status": item.sync_status,
                "enabled": item.is_enabled_on_device,
                "last_synced_at": item.last_synced_at.isoformat() if item.last_synced_at else None,
                "last_error": item.last_error,
            }
            for item in staff_statuses
        ],
    }
    return JsonResponse(data)


@login_required
@require_http_methods(["POST"])
def device_enrollment(request):
    if getattr(request.user, "role", None) != UserAccount.ROLE_OWNER:
        raise PermissionDenied("Only owners can queue enrollment commands.")

    payload = json.loads(request.body.decode("utf-8") or "{}")
    device_id = payload.get("device_id")
    person_type = payload.get("person_type")
    person_id = payload.get("person_id")
    command = payload.get("command", BiometricDeviceCommand.CommandType.SYNC_USER)

    device = get_object_or_404(BiometricDevice, pk=device_id)

    member = None
    staff = None
    if person_type == AttendanceLog.PersonType.MEMBER:
        member = get_object_or_404(Member, pk=person_id)
        device_user_id = member.device_user_id or member.member_id
    elif person_type == AttendanceLog.PersonType.STAFF:
        staff = get_object_or_404(Staff, pk=person_id)
        device_user_id = staff.device_user_id or staff.staff_id
    else:
        return JsonResponse({"ok": False, "error": "Invalid person_type."}, status=400)

    cmd = BiometricDeviceCommand.objects.create(
        device=device,
        member=member,
        staff=staff,
        command=command,
        device_user_id=device_user_id,
        payload=json.dumps(payload),
    )

    return JsonResponse(
        {
            "ok": True,
            "command_id": cmd.id,
            "status": cmd.status,
            "device": str(device),
            "device_user_id": cmd.device_user_id,
        }
    )


@csrf_exempt
def bridge_entry(request):
    body_text = request.body.decode("utf-8", errors="ignore")
    return JsonResponse(
        {
            "ok": True,
            "method": request.method,
            "path": request.path,
            "query": dict(request.GET),
            "body": body_text[:5000],
        }
    )


@csrf_exempt
def access_sync(request):
    body_text = request.body.decode("utf-8", errors="ignore")
    return JsonResponse(
        {
            "ok": True,
            "method": request.method,
            "path": request.path,
            "query": dict(request.GET),
            "body": body_text[:5000],
        }
    )


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("REMOTE_ADDR", "")


def _clean_querydict(querydict):
    return {str(k).lower(): querydict.get(k, "") for k in querydict.keys()}


def _parse_xml_fields(body_text):
    body_text = (body_text or "").strip()
    if not body_text.startswith("<"):
        return {}
    try:
        root = ET.fromstring(body_text)
    except ET.ParseError:
        return {}
    data = {}
    for elem in root.iter():
        if elem is root:
            continue
        tag = elem.tag.split("}")[-1].lower()
        value = (elem.text or "").strip()
        if value:
            data[tag] = value
    return data


def _parse_json_payload(body_text):
    body_text = (body_text or "").strip()
    if not body_text:
        return None
    try:
        return json.loads(body_text)
    except json.JSONDecodeError:
        return None


def _parse_plain_text_rows(body_text):
    rows = []
    for raw_line in (body_text or "").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if "\t" not in line:
            continue

        parts = [p.strip() for p in raw_line.strip().split("\t")]
        non_empty = [p for p in parts if p != ""]

        entry = {"_raw": raw_line.strip(), "_cols": non_empty}
        if len(non_empty) >= 2:
            entry["id"] = non_empty[0]
            entry["pin"] = non_empty[0]
            entry["checktime"] = non_empty[1]
        if len(non_empty) >= 3:
            entry["status"] = non_empty[2]
        if len(non_empty) >= 4:
            entry["verify"] = non_empty[3]
        if len(non_empty) >= 5:
            entry["workcode"] = non_empty[4]
        if len(non_empty) >= 6:
            entry["reserved_1"] = non_empty[5]
        if len(non_empty) >= 7:
            entry["reserved_2"] = non_empty[6]

        rows.append(entry)
    return rows


def _request_snapshot(request, body_text, xml_fields, text_rows, json_payload):
    return {
        "method": request.method,
        "path": request.path,
        "headers": {
            "REMOTE_ADDR": request.META.get("REMOTE_ADDR"),
            "HTTP_HOST": request.META.get("HTTP_HOST"),
            "HTTP_USER_AGENT": request.META.get("HTTP_USER_AGENT"),
            "CONTENT_LENGTH": request.META.get("CONTENT_LENGTH"),
            "HTTP_ACCEPT": request.META.get("HTTP_ACCEPT"),
            "HTTP_ACCEPT_ENCODING": request.META.get("HTTP_ACCEPT_ENCODING"),
            "HTTP_CDN_LOOP": request.META.get("HTTP_CDN_LOOP"),
            "HTTP_CF_CONNECTING_IP": request.META.get("HTTP_CF_CONNECTING_IP"),
            "HTTP_CF_IPCOUNTRY": request.META.get("HTTP_CF_IPCOUNTRY"),
            "HTTP_CF_RAY": request.META.get("HTTP_CF_RAY"),
            "HTTP_CF_VISITOR": request.META.get("HTTP_CF_VISITOR"),
            "CONTENT_TYPE": request.META.get("CONTENT_TYPE"),
            "HTTP_RENDER_PROXY_TTL": request.META.get("HTTP_RENDER_PROXY_TTL"),
            "HTTP_RNDR_ID": request.META.get("HTTP_RNDR_ID"),
            "HTTP_TRUE_CLIENT_IP": request.META.get("HTTP_TRUE_CLIENT_IP"),
            "HTTP_X_FORWARDED_FOR": request.META.get("HTTP_X_FORWARDED_FOR"),
            "HTTP_X_FORWARDED_PROTO": request.META.get("HTTP_X_FORWARDED_PROTO"),
            "HTTP_X_REQUEST_START": request.META.get("HTTP_X_REQUEST_START"),
        },
        "query_data": _clean_querydict(request.GET),
        "post_data": {str(k): request.POST.get(k, "") for k in request.POST.keys()},
        "raw_body": body_text[:5000],
        "xml_fields": xml_fields,
        "plain_text_rows": text_rows,
        "json_payload": json_payload,
    }


def _extract_serial(request, xml_fields=None, json_payload=None):
    query = _clean_querydict(request.GET)
    xml_fields = xml_fields or {}
    json_payload = json_payload or {}

    return (
        query.get("sn")
        or request.POST.get("SN")
        or request.POST.get("sn")
        or xml_fields.get("sn")
        or xml_fields.get("serialnumber")
        or json_payload.get("sn")
        or json_payload.get("serial_number")
        or ""
    ).strip()


def _get_or_create_device(serial_number, payload="", remote_ip=None):
    if not serial_number:
        return None
    device, _ = BiometricDevice.objects.get_or_create(
        serial_number=serial_number,
        defaults={"device_name": serial_number},
    )
    device.touch_heartbeat(payload=payload, remote_ip=remote_ip)
    return device


def _parse_device_datetime(value):
    if not value:
        return None
    value = str(value).strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(value)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    except ValueError:
        return None


def _resolve_person(device_user_id):
    if not device_user_id:
        return None, None, ""

    link = (
        DeviceUserLink.objects.select_related("member", "staff")
        .filter(device_user_id=str(device_user_id), is_active=True)
        .first()
    )
    if link:
        if link.member:
            return link.member, None, AttendanceLog.PersonType.MEMBER
        if link.staff:
            return None, link.staff, AttendanceLog.PersonType.STAFF

    member = (
        Member.objects.filter(
            Q(device_user_id=str(device_user_id)) | Q(member_id=str(device_user_id))
        )
        .first()
    )
    if member:
        return member, None, AttendanceLog.PersonType.MEMBER

    staff = (
        Staff.objects.filter(
            Q(device_user_id=str(device_user_id)) | Q(staff_id=str(device_user_id))
        )
        .first()
    )
    if staff:
        return None, staff, AttendanceLog.PersonType.STAFF

    return None, None, ""


def _detect_event_type(request, query, xml_fields, body_text, text_rows):
    path = request.path.lower()
    table = (query.get("table") or xml_fields.get("table") or "").upper()

    if "getrequest" in path:
        return BiometricRawEvent.EventType.COMMAND_POLL

    if request.method == "GET" and "cdata" in path:
        return BiometricRawEvent.EventType.HEARTBEAT

    if table == "ATTLOG" or text_rows:
        return BiometricRawEvent.EventType.ATTENDANCE

    if table in {"OPERLOG", "OPLOG"}:
        return BiometricRawEvent.EventType.UNKNOWN

    if body_text.strip():
        return BiometricRawEvent.EventType.UNKNOWN

    return BiometricRawEvent.EventType.HEARTBEAT


def _create_raw_event(device, event_type, remote_ip, device_user_id, event_time, payload, parsed_ok, notes=""):
    return BiometricRawEvent.objects.create(
        device=device,
        event_type=event_type,
        remote_ip=remote_ip or "",
        device_user_id=device_user_id or "",
        event_time=event_time or timezone.now(),
        payload=(payload or "")[:10000],
        parsed_ok=parsed_ok,
        notes=notes,
    )


def _attendance_already_exists(member, staff, device, device_user_id, event_dt):
    start = event_dt - timedelta(seconds=3)
    end = event_dt + timedelta(seconds=3)

    qs = AttendanceLog.objects.filter(
        check_in_time__gte=start,
        check_in_time__lte=end,
        device_user_id=str(device_user_id or ""),
    )

    if device:
        qs = qs.filter(device=device)

    if member:
        qs = qs.filter(member=member)
    elif staff:
        qs = qs.filter(staff=staff)

    return qs.exists()


def _save_attendance_row(device, row, remote_ip, source_label="device_push"):
    device_user_id = (
        row.get("pin")
        or row.get("id")
        or row.get("uid")
        or row.get("userid")
        or ""
    ).strip()
    checktime_raw = (
        row.get("checktime")
        or row.get("time")
        or row.get("datetime")
        or row.get("timestamp")
        or ""
    ).strip()

    event_dt = _parse_device_datetime(checktime_raw)
    if not device_user_id or not event_dt:
        BiometricSyncLog.objects.create(
            device=device,
            action=BiometricSyncLog.Action.RAW_EVENT,
            device_user_id=device_user_id,
            success=False,
            payload=json.dumps(row),
            response="Skipped",
            notes="Missing device_user_id or invalid datetime.",
        )
        _create_raw_event(
            device=device,
            event_type=BiometricRawEvent.EventType.ATTENDANCE,
            remote_ip=remote_ip,
            device_user_id=device_user_id,
            event_time=timezone.now(),
            payload=json.dumps(row),
            parsed_ok=False,
            notes="Missing device_user_id or invalid datetime.",
        )
        return False

    member, staff, person_type = _resolve_person(device_user_id)

    _create_raw_event(
        device=device,
        event_type=BiometricRawEvent.EventType.ATTENDANCE,
        remote_ip=remote_ip,
        device_user_id=device_user_id,
        event_time=event_dt,
        payload=json.dumps(row),
        parsed_ok=bool(member or staff),
        notes="" if (member or staff) else "No linked member/staff found.",
    )

    if not member and not staff:
        BiometricSyncLog.objects.create(
            device=device,
            action=BiometricSyncLog.Action.RAW_EVENT,
            device_user_id=device_user_id,
            success=False,
            payload=json.dumps(row),
            response="Unlinked user",
            notes="No active DeviceUserLink/member/staff match found.",
        )
        return False

    if _attendance_already_exists(member, staff, device, device_user_id, event_dt):
        BiometricSyncLog.objects.create(
            device=device,
            member=member,
            staff=staff,
            action=BiometricSyncLog.Action.RAW_EVENT,
            device_user_id=device_user_id,
            success=True,
            payload=json.dumps(row),
            response="Duplicate skipped",
            notes="Duplicate attendance within 3-second window.",
        )
        return True

    AttendanceLog.objects.create(
        member=member,
        staff=staff,
        date=timezone.localtime(event_dt).date(),
        check_in_time=event_dt,
        source=AttendanceLog.Source.DEVICE,
        verification_mode=AttendanceLog.VerificationMode.DEVICE,
        device=device,
        device_identifier=device.serial_number if device else "",
        device_user_id=device_user_id,
        status=AttendanceLog.Status.PRESENT,
        remarks=f"Imported from {source_label}",
    )

    BiometricSyncLog.objects.create(
        device=device,
        member=member,
        staff=staff,
        action=BiometricSyncLog.Action.DEVICE_SYNC,
        device_user_id=device_user_id,
        success=True,
        payload=json.dumps(row),
        response="Attendance log saved",
        notes="Attendance imported successfully.",
    )
    return True


def _pending_command_for_device(device):
    if not device:
        return None
    return (
        BiometricDeviceCommand.objects.filter(
            device=device,
            status=BiometricDeviceCommand.Status.PENDING,
        )
        .order_by("queued_at", "id")
        .first()
    )


def _render_command_text(command):
    payload = (command.payload or "").strip()
    if payload:
        return payload
    return f"C:{command.id}:{command.command}:{command.device_user_id}"


@csrf_exempt
@require_http_methods(["GET", "POST"])
def biometric_device_cdata(request):
    body_text = request.body.decode("utf-8", errors="ignore")
    xml_fields = _parse_xml_fields(body_text)
    json_payload = _parse_json_payload(body_text)
    text_rows = _parse_plain_text_rows(body_text)
    remote_ip = _client_ip(request)
    query = _clean_querydict(request.GET)

    snapshot = _request_snapshot(request, body_text, xml_fields, text_rows, json_payload)
    logger.info("Biometric request: %s", json.dumps(snapshot, default=str))

    serial_number = _extract_serial(request, xml_fields=xml_fields, json_payload=json_payload)
    device = _get_or_create_device(serial_number, payload=body_text or json.dumps(snapshot), remote_ip=remote_ip)

    event_type = _detect_event_type(request, query, xml_fields, body_text, text_rows)

    if request.method == "GET":
        _create_raw_event(
            device=device,
            event_type=event_type,
            remote_ip=remote_ip,
            device_user_id="",
            event_time=timezone.now(),
            payload=request.get_full_path(),
            parsed_ok=True,
            notes="GET cdata handshake/options request.",
        )
        return HttpResponse("OK", content_type="text/plain")

    if event_type == BiometricRawEvent.EventType.ATTENDANCE:
        saved_count = 0
        for row in text_rows:
            if _save_attendance_row(device, row, remote_ip, source_label="MB20/AiFace push"):
                saved_count += 1
        return HttpResponse(f"OK:{saved_count}", content_type="text/plain")

    _create_raw_event(
        device=device,
        event_type=event_type,
        remote_ip=remote_ip,
        device_user_id="",
        event_time=timezone.now(),
        payload=body_text,
        parsed_ok=True,
        notes="Non-ATTLOG cdata payload received.",
    )
    return HttpResponse("OK", content_type="text/plain")


@csrf_exempt
@require_http_methods(["GET"])
def biometric_get_request(request):
    remote_ip = _client_ip(request)
    serial_number = _extract_serial(request)
    device = _get_or_create_device(serial_number, payload=request.get_full_path(), remote_ip=remote_ip)

    _create_raw_event(
        device=device,
        event_type=BiometricRawEvent.EventType.COMMAND_POLL,
        remote_ip=remote_ip,
        device_user_id="",
        event_time=timezone.now(),
        payload=request.get_full_path(),
        parsed_ok=True,
        notes="Device polled for pending commands.",
    )

    command = _pending_command_for_device(device)
    if not command:
        return HttpResponse("OK", content_type="text/plain")

    command_text = _render_command_text(command)
    command.mark_sent(response_payload=command_text)

    BiometricSyncLog.objects.create(
        device=device,
        member=command.member,
        staff=command.staff,
        action=BiometricSyncLog.Action.COMMAND,
        device_user_id=command.device_user_id,
        success=True,
        payload=command.payload,
        response=command_text,
        notes="Command sent to device via getrequest.",
    )

    return HttpResponse(command_text, content_type="text/plain")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def biometric_endpoint(request):
    if request.method == "GET":
        return HttpResponse("OK", content_type="text/plain")
    return biometric_device_cdata(request)


@csrf_exempt
@require_http_methods(["POST", "GET"])
def ebioserver_webhook(request):
    body_text = request.body.decode("utf-8", errors="ignore")
    remote_ip = _client_ip(request)

    if request.method == "GET":
        return HttpResponse("OK", content_type="text/plain")

    json_payload = _parse_json_payload(body_text)
    xml_fields = _parse_xml_fields(body_text)

    BiometricSyncLog.objects.create(
        action=BiometricSyncLog.Action.RAW_EVENT,
        success=True,
        payload=body_text[:10000],
        response="OK",
        notes=f"eBioServer webhook received from {remote_ip}",
    )

    _create_raw_event(
        device=None,
        event_type=BiometricRawEvent.EventType.UNKNOWN,
        remote_ip=remote_ip,
        device_user_id="",
        event_time=timezone.now(),
        payload=body_text[:10000],
        parsed_ok=bool(json_payload or xml_fields or body_text.strip()),
        notes="eBioServer webhook payload received.",
    )

    return HttpResponse("OK", content_type="text/plain")
