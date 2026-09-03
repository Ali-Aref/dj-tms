from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0003_terminal_last_location")]

    operations = [
        migrations.AddField(
            model_name="terminal",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending approval"),
                    ("active", "Active"),
                    ("deleted", "Deleted / revoked"),
                    ("decommissioned", "Decommissioned"),
                ],
                default="active",
                max_length=32,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="terminal",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending approval"),
                    ("active", "Active"),
                    ("deleted", "Deleted / revoked"),
                    ("decommissioned", "Decommissioned"),
                ],
                default="pending",
                max_length=32,
            ),
        ),
    ]
