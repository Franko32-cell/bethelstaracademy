from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0012_result_exam_result_group_work_result_test1_result_test2"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="result",
            name="ca",
        ),
        migrations.RemoveField(
            model_name="result",
            name="exams",
        ),
        migrations.RemoveField(
            model_name="result",
            name="reopen",
        ),
    ]
