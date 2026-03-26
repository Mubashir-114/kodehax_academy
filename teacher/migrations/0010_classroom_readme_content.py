from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("teacher", "0009_alter_assignment_id_alter_chatmessage_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="classroom",
            name="readme_content",
            field=models.TextField(blank=True, null=True),
        ),
    ]
