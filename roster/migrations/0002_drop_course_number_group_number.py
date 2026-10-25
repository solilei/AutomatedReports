from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("roster", "0001_initial")]

    operations = [
        migrations.RemoveField(model_name="group", name="course_number"),
        migrations.RemoveField(model_name="rosterupload", name="course_number"),
        migrations.RemoveField(model_name="rosterupload", name="group_col"),
        migrations.RemoveField(model_name="rostercolumnpreference", name="group_header"),
        migrations.AddField(
            model_name="rosterupload",
            name="group_number",
            field=models.CharField(default="", max_length=20),
            preserve_default=False,
        ),
    ]
