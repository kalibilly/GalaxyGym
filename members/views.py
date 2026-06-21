import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from accounts.models import UserAccount
from accounts.permissions import RoleRequiredMixin
from attendance.biometric import BiometricSyncService
from attendance.models import (
    BiometricDevice,
    BiometricDeviceCommand,
    BiometricSyncLog,
    DeviceUserLink,
    MemberBiometricDeviceStatus,
)
from staffs.models import Staff

from .forms import (
    MemberDeleteRequestForm,
    MemberDeleteRequestReviewForm,
    MemberForm,
)
from .models import Member, MemberDeleteRequest


class MemberListView(LoginRequiredMixin, ListView):
    model = Member
    context_object_name = 'member_list'
    template_name = 'members/member_list.html'
    paginate_by = 12

    def get_queryset(self):
        device_status_queryset = (
            MemberBiometricDeviceStatus.objects
            .select_related('device')
            .order_by('device__device_name', 'device__serial_number')
        )

        queryset = (
            super()
            .get_queryset()
            .select_related('assigned_staff')
            .prefetch_related(
                Prefetch('device_statuses', queryset=device_status_queryset)
            )
            .order_by('member_id')
        )

        query = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        staff_id = self.request.GET.get('staff', '').strip()

        if query:
            queryset = queryset.filter(
                Q(member_id__icontains=query)
                | Q(full_name__icontains=query)
                | Q(phone_number__icontains=query)
                | Q(email__icontains=query)
                | Q(emergency_contact_name__icontains=query)
                | Q(device_user_id__icontains=query)
            )

        if status:
            queryset = queryset.filter(status=status)

        if staff_id:
            queryset = queryset.filter(assigned_staff_id=staff_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        devices = list(
            BiometricDevice.objects
            .filter(is_active=True)
            .order_by('device_name', 'serial_number')
        )

        front_device = devices[0] if len(devices) > 0 else None
        back_device = devices[1] if len(devices) > 1 else None

        context['q'] = self.request.GET.get('q', '')
        context['status'] = self.request.GET.get('status', '')
        context['staff_id'] = self.request.GET.get('staff', '')
        context['staff_members'] = Staff.objects.order_by('full_name')
        context['biometric_devices'] = devices
        context['front_device'] = front_device
        context['back_device'] = back_device

        for member in context['member_list']:
            status_map = {item.device_id: item for item in member.device_statuses.all()}
            member.device_status_map = status_map
            member.front_device_status = status_map.get(front_device.id) if front_device else None
            member.back_device_status = status_map.get(back_device.id) if back_device else None

        return context


class MemberCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Member
    form_class = MemberForm
    template_name = 'members/member_form.html'
    success_url = reverse_lazy('members:list')
    success_message = 'Member profile created successfully.'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.updated_by = self.request.user
        self.object.save()
        form.save_m2m()

        devices = BiometricDevice.objects.filter(
            device_type=BiometricDevice.DeviceType.AIFACE,
            is_active=True,
        )

        for device in devices:
            service = BiometricSyncService(device)
            service.push_enrollment(
                self.object,
                self.object.device_user_id or self.object.member_id,
            )

        messages.success(self.request, self.success_message)
        return redirect(self.success_url)


class MemberUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Member
    form_class = MemberForm
    template_name = 'members/member_form.html'
    success_url = reverse_lazy('members:list')
    success_message = 'Member profile updated successfully.'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.updated_by = self.request.user
        self.object.save()
        form.save_m2m()

        devices = BiometricDevice.objects.filter(
            device_type=BiometricDevice.DeviceType.AIFACE,
            is_active=True,
        )

        for device in devices:
            service = BiometricSyncService(device)
            service.push_enrollment(
                self.object,
                self.object.device_user_id or self.object.member_id,
            )

        messages.success(self.request, self.success_message)
        return redirect(self.success_url)


class MemberDeleteRequestCreateView(RoleRequiredMixin, SuccessMessageMixin, CreateView):
    allowed_roles = [UserAccount.ROLE_STAFF, UserAccount.ROLE_OWNER]
    model = MemberDeleteRequest
    form_class = MemberDeleteRequestForm
    template_name = 'members/member_delete_request_form.html'
    success_url = reverse_lazy('members:list')
    success_message = 'Delete request submitted successfully. Owner will review it.'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['member'] = get_object_or_404(Member, pk=self.kwargs['pk'])
        return context

    def form_valid(self, form):
        form.instance.member = get_object_or_404(Member, pk=self.kwargs['pk'])
        form.instance.requested_by = self.request.user
        messages.success(self.request, self.success_message)
        return super().form_valid(form)


class MemberDeleteRequestListView(RoleRequiredMixin, TemplateView):
    allowed_roles = [UserAccount.ROLE_OWNER, UserAccount.ROLE_STAFF]
    template_name = 'members/member_delete_request_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        requests = (
            MemberDeleteRequest.objects
            .select_related('member', 'requested_by', 'reviewed_by')
            .order_by('-requested_at')
        )
        if self.request.user.role == UserAccount.ROLE_STAFF:
            requests = requests.filter(requested_by=self.request.user)
        context['delete_requests'] = requests
        return context


