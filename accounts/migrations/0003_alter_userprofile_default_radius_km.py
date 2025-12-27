from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		("accounts", "0002_alter_userprofile_country"),
	]

	operations = [
		migrations.AlterField(
			model_name="userprofile",
			name="default_radius_km",
			field=models.PositiveIntegerField(
				default=50,
				help_text="Default search radius (used when we have lat/lng).",
			),
		),
	]
