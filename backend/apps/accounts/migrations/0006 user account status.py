from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_user_is_approved"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="account_status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("inactive", "Inactive"),
                    ("suspended", "Suspended"),
                    ("archived", "Archived"),
                ],
                default="active",
                help_text=(
                    "Drives is_active automatically. 'suspended' and 'archived' "
                    "both disable login, but are tracked separately from a plain "
                    "deactivation for audit/reporting purposes."
                ),
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]