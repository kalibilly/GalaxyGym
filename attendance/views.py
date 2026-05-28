import json
import logging
import xml.etree.ElementTree as ET

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from accounts.models import UserAccount
from members.models import Member
from staffs.models import Staff
from .forms import AttendanceLogForm
from .models import AttendanceLog

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


def extract_device_user_id(post_data, xml_fields, query_data):
    candidate_fields = [
        'pin',
        'uid',
        'userid',
        'user_id',
        'code',
        'sn',
        'id',
    ]
    for field in candidate_fields:
        for source in (post_data, xml_fields, query_data):
            if source.get(field):
                return str(source.get(field)).strip()
    return None


def render_device_response(request, status_text='OK'):
    raw_body = request.body.decode('utf-8', errors='ignore')
    if 'xml' in (request.content_type or '') or raw_body.strip().startswith('<'):
        return HttpResponse(f'<Response>{status_text}</Response>', content_type='application/xml')
    return HttpResponse(status_text, content_type='text/plain')


def get_device_target(device_user_id):
    if not device_user_id:
        return None
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


def deny_expired_member(target):
    if isinstance(target, Member):
        target.status = Member.STATUS_INACTIVE
        target.save(update_fields=['status'])
        if target.user:
            target.user.is_active = False
            target.user.save(update_fields=['is_active'])


def log_biometric_request(request, payload):
    logger.info(
        'Biometric request received: %s',
        json.dumps(payload, default=str),
    )


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
        post_data = request.POST.dict()
        query_data = request.GET.dict()
        xml_fields = parse_xml(raw_body)
        json_payload = None
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
            'xml_fields': xml_fields,
            'json_payload': json_payload,
        }
        log_biometric_request(request, payload)

        device_user_id = extract_device_user_id(post_data, xml_fields, query_data)
        target = get_device_target(device_user_id)
        if not target:
            logger.warning('Biometric request could not match any Member or Staff for device_user_id=%s', device_user_id)
            return render_device_response(request, status_text='ERR_USER_NOT_FOUND')

        active_membership = None
        allow_access = True
        if isinstance(target, Member):
            active_membership = target.active_membership
            allow_access = bool(active_membership and active_membership.status == active_membership.STATUS_ACTIVE)
            if not allow_access:
                deny_expired_member(target)

        if allow_access:
            attendance = AttendanceLog.objects.create(
                member=target if isinstance(target, Member) else None,
                staff=target if isinstance(target, Staff) else None,
                source=AttendanceLog.SOURCE_DEVICE,
                verification_mode=AttendanceLog.VERIFICATION_BIOMETRIC,
                device_id=request.path,
                status=AttendanceLog.STATUS_PRESENT,
                remarks=f'Biometric attendance from device_user_id={device_user_id}',
            )
            logger.info('Created biometric attendance record %s for device_user_id=%s', attendance.pk, device_user_id)
            return render_device_response(request, status_text='OK')

        logger.info('Denied biometric access for device_user_id=%s due to expired membership', device_user_id)
        return render_device_response(request, status_text='DENY')


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
