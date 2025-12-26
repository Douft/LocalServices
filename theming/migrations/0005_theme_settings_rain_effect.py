from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		("theming", "0004_theme_settings_more_color_schemes"),
	]

	operations = [
		migrations.AddField(
			model_name="themesettings",
			name="rain_effect",
			field=models.BooleanField(
				default=False,
				help_text="If enabled, shows a subtle falling-rain effect.",
			),
		),
	]
