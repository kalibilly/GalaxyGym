from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0005_biometricdevicecommand_biometricrawevent_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='biometricdevice',
            name='device_type',
            field=models.CharField(
                max_length=32,
                choices=[
                    ('unknown', 'Unknown'),
                    ('mb20', 'MB20'),
                    ('aiface', 'AiFace'),
                ],
                default='unknown',
            ),
        ),
    ]
