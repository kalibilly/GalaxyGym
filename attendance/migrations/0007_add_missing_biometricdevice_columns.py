from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0006_your_existing_migration_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='biometricdevice',
            name='firmware_version',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='biometricdevice',
            name='last_sync_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='biometricdevice',
            name='last_known_ip',
            field=models.CharField(blank=True, max_length=45),
        ),
    ]
