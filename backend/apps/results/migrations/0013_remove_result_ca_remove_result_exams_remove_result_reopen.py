from django.db import migrations


def clear_legacy_results(apps, schema_editor):
    apps.get_model("results", "Result").objects.using(schema_editor.connection.alias).all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0012_result_exam_result_group_work_result_test1_result_test2"),
    ]

    operations = [
        migrations.RunPython(clear_legacy_results, migrations.RunPython.noop),
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
