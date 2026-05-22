set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput

python manage.py migrate --noinput

if [ "$DJANGO_SUPERUSER_PASSWORD" ] && [ "$DJANGO_SUPERUSER_LOGIN_ID" ] && [ "$DJANGO_SUPERUSER_EMAIL" ] && [ "$DJANGO_SUPERUSER_PHONE_NUMBER" ]; then
    echo "Ensuring superuser exists..."
    python manage.py shell -c "
from django.contrib.auth import get_user_model

User = get_user_model()
login_id = '$DJANGO_SUPERUSER_LOGIN_ID'
email = '$DJANGO_SUPERUSER_EMAIL'
phone_number = '$DJANGO_SUPERUSER_PHONE_NUMBER'
password = '$DJANGO_SUPERUSER_PASSWORD'

user = User.objects.filter(login_id=login_id).first()

if user is None:
    User.objects.create_superuser(
        login_id=login_id,
        email=email,
        phone_number=phone_number,
        password=password
    )
    print('Superuser created successfully.')
else:
    updated = False

    if user.email != email:
        user.email = email
        updated = True

    if hasattr(user, 'phone_number') and user.phone_number != phone_number:
        user.phone_number = phone_number
        updated = True

    if not user.is_staff:
        user.is_staff = True
        updated = True

    if not user.is_superuser:
        user.is_superuser = True
        updated = True

    if not user.is_active:
        user.is_active = True
        updated = True

    user.set_password(password)
    updated = True

    if updated:
        user.save()
        print('Existing superuser updated successfully.')
    else:
        print('Superuser already exists and is up to date.')
"
else
    echo "Skipping superuser creation. Required environment variables are missing."
    echo "Required: DJANGO_SUPERUSER_LOGIN_ID, DJANGO_SUPERUSER_EMAIL, DJANGO_SUPERUSER_PHONE_NUMBER, DJANGO_SUPERUSER_PASSWORD"
fi
