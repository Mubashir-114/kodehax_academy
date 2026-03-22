from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("adminpanel", "0005_sitesettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="force_logout_generation",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
