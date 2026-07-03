from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0006_add_biometricdevice_device_type'),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
