from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q, Sum, Prefetch
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView


from accounts.models import UserAccount
from accounts.permissions import RoleRequiredMixin
from attendance.models import (
    AttendanceLog,
    BiometricDevice,
    MemberBiometricDeviceStatus,
)
from staffs.models import Staff
from .forms import (
    MemberForm,
    MemberDeleteRequestForm,
    MemberDeleteRequestReviewForm,
)
from .models import Member, MemberDeleteRequest



class MemberListView(LoginRequiredMixin, ListView):
    model = Member
    context_object_name = 'member_list'
    template_name = 'members/member_list.html'
    paginate_by = 12


    def get_queryset(self):
        device_status_queryset = MemberBiometricDeviceStatus.objects.select_related('device').order_by('device__device_name', 'device__serial_number')
        queryset = (
            super()
            .get_queryset()
            .select_related('assigned_staff')
            .prefetch_related(
                Prefetch('device_statuses', queryset=device_status_queryset)
            )
            .order_by('member_id')
        )
        query = self.request.GET.get('q')
        status = self.request.GET.get('status')
        staff_id = self.request.GET.get('staff')


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
        devices = BiometricDevice.objects.filter(is_active=True).order_by('device_name', 'serial_number')
        context['q'] = self.request.GET.get('q', '')
        context['status'] = self.request.GET.get('status', '')
        context['staff_id'] = self.request.GET.get('staff', '')
        context['staff_members'] = Staff.objects.order_by('full_name')
        context['biometric_devices'] = devices
        context['front_device'] = devices.first()
        context['back_device'] = devices[1] if devices.count() > 1 else None

        for member in context['member_list']:
            status_map = {item.device_id: item for item in member.device_statuses.all()}
            member.device_status_map = status_map
            member.front_device_status = status_map.get(context['front_device'].id) if context['front_device'] else None
            member.back_device_status = status_map.get(context['back_device'].id) if context['back_device'] else None
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
        return super().form_valid(form)



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
        return super().form_valid(form)



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
        return super().form_valid(form)



class MemberDeleteRequestListView(RoleRequiredMixin, TemplateView):
    allowed_roles = [UserAccount.ROLE_OWNER, UserAccount.ROLE_STAFF]
    template_name = 'members/member_delete_request_list.html'


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        requests = MemberDeleteRequest.objects.select_related('member', 'requested_by', 'reviewed_by').order_by('-requested_at')
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
        return response



class MemberDetailView(LoginRequiredMixin, DetailView):
    model = Member
    template_name = 'members/member_detail.html'
    context_object_name = 'member'


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.object
        device_statuses = member.device_statuses.select_related('device').order_by('device__device_name', 'device__serial_number')
        devices = BiometricDevice.objects.filter(is_active=True).order_by('device_name', 'serial_number')

        context['active_membership'] = member.active_membership
        context['recent_memberships'] = member.memberships.order_by('-start_date')[:5]
        context['latest_invoice'] = member.invoices.order_by('-invoice_date').first()
        context['open_invoices'] = member.invoices.filter(
            status__in=[member.invoices.model.STATUS_UNPAID, member.invoices.model.STATUS_PARTIAL]
        ).order_by('due_date')[:5]
        context['recent_payments'] = member.payments.order_by('-payment_date')[:5]
        context['attendance_history'] = member.attendance_logs.order_by('-check_in_time')[:5]
        context['outstanding_balance'] = member.invoices.filter(
            status__in=[member.invoices.model.STATUS_UNPAID, member.invoices.model.STATUS_PARTIAL]
        ).aggregate(total=Sum('balance_amount'))['total'] or 0
        context['delete_request'] = member.delete_requests.order_by('-requested_at').first()
        context['device_statuses'] = device_statuses
        context['biometric_devices'] = devices
        context['front_device'] = devices.first()
        context['back_device'] = devices[1] if devices.count() > 1 else None

        status_map = {item.device_id: item for item in device_statuses}
        context['device_status_map'] = status_map
        context['front_device_status'] = status_map.get(context['front_device'].id) if context['front_device'] else None
        context['back_device_status'] = status_map.get(context['back_device'].id) if context['back_device'] else None
        return context



