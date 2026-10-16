from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0011_mockresult_preschoolassessment"),
    ]

    operations = [
        migrations.AddField(
            model_name="result",
            name="exam",
            field=models.FloatField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]),
        ),
        migrations.AddField(
            model_name="result",
            name="group_work",
            field=models.FloatField(default=0, validators=[MinValueValidator(0), MaxValueValidator(20)]),
        ),
        migrations.AddField(
            model_name="result",
            name="test1",
            field=models.FloatField(default=0, validators=[MinValueValidator(0), MaxValueValidator(20)]),
        ),
        migrations.AddField(
            model_name="result",
            name="test2",
            field=models.FloatField(default=0, validators=[MinValueValidator(0), MaxValueValidator(20)]),
        ),
    ]
