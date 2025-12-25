from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		("theming", "0001_initial"),
	]

	operations = [
		migrations.AddField(
			model_name="themesettings",
			name="background_gradients",
			field=models.BooleanField(
				default=True,
				help_text="If disabled, removes the decorative background gradients.",
			),
		),
		migrations.AddField(
			model_name="themesettings",
			name="compact_layout",
			field=models.BooleanField(
				default=False,
				help_text="If enabled, reduces padding for a denser layout.",
			),
		),
		migrations.AddField(
			model_name="themesettings",
			name="snow_effect",
			field=models.BooleanField(
				default=False,
				help_text="If enabled, shows a subtle falling-snow effect.",
			),
		),
	]
