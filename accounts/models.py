from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from core.models import phone_regex


class UserAccountManager(BaseUserManager):
    def create_user(self, login_id, phone_number=None, email=None, password=None, role='member', **extra_fields):
        if not login_id:
            raise ValueError('The login_id field is required.')
        email = self.normalize_email(email)
        user = self.model(
            login_id=login_id,
            phone_number=phone_number,
            email=email,
            role=role,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, login_id, password=None, **extra_fields):
        extra_fields.setdefault('role', 'owner')
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
        return self.login_id

    def get_short_name(self):
        return self.login_id