class MemberDeleteRequestReviewView(RoleRequiredMixin, SuccessMessageMixin, UpdateView):
    allowed_roles = [UserAccount.ROLE_OWNER]
    model = MemberDeleteRequest
    form_class = MemberDeleteRequestReviewForm
    template_name = 'members/member_delete_request_review.html'
    success_url = reverse_lazy('members:delete_request_list')
    success_message = 'Delete request updated successfully.'

    def form_valid(self, form):
        form.instance.reviewed_by = self.request.user
        form.instance.reviewed_at = timezone.now()
        response = super().form_valid(form)

        if form.instance.status == MemberDeleteRequest.STATUS_APPROVED:
            member = form.instance.member
            member.status = Member.STATUS_INACTIVE
            member.save(update_fields=['status'])

        messages.success(self.request, self.success_message)
        return response


class MemberDetailView(LoginRequiredMixin, DetailView):
    model = Member
    template_name = 'members/member_detail.html'
    context_object_name = 'member'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.object

        device_statuses = list(
            member.device_statuses
            .select_related('device')
            .order_by('device__device_name', 'device__serial_number')
        )
        devices = list(
            BiometricDevice.objects
            .filter(is_active=True)
            .order_by('device_name', 'serial_number')
        )

        front_device = devices[0] if len(devices) > 0 else None
        back_device = devices[1] if len(devices) > 1 else None
        status_map = {item.device_id: item for item in device_statuses}

        context['active_membership'] = member.active_membership
        context['recent_memberships'] = member.memberships.order_by('-start_date')[:5]
        context['latest_invoice'] = member.invoices.order_by('-invoice_date').first()
        context['open_invoices'] = member.invoices.filter(
            status__in=[
                member.invoices.model.STATUS_UNPAID,
                member.invoices.model.STATUS_PARTIAL,
            ]
        ).order_by('due_date')[:5]
        context['recent_payments'] = member.payments.order_by('-payment_date')[:5]
        context['attendance_history'] = (
            member.attendance_logs
            .select_related('device')
            .order_by('-check_in_time')[:5]
        )
        context['outstanding_balance'] = (
            member.invoices.filter(
                status__in=[
                    member.invoices.model.STATUS_UNPAID,
                    member.invoices.model.STATUS_PARTIAL,
                ]
            ).aggregate(total=Sum('balance_amount'))['total'] or 0
        )
        context['delete_request'] = member.delete_requests.order_by('-requested_at').first()
        context['device_statuses'] = device_statuses
        context['biometric_devices'] = devices
        context['front_device'] = front_device
        context['back_device'] = back_device
        context['device_status_map'] = status_map
        context['front_device_status'] = status_map.get(front_device.id) if front_device else None
        context['back_device_status'] = status_map.get(back_device.id) if back_device else None
        context['recent_sync_logs'] = (
            BiometricSyncLog.objects
            .filter(member=member)
            .select_related('device')
            .order_by('-created_at')[:10]
        )
        context['recent_device_commands'] = (
            BiometricDeviceCommand.objects
            .filter(member=member)
            .select_related('device')
            .order_by('-created_at')[:10]
        )
        context['device_user_links'] = (
            DeviceUserLink.objects
            .filter(member=member)
            .order_by('device_user_id')
        )
        return context


