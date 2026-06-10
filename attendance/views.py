import json
import logging
import re
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
from .forms import AttendanceLogForm
from .models import AttendanceLog, BiometricDevice
from .biometric import BiometricSyncService
from .services import AccessDecisionError, create_attendance_attempt, evaluate_member_access, evaluate_staff_access

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
        queryset = super().get_queryset().select_related('member', 'staff').order_by('-date', '-check_in_time')
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
        raise PermissionDenied('You do not have permission to view another member\'s attendance history.')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.object
        context['attendance_list'] = member.attendance_logs.order_by('-check_in_time')[:20]
        return context

def extract_headers(request):
    headers = {}
    for key, value in request.META.items():
        if key.startswith('HTTP_') or key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
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
            # ATTLOG format: first column is the device user ID; preserve raw data for debugging
            parsed_line['id'] = tokens[0] if tokens else None
            parsed_line['_split_cols'] = tokens
            parsed_line['_raw'] = stripped_line
            logger.debug('parse_plain_text_rows ATTLOG row=%s split=%s parsed=%s', stripped_line, tokens, parsed_line)

        if parsed_line:
            rows.append(parsed_line)
    logger.debug('parse_plain_text_rows parsed %d rows: %s', len(rows), rows)
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
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def render_device_response(request, status_text='OK'):
    raw_body = request.body.decode('utf-8', errors='ignore')
    if 'xml' in (request.content_type or '') or raw_body.strip().startswith('<'):
        return HttpResponse(f'<Response>{status_text}</Response>', content_type='application/xml')
    return HttpResponse(status_text, content_type='text/plain')


def get_device_target(device_user_id):
    if not device_user_id:
        logger.debug('get_device_target called with empty device_user_id')
        return None

    # Try device_user_id mapping first
    target = Member.objects.filter(device_user_id=device_user_id).select_related('user').first()
    if target:
        logger.debug('Found Member by device_user_id=%s -> member_id=%s', device_user_id, target.member_id)
        return target

    target = Staff.objects.filter(device_user_id=device_user_id).select_related('user').first()
    if target:
        logger.debug('Found Staff by device_user_id=%s -> staff_id=%s', device_user_id, target.staff_id)
        return target

    # Try member_id/staff_id fallback
    target = Member.objects.filter(member_id=device_user_id).select_related('user').first()
    if target:
        logger.debug('Found Member by member_id=%s', device_user_id)
        return target

    target = Staff.objects.filter(staff_id=device_user_id).select_related('user').first()
    if target:
        logger.debug('Found Staff by staff_id=%s', device_user_id)
        return target

    logger.debug('No Member/Staff matched for device_user_id=%s', device_user_id)
    return None


def deny_expired_member(target):
    if isinstance(target, Member):
        target.status = Member.STATUS_INACTIVE
        target.save(update_fields=['status'])
        if target.user:
            target.user.is_active = False
            target.user.save(update_fields=['is_active'])


def update_device_record(device_serial, raw_body, request=None):
    if not device_serial:
        return None
    device, created = BiometricDevice.objects.get_or_create(
        serial_number=device_serial,
        defaults={'device_name': device_serial},
    )
    remote_ip = None
    if request is not None:
        remote_ip = request.META.get('REMOTE_ADDR')
    device.touch_heartbeat(raw_body, remote_ip=remote_ip)
    return device


@require_http_methods(['GET', 'POST'])
@csrf_exempt
@require_http_methods(['GET', 'POST'])
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
    return JsonResponse({
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
    })


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

    device, created = BiometricDevice.objects.get_or_create(
        serial_number=serial_number,
        defaults={'device_name': serial_number},
    )
    device.touch_heartbeat(json.dumps(payload, default=str), remote_ip=request.META.get('REMOTE_ADDR'))

    target = None
    if member_id:
        target = Member.objects.filter(member_id=member_id).select_related('user').first()
        if not target:
            return JsonResponse({'ok': False, 'error': 'Unknown member_id.'}, status=404)
    elif staff_id:
        target = Staff.objects.filter(staff_id=staff_id).select_related('user').first()
        if not target:
            return JsonResponse({'ok': False, 'error': 'Unknown staff_id.'}, status=404)

    sync_service = BiometricSyncService(device)
    sync_result = sync_service.push_enrollment(target, device_user_id)
    return JsonResponse({
        'ok': sync_result.get('ok', False),
        'result': sync_result,
        'device_serial': device.serial_number,
        'device_user_id': device_user_id,
        'member_id': getattr(target, 'member_id', None),
        'staff_id': getattr(target, 'staff_id', None),
    }, status=200 if sync_result.get('ok', False) else 409)


