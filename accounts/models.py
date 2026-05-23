from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import phone_regex


class UserAccountManager(BaseUserManager):
    def create_user(
        self,
        login_id,
        password=None,
        phone_number=None,
        email=None,
        full_name='',
        role='member',
        is_active=True,
        **extra_fields,
    ):
        if not login_id:
            raise ValueError('The login_id field is required.')
        email = self.normalize_email(email)
        user = self.model(
            login_id=login_id,
            phone_number=phone_number,
            email=email,
            full_name=full_name,
            role=role,
            is_active=is_active,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, login_id, password=None, **extra_fields):
        extra_fields.setdefault('role', UserAccount.ROLE_OWNER)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(login_id, password=password, **extra_fields)


class UserAccount(AbstractBaseUser, PermissionsMixin):
    ROLE_OWNER = 'owner'
    ROLE_MEMBER = 'member'
    ROLE_STAFF = 'staff'

    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_MEMBER, 'Member'),
        (ROLE_STAFF, 'Staff'),
    ]

    login_id = models.CharField(max_length=32, unique=True)
    full_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True, null=True, unique=True)
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        validators=[phone_regex],
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(blank=True, null=True)

    objects = UserAccountManager()

    USERNAME_FIELD = 'login_id'
    REQUIRED_FIELDS = ['phone_number']

    class Meta:
        verbose_name = 'User Account'
        verbose_name_plural = 'User Accounts'
        ordering = ['login_id']

    def __str__(self):
        return self.login_id

    def get_full_name(self):
        return self.full_name or self.login_id

    def get_short_name(self):
        return self.full_name or self.login_id


class GymIssuedID(models.Model):
    code = models.CharField(max_length=32, unique=True)
    role = models.CharField(max_length=10, choices=UserAccount.ROLE_CHOICES)
    is_used = models.BooleanField(default=False)
    used_by = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='gym_issued_id',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Gym Issued ID'
        verbose_name_plural = 'Gym Issued IDs'
        ordering = ['code']

    def __str__(self):
        return f'{self.code} ({self.role})'


class SignupRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    requested_role = models.CharField(max_length=10, choices=UserAccount.ROLE_CHOICES)
    unique_id = models.CharField(max_length=32)
    full_name = models.CharField(max_length=120)
    phone_number = models.CharField(max_length=20, validators=[phone_regex])
    email = models.EmailField(blank=True, null=True)
    desired_login_id = models.CharField(max_length=32, unique=True)
    password_hash = models.CharField(max_length=255)
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_signup_requests',
    )
    rejection_reason = models.TextField(blank=True, null=True)
    whatsapp_notified = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)
    
    created_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='signup_request',
    )

    class Meta:
        verbose_name = 'Signup Request'
        verbose_name_plural = 'Signup Requests'
        ordering = ['-submitted_at']
        unique_together = ('desired_login_id', 'phone_number')

    def __str__(self):
        return f'{self.full_name} ({self.requested_role}) - {self.status}'

    def approve(self, reviewed_by):
        """
        Approve the signup request and create the user account.
        """
        if self.status == self.STATUS_APPROVED:
            if self.created_user:
                return self.created_user

            existing_user = UserAccount.objects.filter(login_id=self.desired_login_id).first()
            if existing_user:
                self.created_user = existing_user
                self.reviewed_at = self.reviewed_at or timezone.now()
                self.reviewed_by = reviewed_by or self.reviewed_by
                self.save(update_fields=['created_user', 'reviewed_at', 'reviewed_by'])
                return existing_user

        if self.status != self.STATUS_PENDING:
            raise ValueError(f'Can only approve pending requests. Current status: {self.status}')

        if UserAccount.objects.filter(login_id=self.desired_login_id).exists():
            raise ValueError(f'User with login_id {self.desired_login_id} already exists.')

        user = UserAccount(
            login_id=self.desired_login_id,
            email=self.email,
            phone_number=self.phone_number,
            full_name=self.full_name,
            role=self.requested_role,
            is_active=True,
            is_verified=True,
            is_staff=self.requested_role in {UserAccount.ROLE_OWNER, UserAccount.ROLE_STAFF},
        )
        user.password = self.password_hash
        user.save()

        self.status = self.STATUS_APPROVED
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewed_by
        self.created_user = user
        self.save()

        return user

    def reject(self, reviewed_by, reason=''):
        """
        Reject the signup request.
        """
        if self.status != self.STATUS_PENDING:
            raise ValueError(f'Can only reject pending requests. Current status: {self.status}')

        self.status = self.STATUS_REJECTED
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewed_by
        self.rejection_reason = reason
        self.save()
