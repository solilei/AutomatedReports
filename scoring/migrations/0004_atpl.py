from django.db import migrations

from scoring.programmes import ATPL_NAME, ATPL_PREFIX, ATPL_SUBJECTS, refuse_if_data


def create_atpl(apps, schema_editor):
    refuse_if_data(apps)
    Programme = apps.get_model("scoring", "Programme")
    Subject = apps.get_model("scoring", "Subject")
    atpl = Programme.objects.create(name=ATPL_NAME, group_prefix=ATPL_PREFIX, is_fixed=True)
    for name in ATPL_SUBJECTS:
        Subject.objects.create(name=name, programme=atpl)


class Migration(migrations.Migration):

    dependencies = [("scoring", "0003_programmes")]

    operations = [migrations.RunPython(create_atpl, migrations.RunPython.noop)]
