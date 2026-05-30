from datetime import date

from django.db.models import Q
from django.utils import timezone

from .models import AttendanceLog


class AccessDecisionError(Exception):
    """Raised when an access decision cannot be made for a device event."""


def _latest_membership(member):
    return member.memberships.order_by('-end_date').first() if member else None


def evaluate_member_access(member):
    if not member:
        raise AccessDecisionError('Member not found.')

    if not member.is_active or (member.user and not member.user.is_active):
        return {
            'ok': False,
            'user_type': 'member',
            'member_id': member.member_id,
            'member_name': member.full_name,
            'gym_access': False,
            'reason': 'Member profile is inactive.',
        }

    membership = _latest_membership(member)
    if not membership:
        return {
            'ok': False,
            'user_type': 'member',
            'member_id': member.member_id,
            'member_name': member.full_name,
            'gym_access': False,
            'reason': 'No active membership found in software.',
        }

    today = date.today()
    if membership.end_date < today:
        days_expired = (today - membership.end_date).days
        if days_expired > 3:
            return {
                'ok': False,
                'user_type': 'member',
                'member_id': member.member_id,
                'member_name': member.full_name,
                'gym_access': False,
                'reason': 'Membership expired more than 3 days ago.',
            }

    if membership.status not in {membership.STATUS_ACTIVE, membership.STATUS_EXPIRING_SOON} and membership.end_date >= today:
        return {
            'ok': False,
            'user_type': 'member',
            'member_id': member.member_id,
            'member_name': member.full_name,
            'gym_access': False,
            'reason': 'Membership is not currently active for access.',
        }

    if member.pending_amount and member.pending_amount > 0:
        return {
            'ok': False,
            'user_type': 'member',
            'member_id': member.member_id,
            'member_name': member.full_name,
            'gym_access': False,
            'reason': 'Outstanding balance prevents gate access.',
        }

    return {
        'ok': True,
        'user_type': 'member',
        'member_id': member.member_id,
        'member_name': member.full_name,
        'gym_access': True,
        'reason': 'Access allowed by software rules.',
    }


def evaluate_staff_access(staff):
    if not staff:
        raise AccessDecisionError('Staff not found.')

    if not staff.is_active or (staff.user and not staff.user.is_active):
        return {
            'ok': False,
            'user_type': 'staff',
            'staff_id': staff.staff_id,
            'staff_name': staff.full_name,
            'is_staff_active': False,
            'reason': 'Staff profile is inactive or on leave.',
        }

    return {
        'ok': True,
        'user_type': 'staff',
        'staff_id': staff.staff_id,
        'staff_name': staff.full_name,
        'is_staff_active': True,
        'reason': 'Staff access allowed by software rules.',
    }


def has_daily_attendance_for_user(user_type, user, for_date=None):
    if not user:
        return False

    attendance_date = for_date or date.today()
    lookup = Q(date=attendance_date)
    if user_type == 'member':
        return AttendanceLog.objects.filter(member=user).filter(lookup).exists()
    return AttendanceLog.objects.filter(staff=user).filter(lookup).exists()


def create_attendance_attempt(user_type, user, *, source, verification_mode, device_id, remarks, status='present', check_in_time=None):
    attendance_date = check_in_time.date() if check_in_time else date.today()
    if has_daily_attendance_for_user(user_type, user, for_date=attendance_date):
        return None, True

    attendance = AttendanceLog.objects.create(
        member=user if user_type == 'member' else None,
        staff=user if user_type == 'staff' else None,
        source=source,
        verification_mode=verification_mode,
        device_id=device_id,
        status=status,
        remarks=remarks,
        check_in_time=check_in_time if check_in_time else timezone.localtime(),
        date=attendance_date,
    )
    return attendance, False
