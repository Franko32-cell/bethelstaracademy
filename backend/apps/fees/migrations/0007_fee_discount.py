from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fees", "0006_alter_fee_unique_together_fee_school_class_fee_year_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="fee",
            name="discount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
