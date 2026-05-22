set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput

python manage.py createsuperuser --noinput || true

python manage.py makemigrations --noinput

python manage.py migrate --noinput

if [ "$DJANGO_SUPERUSER_PASSWORD" ] && [ "$DJANGO_SUPERUSER_LOGIN_ID" ] && [ "$DJANGO_SUPERUSER_EMAIL" ]; then
    echo "Creating superuser..."
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
User.objects.filter(username='$DJANGO_SUPERUSER_LOGIN_ID').delete()
User.objects.create_superuser(
    username='$DJANGO_SUPERUSER_LOGIN_ID',
    email='$DJANGO_SUPERUSER_EMAIL',
    password='$DJANGO_SUPERUSER_PASSWORD'
)
print('Superuser created!')
"
fi
