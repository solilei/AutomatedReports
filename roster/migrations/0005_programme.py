import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("roster", "0004_cadet_name_ignores_case"),
        ("scoring", "0004_atpl"),
    ]

    operations = [
        migrations.AddField(
            model_name="group",
            name="programme",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="groups",
                to="scoring.programme",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="rosterupload",
            name="programme",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="scoring.programme",
            ),
        ),
    ]