def log_biometric_request(request, payload):
    logger.info(
        'Biometric request received: %s',
        json.dumps(payload, default=str),
    )


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


def dispatch_biometric_request(request, payload, device_user_id, device_serial, device_timestamp):
    logger.debug('Dispatch biometric request: device_user_id=%s device_serial=%s device_timestamp=%s', device_user_id, device_serial, device_timestamp)
    target = get_device_target(device_user_id)
    if not target:
        logger.warning('Biometric request could not match any Member or Staff for device_user_id=%s', device_user_id)
        return render_device_response(request, status_text='ERR_USER_NOT_FOUND')

    if isinstance(target, Member):
        decision = evaluate_member_access(target)
        if not decision['gym_access']:
            deny_expired_member(target)
            attendance, duplicate = create_attendance_attempt(
                'member',
                target,
                source=AttendanceLog.SOURCE_DEVICE,
                verification_mode=AttendanceLog.VERIFICATION_BIOMETRIC,
                device_id=device_serial or request.path,
                device_user_id=device_user_id,
                remarks=f'Access denied by software rules for device_user_id={device_user_id}: {decision.get("reason")}',
                status=AttendanceLog.STATUS_ABSENT,
                check_in_time=device_timestamp,
            )
            logger.info('Denied biometric access for device_user_id=%s: %s', device_user_id, decision.get('reason'))
            return render_device_response(request, status_text='DENY')

        attendance, duplicate = create_attendance_attempt(
            'member',
            target,
            source=AttendanceLog.SOURCE_DEVICE,
            verification_mode=AttendanceLog.VERIFICATION_BIOMETRIC,
            device_id=device_serial or request.path,
            device_user_id=device_user_id,
            remarks=f'Biometric attendance from device_user_id={device_user_id}',
            status=AttendanceLog.STATUS_PRESENT,
            check_in_time=device_timestamp,
        )
        if attendance:
            logger.info('Created biometric attendance record %s for device_user_id=%s', attendance.pk, device_user_id)
        else:
            logger.info('Skipped duplicate biometric attendance for device_user_id=%s', device_user_id)
        return render_device_response(request, status_text='OK')

    if isinstance(target, Staff):
        decision = evaluate_staff_access(target)
        if not decision['is_staff_active']:
            attendance, duplicate = create_attendance_attempt(
                'staff',
                target,
                source=AttendanceLog.SOURCE_DEVICE,
                verification_mode=AttendanceLog.VERIFICATION_BIOMETRIC,
                device_id=device_serial or request.path,
                device_user_id=device_user_id,
                remarks=f'Access denied by software rules for device_user_id={device_user_id}: {decision.get("reason")}',
                status=AttendanceLog.STATUS_ABSENT,
                check_in_time=device_timestamp,
            )
            logger.info('Denied biometric staff access for device_user_id=%s: %s', device_user_id, decision.get('reason'))
            return render_device_response(request, status_text='DENY')

        attendance, duplicate = create_attendance_attempt(
            'staff',
            target,
            source=AttendanceLog.SOURCE_DEVICE,
            verification_mode=AttendanceLog.VERIFICATION_BIOMETRIC,
            device_id=device_serial or request.path,
            device_user_id=device_user_id,
            remarks=f'Biometric attendance from device_user_id={device_user_id}',
            status=AttendanceLog.STATUS_PRESENT,
            check_in_time=device_timestamp,
        )
        if attendance:
            logger.info('Created biometric attendance record %s for device_user_id=%s', attendance.pk, device_user_id)
        else:
            logger.info('Skipped duplicate biometric attendance for device_user_id=%s', device_user_id)
        return render_device_response(request, status_text='OK')

    logger.info('Denied biometric access for device_user_id=%s due to unknown target type', device_user_id)
    return render_device_response(request, status_text='DENY')


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def biometric_get_request(request):
    raw_body = request.body.decode('utf-8', errors='ignore')
    headers = extract_headers(request)
    query_data = {k.lower(): v for k, v in request.GET.items()}
    post_data = {k.lower(): v for k, v in request.POST.items()}
    xml_fields = parse_xml(raw_body)
    json_payload = None
    plain_text_rows = parse_plain_text_rows(raw_body)
    if 'json' in (request.content_type or '') and raw_body:
        try:
            json_payload = json.loads(raw_body)
        except json.JSONDecodeError:
            json_payload = None

    payload = {
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
    log_biometric_request(request, payload)

    device_serial = extract_device_serial(query_data, post_data, xml_fields, plain_text_rows[0] if plain_text_rows else {}, json_payload or {})
    update_device_record(device_serial, raw_body, request=request)
    return HttpResponse('OK', content_type='text/plain')


@require_http_methods(['GET', 'POST'])
def bridge_entry(request):
    try:
        payload = json.loads(request.body or '{}') if request.content_type and 'json' in request.content_type else request.POST.dict()
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON payload.'}, status=400)

    member_id = payload.get('member_id') or payload.get('user_id')
    staff_id = payload.get('staff_id')
    member_name = payload.get('member_name') or payload.get('name')
    staff_name = payload.get('staff_name')
    entry_time = payload.get('entry_time') or payload.get('check_in_time')

    if member_id:
        member = Member.objects.filter(member_id=member_id).select_related('user').first()
        if not member:
            return JsonResponse({'ok': False, 'error': 'Unknown member_id.'}, status=404)

        decision = evaluate_member_access(member)
        attendance, duplicate = create_attendance_attempt(
            'member',
            member,
            source=AttendanceLog.SOURCE_DEVICE,
            verification_mode=AttendanceLog.VERIFICATION_DEVICE,
            device_id=payload.get('device_id', 'bridge'),
            device_user_id=member_id,
            remarks='Bridge attendance attempt' if decision['gym_access'] else 'Bridge access denied by software rules',
            status=AttendanceLog.STATUS_PRESENT if decision['gym_access'] else AttendanceLog.STATUS_ABSENT,
        )
        return JsonResponse({
            'ok': True,
            'user_type': 'member',
            'member_id': member.member_id,
            'member_name': member.full_name,
            'entry_time': entry_time,
            'gym_access': decision['gym_access'],
            'attendance_created': attendance is not None,
            'duplicate_daily_attendance': duplicate,
            'reason': decision.get('reason'),
        })

    if staff_id:
        staff = Staff.objects.filter(staff_id=staff_id).select_related('user').first()
        if not staff:
            return JsonResponse({'ok': False, 'error': 'Unknown staff_id.'}, status=404)

        decision = evaluate_staff_access(staff)
        attendance, duplicate = create_attendance_attempt(
            'staff',
            staff,
            source=AttendanceLog.SOURCE_DEVICE,
            verification_mode=AttendanceLog.VERIFICATION_DEVICE,
            device_id=payload.get('device_id', 'bridge'),
            device_user_id=staff_id,
            remarks='Bridge attendance attempt' if decision['is_staff_active'] else 'Bridge staff access denied by software rules',
            status=AttendanceLog.STATUS_PRESENT if decision['is_staff_active'] else AttendanceLog.STATUS_ABSENT,
        )
        return JsonResponse({
            'ok': True,
            'user_type': 'staff',
            'staff_id': staff.staff_id,
            'staff_name': staff.full_name,
            'entry_time': entry_time,
            'is_staff_active': decision['is_staff_active'],
            'attendance_created': attendance is not None,
            'duplicate_daily_attendance': duplicate,
            'reason': decision.get('reason'),
        })

    return JsonResponse({'ok': False, 'error': 'Provide member_id or staff_id.'}, status=400)


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
        return JsonResponse({
            'ok': True,
            'user_type': 'member',
            'member_id': member.member_id,
            'member_name': member.full_name,
            'gym_access': decision['gym_access'],
            'reason': decision.get('reason'),
        })

    if staff_id:
        staff = Staff.objects.filter(staff_id=staff_id).select_related('user').first()
        if not staff:
            return JsonResponse({'ok': False, 'error': 'Unknown staff_id.'}, status=404)
        decision = evaluate_staff_access(staff)
        return JsonResponse({
            'ok': True,
            'user_type': 'staff',
            'staff_id': staff.staff_id,
            'staff_name': staff.full_name,
            'is_staff_active': decision['is_staff_active'],
            'reason': decision.get('reason'),
        })

    return JsonResponse({'ok': False, 'error': 'Provide member_id or staff_id.'}, status=400)
@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(require_http_methods(['GET', 'POST']), name='dispatch')
class BiometricEndpointView(View):
    def post(self, request, *args, **kwargs):
        return self.handle_request(request)

    def get(self, request, *args, **kwargs):
        return self.handle_request(request)

    def handle_request(self, request):
        raw_body = request.body.decode('utf-8', errors='ignore')
        headers = extract_headers(request)
        post_data = {k.lower(): v for k, v in request.POST.items()}
        query_data = {k.lower(): v for k, v in request.GET.items()}
        xml_fields = parse_xml(raw_body)
        json_payload = None
        if 'json' in (request.content_type or '') and raw_body:
            try:
                json_payload = json.loads(raw_body)
            except json.JSONDecodeError:
                json_payload = None

        plain_text_rows = parse_plain_text_rows(raw_body)
        payload = {
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
        log_biometric_request(request, payload)

        # If the device sent multiple USER lines (common with ADMS/ZKTeco),
        # parse_plain_text_rows returns multiple dicts. Process each row
        # individually so every PIN entry is evaluated and recorded.
        if plain_text_rows:
            results = []
            for idx, row in enumerate(plain_text_rows):
                row_device_user_id = extract_device_user_id(row, query_data)
                row_device_serial = extract_device_serial(query_data, post_data, xml_fields, row, json_payload or {})
                row_ts = parse_device_timestamp(
                    row.get('datetime') or row.get('stamp') or row.get('time') or row.get('date')
                )
                logger.debug(
                    'Processing biometric row %d raw=%s split=%s parsed_user=%s',
                    idx,
                    row.get('_raw') or row,
                    row.get('_split_cols'),
                    row_device_user_id,
                )
                # update device record once (keep last payload/time)
                update_device_record(row_device_serial, raw_body, request=request)
                resp = dispatch_biometric_request(request, payload, row_device_user_id, row_device_serial, row_ts)
                results.append({'row': idx, 'user': row_device_user_id, 'status': getattr(resp, 'status_code', 'OK')})

            logger.info('Processed %d biometric rows, users=%s', len(plain_text_rows), [r['user'] for r in results])
            # Devices expect a single short response; return OK to acknowledge receipt
            return HttpResponse('OK', content_type='text/plain')

        # fallback for non-plain payloads (JSON, XML, POST fields)
        primary_payload = get_primary_payload(post_data, xml_fields, plain_text_rows, json_payload)
        device_user_id = extract_device_user_id(primary_payload, query_data)
        device_serial = extract_device_serial(query_data, post_data, xml_fields, primary_payload, json_payload or {})
        device_timestamp = parse_device_timestamp(
            primary_payload.get('datetime')
            or primary_payload.get('stamp')
            or primary_payload.get('time')
            or primary_payload.get('date')
        )
        update_device_record(device_serial, raw_body, request=request)

        return dispatch_biometric_request(request, payload, device_user_id, device_serial, device_timestamp)


biometric_endpoint = BiometricEndpointView.as_view()

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
        raise PermissionDenied('You do not have permission to view another staff member\'s attendance history.')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff = self.object
        context['attendance_list'] = staff.attendance_logs.order_by('-check_in_time')[:20]
        return context
