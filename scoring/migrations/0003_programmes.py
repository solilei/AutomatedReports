import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from scoring.programmes import refuse_if_data


def guard(apps, schema_editor):
    refuse_if_data(apps)


class Migration(migrations.Migration):

    dependencies = [
        ("roster", "0004_cadet_name_ignores_case"),
        ("scoring", "0002_scoreset_cadetscore_scoreset_unique_score_set_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(guard, migrations.RunPython.noop),
        migrations.CreateModel(
            name="Programme",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("group_prefix", models.CharField(blank=True, default="", max_length=10)),
                ("is_fixed", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AlterField(
            model_name="subject",
            name="name",
            field=models.CharField(max_length=100),
        ),
        migrations.AddField(
            model_name="subject",
            name="programme",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subjects",
                to="scoring.programme",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="subject",
            name="instructors",
            field=models.ManyToManyField(
                blank=True, related_name="assigned_subjects", to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AlterModelOptions(
            name="subject",
            options={"ordering": ["programme__name", "name"]},
        ),
        migrations.AddConstraint(
            model_name="subject",
            constraint=models.UniqueConstraint(
                fields=("programme", "name"), name="unique_subject_per_programme"
            ),
        ),
        migrations.CreateModel(
            name="CadetSubjectExclusion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("cadet", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="exclusions", to="roster.cadet")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="scoring.subject")),
            ],
        ),
        migrations.AddConstraint(
            model_name="cadetsubjectexclusion",
            constraint=models.UniqueConstraint(fields=("cadet", "subject"), name="unique_exclusion"),
        ),
    ]