class MemberBiometricSyncBaseView(RoleRequiredMixin, View):
    allowed_roles = [UserAccount.ROLE_OWNER, UserAccount.ROLE_STAFF]

    def get_member(self):
        return get_object_or_404(Member, pk=self.kwargs['pk'])

    def get_device(self, device_pk):
        return get_object_or_404(BiometricDevice, pk=device_pk, is_active=True)

    def get_target_device_user_id(self, member):
        return (member.device_user_id or member.member_id or '').strip()

    def get_or_create_status(self, member, device):
        device_user_id = self.get_target_device_user_id(member)
        status_obj, created = MemberBiometricDeviceStatus.objects.get_or_create(
            member=member,
            device=device,
            defaults={
                'device_user_id': device_user_id,
                'sync_status': MemberBiometricDeviceStatus.SyncStatus.PENDING,
            },
        )

        updates = []
        if device_user_id and status_obj.device_user_id != device_user_id:
            status_obj.device_user_id = device_user_id
            updates.append('device_user_id')

        if updates:
            status_obj.save(update_fields=updates)

        return status_obj

    def log_command(self, device, member, command, payload=''):
        return BiometricDeviceCommand.objects.create(
            device=device,
            member=member,
            command=command,
            payload=payload or '',
            status=BiometricDeviceCommand.Status.PENDING,
        )

    def update_device_link(self, member, device_user_id):
        if not device_user_id:
            return None

        link, created = DeviceUserLink.objects.get_or_create(
            device_user_id=device_user_id,
            defaults={
                'member': member,
                'staff': None,
                'is_active': True,
            },
        )

        changed = False
        if link.member_id != member.id:
            link.member = member
            link.staff = None
            changed = True
        if not link.is_active:
            link.is_active = True
            changed = True

        if changed:
            link.save(update_fields=['member', 'staff', 'is_active'])

        return link

    def perform_sync(self, member, device):
        status_obj = self.get_or_create_status(member, device)
        device_user_id = self.get_target_device_user_id(member)

        if not device_user_id:
            status_obj.sync_status = MemberBiometricDeviceStatus.SyncStatus.FAILED
            status_obj.last_error = 'Member has no device_user_id or member_id for biometric sync.'
            status_obj.last_status_checked_at = timezone.now()
            status_obj.notes = 'Sync failed before dispatch because no device user identifier was available.'
            status_obj.save(
                update_fields=[
                    'sync_status',
                    'last_error',
                    'last_status_checked_at',
                    'notes',
                ]
            )
            return False, status_obj, None

        payload = json.dumps(
            {
                'member_id': member.member_id,
                'device_user_id': device_user_id,
                'full_name': member.full_name,
            },
            default=str,
        )

        command = self.log_command(
            device=device,
            member=member,
            command=BiometricDeviceCommand.CommandType.SYNC_USER,
            payload=payload,
        )

        service = BiometricSyncService(device)
        result = service.push_enrollment(member, device_user_id)

        command.status = (
            BiometricDeviceCommand.Status.SUCCESS
            if result.get('ok')
            else BiometricDeviceCommand.Status.FAILED
        )
        command.response_payload = json.dumps(result, default=str)
        command.processed_at = timezone.now()
        command.error_message = '' if result.get('ok') else result.get('message', 'Enrollment failed.')
        command.save(update_fields=['status', 'response_payload', 'processed_at', 'error_message'])

        status_obj.refresh_from_db()

        if result.get('ok'):
            status_obj.notes = 'Member synced successfully to biometric device.'
            self.update_device_link(member, device_user_id)
        else:
            status_obj.notes = 'Biometric sync attempt failed.'

        status_obj.save(update_fields=['notes'])

        BiometricSyncLog.objects.create(
            device=device,
            member=member,
            person_type='member',
            action=BiometricSyncLog.Action.COMMAND,
            device_user_id=device_user_id,
            success=bool(result.get('ok')),
            payload=payload,
            response=json.dumps(result, default=str),
            notes=status_obj.notes,
        )

        return bool(result.get('ok')), status_obj, result

    def perform_status_check(self, member, device):
        status_obj = self.get_or_create_status(member, device)
        service = BiometricSyncService(device)
        result = service.probe()

        status_obj.last_status_checked_at = timezone.now()
        status_obj.last_error = '' if result.get('ok') else result.get('message', '')
        status_obj.notes = (
            'Device responded successfully.'
            if result.get('ok')
            else 'Device status check failed.'
        )
        status_obj.save(update_fields=['last_status_checked_at', 'last_error', 'notes'])

        BiometricSyncLog.objects.create(
            device=device,
            member=member,
            person_type='member',
            action=BiometricSyncLog.Action.DEVICE_HEARTBEAT,
            device_user_id=status_obj.device_user_id or '',
            success=bool(result.get('ok')),
            payload=json.dumps({'member_id': member.member_id}, default=str),
            response=json.dumps(result, default=str),
            notes=status_obj.notes,
        )

        return bool(result.get('ok')), status_obj, result

    def get_redirect_url(self, member):
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse('members:detail', kwargs={'pk': member.pk})


