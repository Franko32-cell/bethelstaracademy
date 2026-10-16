from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0014_report_head_teacher_remark"),
    ]

    operations = [
        migrations.AddField(
            model_name="report",
            name="attitude",
            field=models.TextField(blank=True, default=""),
        ),
    ]
