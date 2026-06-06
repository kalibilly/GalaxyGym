from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = False

    dependencies = [
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='membership_plan',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='invoices_by_plan', to='memberships.membershipplan'),
        ),
        migrations.AddField(
            model_name='invoice',
            name='membership_end_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
