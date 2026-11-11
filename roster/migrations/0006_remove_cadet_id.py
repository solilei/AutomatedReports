from collections import defaultdict

from django.db import migrations, models
from django.db.models.functions import Lower


def check_names_unique(apps, schema_editor):
    """Without IDs, names identify cadets. Stop if a group has two cadets with one name."""
    Cadet = apps.get_model("roster", "Cadet")
    seen = defaultdict(list)
    for group_number, name in Cadet.objects.values_list("group__number", "name"):
        seen[(group_number, name.casefold())].append(name)
    clashes = [
        f"group {number}: {', '.join(names)}"
        for (number, _), names in sorted(seen.items())
        if len(names) > 1
    ]
    if clashes:
        raise RuntimeError(
            "Cadet IDs are being removed, so names must be unique within a group. "
            "Rename or delete these cadets first: " + "; ".join(clashes)
        )


def reopen_parsed_uploads(apps, schema_editor):
    """Open uploads parsed with an ID column go back to the column step."""
    RosterUpload = apps.get_model("roster", "RosterUpload")
    RosterUpload.objects.filter(status="parsed").update(status="uploaded", parsed={}, name_col=None)


class Migration(migrations.Migration):
    dependencies = [
        ("roster", "0005_programme"),
    ]

    operations = [
        migrations.RunPython(check_names_unique, migrations.RunPython.noop),
        migrations.RunPython(reopen_parsed_uploads, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="cadet", name="unique_cadet_id_per_group"),
        migrations.RemoveConstraint(model_name="cadet", name="unique_cadet_name_per_group"),
        migrations.RemoveField(model_name="cadet", name="external_id"),
        migrations.AddConstraint(
            model_name="cadet",
            constraint=models.UniqueConstraint(
                models.F("group"), Lower("name"), name="unique_cadet_name_per_group"
            ),
        ),
        migrations.RemoveField(model_name="group", name="identity_mode"),
        migrations.RemoveField(model_name="rostercolumnpreference", name="id_header"),
        migrations.RemoveField(model_name="rosterupload", name="id_col"),
    ]
