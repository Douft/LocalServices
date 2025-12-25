from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		("theming", "0002_theme_settings_more_options"),
	]

	operations = [
		migrations.AddField(
			model_name="themesettings",
			name="color_scheme",
			field=models.CharField(
				choices=[
					("midnight", "Midnight"),
					("frost", "Frost"),
					("sunset", "Sunset"),
					("forest", "Forest"),
				],
				default="midnight",
				help_text="Choose the site color template.",
				max_length=32,
			),
		),
	]