class MemberBiometricSyncBaseView(RoleRequiredMixin, View):
    allowed_roles = [UserAccount.ROLE_OWNER, UserAccount.ROLE_STAFF]


    def get_member(self):
        return get_object_or_404(Member, pk=self.kwargs['pk'])


    def get_device(self, device_pk):
        return get_object_or_404(BiometricDevice, pk=device_pk, is_active=True)


    def get_or_create_status(self, member, device):
        status_obj, created = MemberBiometricDeviceStatus.objects.get_or_create(
            member=member,
            device=device,
            defaults={
                'device_user_id': member.device_user_id or member.member_id,
                'sync_status': MemberBiometricDeviceStatus.SYNC_PENDING,
            }
        )
        if status_obj.device_user_id != (member.device_user_id or member.member_id):
            status_obj.device_user_id = member.device_user_id or member.member_id
            status_obj.save(update_fields=['device_user_id'])
        return status_obj


    def get_redirect_url(self, member):
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse_lazy('members:detail', kwargs={'pk': member.pk})



class MemberSendToDeviceView(MemberBiometricSyncBaseView):
    def post(self, request, *args, **kwargs):
        member = self.get_member()
        device = self.get_device(kwargs['device_pk'])

        status_obj = self.get_or_create_status(member, device)
        status_obj.sync_status = MemberBiometricDeviceStatus.SYNC_SENT
        status_obj.device_user_id = member.device_user_id or member.member_id
        status_obj.is_enabled_on_device = True
        status_obj.last_status_checked_at = timezone.now()
        status_obj.last_error = ''
        status_obj.notes = 'Placeholder sync action completed. Real device integration pending.'
        status_obj.save(
            update_fields=[
                'sync_status',
                'device_user_id',
                'is_enabled_on_device',
                'last_status_checked_at',
                'last_error',
                'notes',
            ]
        )

        messages.success(
            request,
            f'{member.full_name} was marked as sent to {device.device_name or device.serial_number}.',
        )
        return redirect(self.get_redirect_url(member))



class MemberSendToBothDevicesView(MemberBiometricSyncBaseView):
    def post(self, request, *args, **kwargs):
        member = self.get_member()
        devices = BiometricDevice.objects.filter(is_active=True).order_by('device_name', 'serial_number')[:2]

        if not devices:
            messages.error(request, 'No active biometric devices found.')
            return redirect(self.get_redirect_url(member))

        for device in devices:
            status_obj = self.get_or_create_status(member, device)
            status_obj.sync_status = MemberBiometricDeviceStatus.SYNC_SENT
            status_obj.device_user_id = member.device_user_id or member.member_id
            status_obj.is_enabled_on_device = True
            status_obj.last_status_checked_at = timezone.now()
            status_obj.last_error = ''
            status_obj.notes = 'Placeholder bulk sync action completed. Real device integration pending.'
            status_obj.save(
                update_fields=[
                    'sync_status',
                    'device_user_id',
                    'is_enabled_on_device',
                    'last_status_checked_at',
                    'last_error',
                    'notes',
                ]
            )

        messages.success(request, f'{member.full_name} was marked as sent to available biometric devices.')
        return redirect(self.get_redirect_url(member))



class MemberCheckDeviceStatusView(MemberBiometricSyncBaseView):
    def post(self, request, *args, **kwargs):
        member = self.get_member()
        device = self.get_device(kwargs['device_pk'])

        status_obj = self.get_or_create_status(member, device)
        status_obj.last_status_checked_at = timezone.now()
        if not status_obj.device_user_id:
            status_obj.device_user_id = member.device_user_id or member.member_id

        if status_obj.sync_status == MemberBiometricDeviceStatus.SYNC_PENDING:
            status_obj.notes = 'Status checked. Member has not been sent to this device yet.'
        elif status_obj.sync_status == MemberBiometricDeviceStatus.SYNC_SENT:
            status_obj.notes = 'Status checked. Awaiting real confirmation from device integration layer.'
        elif status_obj.sync_status == MemberBiometricDeviceStatus.SYNC_SUCCESS:
            status_obj.notes = 'Status checked. Member is successfully available on this device.'
        else:
            status_obj.notes = 'Status checked. Last sync attempt failed.'

        status_obj.save(
            update_fields=[
                'device_user_id',
                'last_status_checked_at',
                'notes',
            ]
        )

        messages.info(
            request,
            f'Status check completed for {member.full_name} on {device.device_name or device.serial_number}.',
        )
        return redirect(self.get_redirect_url(member))
