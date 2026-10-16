from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0013_remove_result_ca_remove_result_exams_remove_result_reopen"),
    ]

    operations = [
        migrations.AddField(
            model_name="report",
            name="head_teacher_remark",
            field=models.TextField(blank=True, default=""),
        ),
    ]