class MemberSendToDeviceView(MemberBiometricSyncBaseView):
    def post(self, request, *args, **kwargs):
        member = self.get_member()
        device = self.get_device(kwargs['device_pk'])

        ok, status_obj, result = self.perform_sync(member, device)

        if ok:
            messages.success(
                request,
                f'{member.full_name} was synced to {device.device_name or device.serial_number}.',
            )
        else:
            messages.error(
                request,
                f'Failed to sync {member.full_name} to {device.device_name or device.serial_number}: {status_obj.last_error}',
            )

        return redirect(self.get_redirect_url(member))


class MemberSendToBothDevicesView(MemberBiometricSyncBaseView):
    def post(self, request, *args, **kwargs):
        member = self.get_member()
        devices = list(
            BiometricDevice.objects
            .filter(is_active=True)
            .order_by('device_name', 'serial_number')[:2]
        )

        if not devices:
            messages.error(request, 'No active biometric devices found.')
            return redirect(self.get_redirect_url(member))

        success_count = 0
        failure_count = 0

        for device in devices:
            ok, status_obj, result = self.perform_sync(member, device)
            if ok:
                success_count += 1
            else:
                failure_count += 1

        if success_count and not failure_count:
            messages.success(request, f'{member.full_name} was synced to all available biometric devices.')
        elif success_count and failure_count:
            messages.warning(
                request,
                f'{member.full_name} synced to {success_count} device(s), but failed on {failure_count} device(s).',
            )
        else:
            messages.error(request, f'Failed to sync {member.full_name} to available biometric devices.')

        return redirect(self.get_redirect_url(member))


class MemberCheckDeviceStatusView(MemberBiometricSyncBaseView):
    def post(self, request, *args, **kwargs):
        member = self.get_member()
        device = self.get_device(kwargs['device_pk'])

        ok, status_obj, result = self.perform_status_check(member, device)

        if ok:
            messages.success(
                request,
                f'Device {device.device_name or device.serial_number} responded successfully.',
            )
        else:
            messages.error(
                request,
                f'Status check failed for {device.device_name or device.serial_number}: {status_obj.last_error or "Unknown device error."}',
            )

        return redirect(self.get_redirect_url(member))
