import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from accounts.models import UserAccount
from members.models import Member
from staffs.models import Staff
from .biometric import BiometricSyncService
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
from .services import create_attendance_attempt, evaluate_member_access, evaluate_staff_access

logger = logging.getLogger('biometric')


class AttendanceAccessMixin(LoginRequiredMixin):
    def get_member_profile(self):
        return getattr(self.request.user, 'member_profile', None)

    def get_staff_profile(self):
        return getattr(self.request.user, 'staff_profile', None)

    def is_owner(self):
        return getattr(self.request.user, 'role', None) == UserAccount.ROLE_OWNER

    def is_member(self):
        return getattr(self.request.user, 'role', None) == UserAccount.ROLE_MEMBER

    def is_staff_user(self):
        return getattr(self.request.user, 'role', None) == UserAccount.ROLE_STAFF

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
        raise PermissionDenied('You are not authorized to access this attendance record.')


class AttendanceListView(AttendanceAccessMixin, ListView):
    model = AttendanceLog
    template_name = 'attendance/attendance_list.html'
    context_object_name = 'attendance_list'
    paginate_by = 15

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related('member', 'staff', 'device')
            .order_by('-date', '-check_in_time')
        )
        person_type = self.request.GET.get('person_type')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        query = self.request.GET.get('q')

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
                | Q(device__serial_number__icontains=query)
                | Q(device__device_name__icontains=query)
            )
        return self.get_allowed_attendance_queryset(queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person_type'] = self.request.GET.get('person_type', '')
        context['start_date'] = self.request.GET.get('start_date', '')
        context['end_date'] = self.request.GET.get('end_date', '')
        context['q'] = self.request.GET.get('q', '')
        return context


class AttendanceCreateView(LoginRequiredMixin, CreateView):
    model = AttendanceLog
    form_class = AttendanceLogForm
    template_name = 'attendance/attendance_form.html'
    success_url = reverse_lazy('attendance:attendance_list')


class AttendanceUpdateView(LoginRequiredMixin, UpdateView):
    model = AttendanceLog
    form_class = AttendanceLogForm
    template_name = 'attendance/attendance_form.html'
    success_url = reverse_lazy('attendance:attendance_list')


class AttendanceDetailView(AttendanceAccessMixin, DetailView):
    model = AttendanceLog
    template_name = 'attendance/attendance_detail.html'
    context_object_name = 'attendance'

    def get_object(self, queryset=None):
        attendance = super().get_object(queryset=queryset)
        return self.ensure_attendance_access(attendance)


class MemberAttendanceHistoryView(AttendanceAccessMixin, DetailView):
    model = Member
    template_name = 'attendance/member_history.html'
    context_object_name = 'member'

    def get_object(self):
        member = get_object_or_404(Member, pk=self.kwargs['member_pk'])
        if self.is_owner():
            return member
        if self.is_member() and member == self.get_member_profile():
            return member
        raise PermissionDenied("You do not have permission to view another member's attendance history.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.object
        context['attendance_list'] = member.attendance_logs.select_related('device').order_by('-check_in_time')[:20]
        return context


class StaffAttendanceHistoryView(AttendanceAccessMixin, DetailView):
    model = Staff
    template_name = 'attendance/staff_history.html'
    context_object_name = 'staff'

    def get_object(self):
        staff = get_object_or_404(Staff, pk=self.kwargs['staff_pk'])
        if self.is_owner():
            return staff
        if self.is_staff_user() and staff == self.get_staff_profile():
            return staff
        raise PermissionDenied("You do not have permission to view another staff member's attendance history.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff = self.object
        context['attendance_list'] = staff.attendance_logs.select_related('device').order_by('-check_in_time')[:20]
        return context


def extract_headers(request):
    headers = {}
    for key, value in request.META.items():
        if key.startswith('HTTP_') or key in ('CONTENT_TYPE', 'CONTENT_LENGTH', 'REMOTE_ADDR'):
            headers[key] = value
    return headers


def parse_xml(raw_body):
    parsed = {}
    if not raw_body or not raw_body.strip().startswith('<'):
        return parsed
    try:
        root = ET.fromstring(raw_body)
        for element in root.iter():
            if element.text and element.tag:
                parsed[element.tag.lower()] = element.text.strip()
    except ET.ParseError:
        logger.warning('Failed to parse XML biometric payload.')
    return parsed


def parse_plain_text_rows(raw_body):
    rows = []
    if not raw_body:
        return rows

    for line in raw_body.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            continue

        parsed_line = {}
        tokens = stripped_line.replace('\t', ' ').split()

        if '=' in stripped_line:
            index = 0
            while index < len(tokens):
                token = tokens[index]
                if '=' not in token:
                    index += 1
                    continue
                key, value = token.split('=', 1)
                key = key.lower()
                if key in {'datetime', 'date', 'time', 'stamp'} and index + 1 < len(tokens):
                    next_token = tokens[index + 1]
                    if ':' in next_token and '=' not in next_token:
                        value = f'{value} {next_token}'
                        index += 1
                parsed_line[key] = value.strip()
                index += 1
        else:
            parsed_line['id'] = tokens[0] if tokens else None
            parsed_line['_split_cols'] = tokens
            parsed_line['_raw'] = stripped_line

        if parsed_line:
            rows.append(parsed_line)

    return rows


def extract_device_user_id(*sources):
    candidate_fields = [
        'pin',
        'uid',
        'userid',
        'user_id',
        'member_id',
        'staff_id',
        'code',
        'id',
    ]
    for field in candidate_fields:
        for source in sources:
            if isinstance(source, dict):
                val = source.get(field) or source.get(field.upper())
                if val:
                    return str(val).strip()
    return None


def extract_device_serial(*sources):
    for source in sources:
        if isinstance(source, dict):
            val = source.get('sn') or source.get('SN') or source.get('serial') or source.get('SERIAL')
            if val:
                return str(val).strip()
    return None


def parse_device_timestamp(value):
    if not value:
        return None

    for fmt in (
        '%Y-%m-%d %H:%M:%S',
        '%Y/%m/%d %H:%M:%S',
        '%d-%m-%Y %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y%m%d%H%M%S',
    ):
        try:
            naive_dt = datetime.strptime(value, fmt)
            return timezone.make_aware(naive_dt, timezone.get_current_timezone())
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(value)
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    except ValueError:
        return None


def render_device_response(request, status_text='OK'):
    raw_body = request.body.decode('utf-8', errors='ignore')
    if 'xml' in (request.content_type or '') or raw_body.strip().startswith('<'):
        return HttpResponse(f'<Response>{status_text}</Response>', content_type='application/xml')
    return HttpResponse(status_text, content_type='text/plain')


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def get_or_create_device(device_serial, raw_body='', request=None):
    if not device_serial:
        return None

    device, created = BiometricDevice.objects.get_or_create(
        serial_number=device_serial,
        defaults={'device_name': device_serial},
    )
    remote_ip = get_client_ip(request) if request is not None else None
    device.touch_heartbeat(raw_body or '', remote_ip=remote_ip)
    return device


def update_device_record(device_serial, raw_body, request=None):
    return get_or_create_device(device_serial, raw_body=raw_body, request=request)


def create_raw_event(device, event_type, request, raw_body, device_user_id='', parsed_ok=False, notes=''):
    return BiometricRawEvent.objects.create(
        device=device,
        event_type=event_type,
        remote_ip=get_client_ip(request),
        device_user_id=device_user_id or '',
        event_time=timezone.now(),
        payload=raw_body or '',
        parsed_ok=parsed_ok,
        notes=notes,
    )


def log_sync_event(action, device=None, member=None, staff=None, device_user_id='', success=True, payload='', response='', notes=''):
    BiometricSyncLog.objects.create(
        device=device,
        member=member,
        staff=staff,
        action=action,
        device_user_id=device_user_id or '',
        success=success,
        payload=payload or '',
        response=response or '',
        notes=notes or '',
    )


def get_target_by_device_user_id(device_user_id):
    if not device_user_id:
        return None

    link = (
        DeviceUserLink.objects
        .select_related('member', 'staff')
        .filter(device_user_id=device_user_id, is_active=True)
        .first()
    )
    if link:
        return link.member or link.staff

    target = Member.objects.filter(device_user_id=device_user_id).select_related('user').first()
    if target:
        return target

    target = Staff.objects.filter(device_user_id=device_user_id).select_related('user').first()
    if target:
        return target

    target = Member.objects.filter(member_id=device_user_id).select_related('user').first()
    if target:
        return target

    target = Staff.objects.filter(staff_id=device_user_id).select_related('user').first()
    if target:
        return target

    return None


def ensure_device_user_link(target, device_user_id):
    if not target or not device_user_id:
        return None

    defaults = {'is_active': True}
    if isinstance(target, Member):
        link, _ = DeviceUserLink.objects.get_or_create(
            device_user_id=device_user_id,
            defaults={**defaults, 'member': target},
        )
        if link.member_id != target.id or link.staff_id is not None or not link.is_active:
            link.member = target
            link.staff = None
            link.is_active = True
            link.save(update_fields=['member', 'staff', 'is_active'])
        return link

    if isinstance(target, Staff):
        link, _ = DeviceUserLink.objects.get_or_create(
            device_user_id=device_user_id,
            defaults={**defaults, 'staff': target},
        )
        if link.staff_id != target.id or link.member_id is not None or not link.is_active:
            link.staff = target
            link.member = None
            link.is_active = True
            link.save(update_fields=['staff', 'member', 'is_active'])
        return link

    return None


def get_member_device_status(member, device):
    if not member or not device:
        return None
    status_obj, _ = MemberBiometricDeviceStatus.objects.get_or_create(
        member=member,
        device=device,
        defaults={'device_user_id': member.device_user_id or member.member_id},
    )
    expected_id = member.device_user_id or member.member_id
    if status_obj.device_user_id != expected_id:
        status_obj.device_user_id = expected_id
        status_obj.save(update_fields=['device_user_id'])
    return status_obj


def get_staff_device_status(staff, device):
    if not staff or not device:
        return None
    status_obj, _ = StaffBiometricDeviceStatus.objects.get_or_create(
        staff=staff,
        device=device,
        defaults={'device_user_id': staff.device_user_id or staff.staff_id},
    )
    expected_id = staff.device_user_id or staff.staff_id
    if status_obj.device_user_id != expected_id:
        status_obj.device_user_id = expected_id
        status_obj.save(update_fields=['device_user_id'])
    return status_obj


def deny_expired_member(target):
    if isinstance(target, Member):
        target.status = Member.STATUS_INACTIVE
        target.save(update_fields=['status'])
        if target.user:
            target.user.is_active = False
            target.user.save(update_fields=['is_active'])


def get_primary_payload(post_data, xml_fields, plain_text_rows, json_payload):
    if plain_text_rows:
        return plain_text_rows[0]
    if post_data:
        return post_data
    if xml_fields:
        return xml_fields
    if json_payload:
        return json_payload
    return {}


def normalize_request_payload(request):
    raw_body = request.body.decode('utf-8', errors='ignore')
    headers = extract_headers(request)
    query_data = {k.lower(): v for k, v in request.GET.items()}
    post_data = {k.lower(): v for k, v in request.POST.items()}
    xml_fields = parse_xml(raw_body)
    plain_text_rows = parse_plain_text_rows(raw_body)
    json_payload = None

    if 'json' in (request.content_type or '') and raw_body:
        try:
            json_payload = json.loads(raw_body)
        except json.JSONDecodeError:
            json_payload = None

    return {
        'method': request.method,
        'path': request.path,
        'headers': headers,
        'raw_body': raw_body,
        'post_data': post_data,
        'query_data': query_data,
        'plain_text_rows': plain_text_rows,
        'xml_fields': xml_fields,
        'json_payload': json_payload,
    }


def log_biometric_request(request, payload):
    logger.info('Biometric request received: %s', json.dumps(payload, default=str))


def record_access_attempt(target, decision, device, device_user_id, device_timestamp, granted):
    if isinstance(target, Member):
        attendance, duplicate = create_attendance_attempt(
            'member',
            target,
            source=AttendanceLog.Source.DEVICE,
            verification_mode=AttendanceLog.VerificationMode.BIOMETRIC,
            device_id=device.serial_number if device else '',
            device_user_id=device_user_id,
            remarks='Biometric attendance from device'
            if granted else f'Access denied by software rules: {decision.get("reason")}',
            status=AttendanceLog.Status.PRESENT if granted else AttendanceLog.Status.ABSENT,
            check_in_time=device_timestamp,
        )
        return attendance, duplicate

    if isinstance(target, Staff):
        attendance, duplicate = create_attendance_attempt(
            'staff',
            target,
            source=AttendanceLog.Source.DEVICE,
            verification_mode=AttendanceLog.VerificationMode.BIOMETRIC,
            device_id=device.serial_number if device else '',
            device_user_id=device_user_id,
            remarks='Biometric attendance from device'
            if granted else f'Access denied by software rules: {decision.get("reason")}',
            status=AttendanceLog.Status.PRESENT if granted else AttendanceLog.Status.ABSENT,
            check_in_time=device_timestamp,
        )
        return attendance, duplicate

    return None, False


def dispatch_biometric_request(request, payload, device_user_id, device_serial, device_timestamp):
    device = update_device_record(device_serial, payload.get('raw_body', ''), request=request)
    target = get_target_by_device_user_id(device_user_id)

    create_raw_event(
        device=device,
        event_type=BiometricRawEvent.EventType.ATTENDANCE,
        request=request,
        raw_body=payload.get('raw_body', ''),
        device_user_id=device_user_id or '',
        parsed_ok=bool(device_user_id),
        notes='Attendance event received from biometric endpoint.',
    )

    if not target:
        log_sync_event(
            action=BiometricSyncLog.Action.ACCESS_ATTEMPT,
            device=device,
            device_user_id=device_user_id or '',
            success=False,
            payload=json.dumps(payload, default=str),
            response='ERR_USER_NOT_FOUND',
            notes='Could not match device user ID to member or staff.',
        )
        return render_device_response(request, status_text='ERR_USER_NOT_FOUND')

    ensure_device_user_link(target, device_user_id)

    if isinstance(target, Member):
        status_obj = get_member_device_status(target, device) if device else None
        decision = evaluate_member_access(target)
        granted = bool(decision.get('gym_access'))

        if not granted:
            deny_expired_member(target)
            attendance, duplicate = record_access_attempt(target, decision, device, device_user_id, device_timestamp, False)
            if status_obj:
                status_obj.last_status_checked_at = timezone.now()
                status_obj.is_enabled_on_device = False
                status_obj.notes = f'Access denied: {decision.get("reason")}'
                status_obj.save(update_fields=['last_status_checked_at', 'is_enabled_on_device', 'notes'])
            log_sync_event(
                action=BiometricSyncLog.Action.ACCESS_ATTEMPT,
                device=device,
                member=target,
                device_user_id=device_user_id,
                success=False,
                payload=json.dumps(payload, default=str),
                response='DENY',
                notes=decision.get('reason', ''),
            )
            return render_device_response(request, status_text='DENY')

        attendance, duplicate = record_access_attempt(target, decision, device, device_user_id, device_timestamp, True)
        if status_obj:
            status_obj.last_status_checked_at = timezone.now()
            status_obj.is_enabled_on_device = True
            status_obj.notes = 'Attendance accepted by software rules.'
            status_obj.save(update_fields=['last_status_checked_at', 'is_enabled_on_device', 'notes'])
        log_sync_event(
            action=BiometricSyncLog.Action.ACCESS_ATTEMPT,
            device=device,
            member=target,
            device_user_id=device_user_id,
            success=True,
            payload=json.dumps(payload, default=str),
            response='OK',
            notes='Attendance recorded.' if attendance else 'Duplicate attendance skipped.',
        )
        return render_device_response(request, status_text='OK')

    if isinstance(target, Staff):
        status_obj = get_staff_device_status(target, device) if device else None
        decision = evaluate_staff_access(target)
        granted = bool(decision.get('is_staff_active'))

        if not granted:
            attendance, duplicate = record_access_attempt(target, decision, device, device_user_id, device_timestamp, False)
            if status_obj:
                status_obj.last_status_checked_at = timezone.now()
                status_obj.is_enabled_on_device = False
                status_obj.notes = f'Access denied: {decision.get("reason")}'
                status_obj.save(update_fields=['last_status_checked_at', 'is_enabled_on_device', 'notes'])
            log_sync_event(
                action=BiometricSyncLog.Action.ACCESS_ATTEMPT,
                device=device,
                staff=target,
                device_user_id=device_user_id,
                success=False,
                payload=json.dumps(payload, default=str),
                response='DENY',
                notes=decision.get('reason', ''),
            )
            return render_device_response(request, status_text='DENY')

        attendance, duplicate = record_access_attempt(target, decision, device, device_user_id, device_timestamp, True)
        if status_obj:
            status_obj.last_status_checked_at = timezone.now()
            status_obj.is_enabled_on_device = True
            status_obj.notes = 'Attendance accepted by software rules.'
            status_obj.save(update_fields=['last_status_checked_at', 'is_enabled_on_device', 'notes'])
        log_sync_event(
            action=BiometricSyncLog.Action.ACCESS_ATTEMPT,
            device=device,
            staff=target,
            device_user_id=device_user_id,
            success=True,
            payload=json.dumps(payload, default=str),
            response='OK',
            notes='Attendance recorded.' if attendance else 'Duplicate attendance skipped.',
        )
        return render_device_response(request, status_text='OK')

    return render_device_response(request, status_text='DENY')


def build_device_command_text(command):
    command_id = command.pk
    user_id = command.device_user_id

    if command.command == BiometricDeviceCommand.CommandType.DELETE_USER:
        return f'C:{command_id}:DATA DEL_USER PIN={user_id}'
    if command.command == BiometricDeviceCommand.CommandType.DISABLE_USER:
        return f'C:{command_id}:DATA UPDATE USERINFO PIN={user_id}\tActive=0'
    if command.command == BiometricDeviceCommand.CommandType.ENABLE_USER:
        return f'C:{command_id}:DATA UPDATE USERINFO PIN={user_id}\tActive=1'
    if command.command == BiometricDeviceCommand.CommandType.SYNC_FACE:
        return f'C:{command_id}:DATA UPDATE FACE PIN={user_id}'
    if command.command == BiometricDeviceCommand.CommandType.SYNC_FINGERPRINT:
        return f'C:{command_id}:DATA UPDATE FINGERTMP PIN={user_id}'
    if command.command == BiometricDeviceCommand.CommandType.SYNC_PASSWORD:
        return f'C:{command_id}:DATA UPDATE USERINFO PIN={user_id}'
    if command.command in {
        BiometricDeviceCommand.CommandType.SYNC_USER,
        BiometricDeviceCommand.CommandType.REFRESH_USER,
    }:
        return f'C:{command_id}:DATA UPDATE USERINFO PIN={user_id}'
    return f'C:{command_id}:DATA UPDATE USERINFO PIN={user_id}'


def queue_member_device_command(member, device, command_type, notes=''):
    command = BiometricDeviceCommand.objects.create(
        device=device,
        member=member,
        command=command_type,
        device_user_id=member.device_user_id or member.member_id,
        notes=notes,
    )
    status_obj = get_member_device_status(member, device)
    if command_type in {
        BiometricDeviceCommand.CommandType.SYNC_USER,
        BiometricDeviceCommand.CommandType.SYNC_FACE,
        BiometricDeviceCommand.CommandType.SYNC_FINGERPRINT,
        BiometricDeviceCommand.CommandType.SYNC_PASSWORD,
        BiometricDeviceCommand.CommandType.REFRESH_USER,
        BiometricDeviceCommand.CommandType.ENABLE_USER,
    }:
        status_obj.mark_sync_sent()
    return command


def queue_staff_device_command(staff, device, command_type, notes=''):
    command = BiometricDeviceCommand.objects.create(
        device=device,
        staff=staff,
        command=command_type,
        device_user_id=staff.device_user_id or staff.staff_id,
        notes=notes,
    )
    status_obj = get_staff_device_status(staff, device)
    if command_type in {
        BiometricDeviceCommand.CommandType.SYNC_USER,
        BiometricDeviceCommand.CommandType.SYNC_FACE,
        BiometricDeviceCommand.CommandType.SYNC_FINGERPRINT,
        BiometricDeviceCommand.CommandType.SYNC_PASSWORD,
        BiometricDeviceCommand.CommandType.REFRESH_USER,
        BiometricDeviceCommand.CommandType.ENABLE_USER,
    }:
        status_obj.mark_sync_sent()
    return command


@require_http_methods(['GET', 'POST'])
@csrf_exempt
def device_sync_status(request):
    query = request.GET.dict() if request.method == 'GET' else request.POST.dict()
    serial_number = query.get('device_serial') or query.get('sn') or query.get('serial')
    if not serial_number:
        return JsonResponse({'ok': False, 'error': 'device_serial query parameter is required.'}, status=400)

    device = BiometricDevice.objects.filter(serial_number=serial_number).first()
    if not device:
        return JsonResponse({'ok': False, 'error': 'Unknown device serial.'}, status=404)

    adapter = BiometricSyncService(device)
    status = adapter.probe()
    return JsonResponse(
        {
            'ok': True,
            'device': {
                'serial_number': device.serial_number,
                'device_name': device.device_name,
                'device_type': device.device_type,
                'firmware_version': device.firmware_version,
                'is_active': device.is_active,
                'last_seen_at': device.last_seen_at.isoformat() if device.last_seen_at else None,
                'last_sync_at': device.last_sync_at.isoformat() if device.last_sync_at else None,
                'last_known_ip': device.last_known_ip,
            },
            'sync_status': status,
        }
    )


@csrf_exempt
@require_http_methods(['POST'])
def device_enrollment(request):
    try:
        payload = json.loads(request.body or '{}') if request.content_type and 'json' in request.content_type else request.POST.dict()
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON payload.'}, status=400)

    serial_number = payload.get('device_serial') or payload.get('serial') or payload.get('sn')
    device_user_id = (
        payload.get('device_user_id')
        or payload.get('pin')
        or payload.get('uid')
        or payload.get('user_id')
        or payload.get('userid')
    )
    member_id = payload.get('member_id')
    staff_id = payload.get('staff_id')

    if not serial_number or not device_user_id or not (member_id or staff_id):
        return JsonResponse(
            {
                'ok': False,
                'error': 'device_serial, device_user_id, and member_id or staff_id are required.',
            },
            status=400,
        )

    device = get_or_create_device(serial_number, raw_body=json.dumps(payload, default=str), request=request)

    target = None
    if member_id:
        target = Member.objects.filter(member_id=member_id).select_related('user').first()
        if not target:
            return JsonResponse({'ok': False, 'error': 'Unknown member_id.'}, status=404)
        ensure_device_user_link(target, device_user_id)
        status_obj = get_member_device_status(target, device)
    else:
        target = Staff.objects.filter(staff_id=staff_id).select_related('user').first()
        if not target:
            return JsonResponse({'ok': False, 'error': 'Unknown staff_id.'}, status=404)
        ensure_device_user_link(target, device_user_id)
        status_obj = get_staff_device_status(target, device)

    sync_service = BiometricSyncService(device)
    sync_result = sync_service.push_enrollment(target, device_user_id)

    if sync_result.get('ok'):
        status_obj.mark_sync_success()
    else:
        status_obj.mark_sync_failed(sync_result.get('error') or 'Enrollment push failed.')

    log_sync_event(
        action=BiometricSyncLog.Action.ENROLLMENT,
        device=device,
        member=target if isinstance(target, Member) else None,
        staff=target if isinstance(target, Staff) else None,
        device_user_id=device_user_id,
        success=bool(sync_result.get('ok')),
        payload=json.dumps(payload, default=str),
        response=json.dumps(sync_result, default=str),
        notes='Enrollment API request processed.',
    )

    return JsonResponse(
        {
            'ok': sync_result.get('ok', False),
            'result': sync_result,
            'device_serial': device.serial_number,
            'device_user_id': device_user_id,
            'member_id': getattr(target, 'member_id', None),
            'staff_id': getattr(target, 'staff_id', None),
        },
        status=200 if sync_result.get('ok', False) else 409,
    )


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def biometric_get_request(request):
    payload = normalize_request_payload(request)
    log_biometric_request(request, payload)

    primary_payload = get_primary_payload(
        payload['post_data'],
        payload['xml_fields'],
        payload['plain_text_rows'],
        payload['json_payload'],
    )
    device_serial = extract_device_serial(
        payload['query_data'],
        payload['post_data'],
        payload['xml_fields'],
        primary_payload,
        payload['json_payload'] or {},
    )
    device_user_id = extract_device_user_id(primary_payload, payload['query_data'])
    device = update_device_record(device_serial, payload['raw_body'], request=request)

    create_raw_event(
        device=device,
        event_type=BiometricRawEvent.EventType.COMMAND_POLL,
        request=request,
        raw_body=payload['raw_body'],
        device_user_id=device_user_id or '',
        parsed_ok=True,
        notes='Device poll endpoint hit.',
    )
    log_sync_event(
        action=BiometricSyncLog.Action.DEVICE_HEARTBEAT,
        device=device,
        device_user_id=device_user_id or '',
        success=True,
        payload=json.dumps(payload, default=str),
        response='OK',
        notes='Device poll/heartbeat received.',
    )
    return HttpResponse('OK', content_type='text/plain')


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def bridge_entry(request):
    try:
        payload = json.loads(request.body or '{}') if request.content_type and 'json' in request.content_type else request.POST.dict()
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON payload.'}, status=400)

    member_id = payload.get('member_id') or payload.get('user_id')
    staff_id = payload.get('staff_id')
    entry_time = payload.get('entry_time') or payload.get('check_in_time')

    if member_id:
        member = Member.objects.filter(member_id=member_id).select_related('user').first()
        if not member:
            return JsonResponse({'ok': False, 'error': 'Unknown member_id.'}, status=404)

        decision = evaluate_member_access(member)
        attendance, duplicate = create_attendance_attempt(
            'member',
            member,
            source=AttendanceLog.Source.DEVICE,
            verification_mode=AttendanceLog.VerificationMode.DEVICE,
            device_id=payload.get('device_id', 'bridge'),
            device_user_id=member.device_user_id or member.member_id,
            remarks='Bridge attendance attempt' if decision['gym_access'] else 'Bridge access denied by software rules',
            status=AttendanceLog.Status.PRESENT if decision['gym_access'] else AttendanceLog.Status.ABSENT,
        )
        return JsonResponse(
            {
                'ok': True,
                'user_type': 'member',
                'member_id': member.member_id,
                'member_name': member.full_name,
                'entry_time': entry_time,
                'gym_access': decision['gym_access'],
                'attendance_created': attendance is not None,
                'duplicate_daily_attendance': duplicate,
                'reason': decision.get('reason'),
            }
        )

    if staff_id:
        staff = Staff.objects.filter(staff_id=staff_id).select_related('user').first()
        if not staff:
            return JsonResponse({'ok': False, 'error': 'Unknown staff_id.'}, status=404)

        decision = evaluate_staff_access(staff)
        attendance, duplicate = create_attendance_attempt(
            'staff',
            staff,
            source=AttendanceLog.Source.DEVICE,
            verification_mode=AttendanceLog.VerificationMode.DEVICE,
            device_id=payload.get('device_id', 'bridge'),
            device_user_id=staff.device_user_id or staff.staff_id,
            remarks='Bridge attendance attempt' if decision['is_staff_active'] else 'Bridge staff access denied by software rules',
            status=AttendanceLog.Status.PRESENT if decision['is_staff_active'] else AttendanceLog.Status.ABSENT,
        )
        return JsonResponse(
            {
                'ok': True,
                'user_type': 'staff',
                'staff_id': staff.staff_id,
                'staff_name': staff.full_name,
                'entry_time': entry_time,
                'is_staff_active': decision['is_staff_active'],
                'attendance_created': attendance is not None,
                'duplicate_daily_attendance': duplicate,
                'reason': decision.get('reason'),
            }
        )

    return JsonResponse({'ok': False, 'error': 'Provide member_id or staff_id.'}, status=400)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def access_sync(request):
    try:
        payload = json.loads(request.body or '{}') if request.content_type and 'json' in request.content_type else request.POST.dict()
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON payload.'}, status=400)

    member_id = payload.get('member_id')
    staff_id = payload.get('staff_id')

    if member_id:
        member = Member.objects.filter(member_id=member_id).select_related('user').first()
        if not member:
            return JsonResponse({'ok': False, 'error': 'Unknown member_id.'}, status=404)
        decision = evaluate_member_access(member)
        return JsonResponse(
            {
                'ok': True,
                'user_type': 'member',
                'member_id': member.member_id,
                'member_name': member.full_name,
                'gym_access': decision['gym_access'],
                'reason': decision.get('reason'),
            }
        )

    if staff_id:
        staff = Staff.objects.filter(staff_id=staff_id).select_related('user').first()
        if not staff:
            return JsonResponse({'ok': False, 'error': 'Unknown staff_id.'}, status=404)
        decision = evaluate_staff_access(staff)
        return JsonResponse(
            {
                'ok': True,
                'user_type': 'staff',
                'staff_id': staff.staff_id,
                'staff_name': staff.full_name,
                'is_staff_active': decision['is_staff_active'],
                'reason': decision.get('reason'),
            }
        )

    return JsonResponse({'ok': False, 'error': 'Provide member_id or staff_id.'}, status=400)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def iclock_cdata(request):
    payload = normalize_request_payload(request)
    log_biometric_request(request, payload)

    plain_text_rows = payload['plain_text_rows']
    primary_payload = get_primary_payload(
        payload['post_data'],
        payload['xml_fields'],
        plain_text_rows,
        payload['json_payload'],
    )
    device_serial = extract_device_serial(
        payload['query_data'],
        payload['post_data'],
        payload['xml_fields'],
        primary_payload,
        payload['json_payload'] or {},
    )
    device = update_device_record(device_serial, payload['raw_body'], request=request)

    if plain_text_rows:
        for row in plain_text_rows:
            row_device_user_id = extract_device_user_id(row, payload['query_data'])
            row_timestamp = parse_device_timestamp(
                row.get('datetime') or row.get('stamp') or row.get('time') or row.get('date')
            )
            dispatch_biometric_request(
                request,
                payload,
                row_device_user_id,
                device_serial,
                row_timestamp,
            )
        return HttpResponse('OK', content_type='text/plain')

    device_user_id = extract_device_user_id(primary_payload, payload['query_data'])
    device_timestamp = parse_device_timestamp(
        primary_payload.get('datetime')
        or primary_payload.get('stamp')
        or primary_payload.get('time')
        or primary_payload.get('date')
    )
    return dispatch_biometric_request(request, payload, device_user_id, device_serial, device_timestamp)


@csrf_exempt
@require_http_methods(['GET'])
def iclock_getrequest(request):
    query_data = {k.lower(): v for k, v in request.GET.items()}
    device_serial = extract_device_serial(query_data)
    device = update_device_record(device_serial, '', request=request)

    create_raw_event(
        device=device,
        event_type=BiometricRawEvent.EventType.COMMAND_POLL,
        request=request,
        raw_body='',
        parsed_ok=True,
        notes='Device requested pending commands.',
    )

    if not device:
        return HttpResponse('OK', content_type='text/plain')

    command = (
        BiometricDeviceCommand.objects
        .filter(device=device, status=BiometricDeviceCommand.Status.PENDING)
        .order_by('queued_at', 'id')
        .first()
    )
    if not command:
        return HttpResponse('OK', content_type='text/plain')

    command_text = build_device_command_text(command)
    command.mark_sent(response_payload=command_text)

    log_sync_event(
        action=BiometricSyncLog.Action.COMMAND,
        device=device,
        member=command.member,
        staff=command.staff,
        device_user_id=command.device_user_id,
        success=True,
        payload=command.payload,
        response=command_text,
        notes=f'Command {command.get_command_display()} sent to device.',
    )
    return HttpResponse(command_text, content_type='text/plain')


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def iclock_devicecmd(request):
    payload = normalize_request_payload(request)
    log_biometric_request(request, payload)

    primary_payload = get_primary_payload(
        payload['post_data'],
        payload['xml_fields'],
        payload['plain_text_rows'],
        payload['json_payload'],
    )
    device_serial = extract_device_serial(
        payload['query_data'],
        payload['post_data'],
        payload['xml_fields'],
        primary_payload,
        payload['json_payload'] or {},
    )
    device = update_device_record(device_serial, payload['raw_body'], request=request)

    create_raw_event(
        device=device,
        event_type=BiometricRawEvent.EventType.COMMAND_ACK,
        request=request,
        raw_body=payload['raw_body'],
        parsed_ok=True,
        notes='Device command acknowledgement received.',
    )

    raw_body = payload['raw_body'] or ''
    ack_match = None
    for token in raw_body.replace('\n', ' ').split():
        if token.isdigit():
            ack_match = token
            break

    command = None
    if ack_match:
        command = BiometricDeviceCommand.objects.filter(pk=ack_match).first()

    if command:
        if 'ok' in raw_body.lower() or 'success' in raw_body.lower():
            command.mark_success(response_payload=raw_body[:5000])
            if command.member:
                status_obj = get_member_device_status(command.member, command.device)
                status_obj.mark_sync_success()
            elif command.staff:
                status_obj = get_staff_device_status(command.staff, command.device)
                status_obj.mark_sync_success()
        else:
            command.mark_acknowledged(response_payload=raw_body[:5000])

        log_sync_event(
            action=BiometricSyncLog.Action.COMMAND,
            device=device,
            member=command.member,
            staff=command.staff,
            device_user_id=command.device_user_id,
            success=True,
            payload=command.payload,
            response=raw_body[:5000],
            notes='Command acknowledgement received from device.',
        )

    return HttpResponse('OK', content_type='text/plain')


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
class BiometricEndpointView(View):
    def post(self, request, *args, **kwargs):
        return self.handle_request(request)

    def get(self, request, *args, **kwargs):
        return self.handle_request(request)

    def handle_request(self, request):
        payload = normalize_request_payload(request)
        log_biometric_request(request, payload)

        plain_text_rows = payload['plain_text_rows']
        if plain_text_rows:
            primary_payload = plain_text_rows[0]
        else:
            primary_payload = get_primary_payload(
                payload['post_data'],
                payload['xml_fields'],
                plain_text_rows,
                payload['json_payload'],
            )

        device_serial = extract_device_serial(
            payload['query_data'],
            payload['post_data'],
            payload['xml_fields'],
            primary_payload,
            payload['json_payload'] or {},
        )

        if plain_text_rows:
            for row in plain_text_rows:
                row_device_user_id = extract_device_user_id(row, payload['query_data'])
                row_ts = parse_device_timestamp(
                    row.get('datetime') or row.get('stamp') or row.get('time') or row.get('date')
                )
                dispatch_biometric_request(request, payload, row_device_user_id, device_serial, row_ts)
            return HttpResponse('OK', content_type='text/plain')

        device_user_id = extract_device_user_id(primary_payload, payload['query_data'])
        device_timestamp = parse_device_timestamp(
            primary_payload.get('datetime')
            or primary_payload.get('stamp')
            or primary_payload.get('time')
            or primary_payload.get('date')
        )
        return dispatch_biometric_request(request, payload, device_user_id, device_serial, device_timestamp)


biometric_endpoint = BiometricEndpointView.as_view()
