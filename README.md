# Local Services

Django-based local service finder with a public search page, optional external provider lookups (OSM/Google), theming, ads, and basic analytics.

## Deploy on Render (from GitHub)

### Required settings (Render → Environment)

- `SECRET_KEY`: set to a long random value
- `DEBUG`: `False`
- `ALLOWED_HOSTS`: include your Render hostname (e.g. `localservices.onrender.com`)

Recommended for POST forms over HTTPS:
- `CSRF_TRUSTED_ORIGINS`: `https://localservices.onrender.com`

Recommended:
- `SQLITE_PATH`: `/var/data/db.sqlite3` (when using a Render persistent disk)
- `OSM_USER_AGENT`: something identifiable like `LocalServices/1.0 (contact@example.com)`
- `OSM_CONTACT_EMAIL`: optional

Optional (if you want Google Places instead of OSM):
- Set this in Admin → Provider settings (preferred), or as env vars:
  - `PROVIDER_BACKEND=GOOGLE`
  - `GOOGLE_MAPS_API_KEY=...`

### Build command

Render will install dependencies from `requirements.txt` automatically, but if you set a build command:

- `pip install -r requirements.txt && python manage.py collectstatic --noinput`

### Start command

- `gunicorn app.wsgi:application`

Demo-safe option (auto-migrate on startup):
- Set env var `AUTO_MIGRATE_ON_STARTUP=True` (and optionally `AUTO_SEED_DEMO_ON_STARTUP=True`).

### One-time / per-deploy commands

Run migrations at least once after deploy:

- `python manage.py migrate`

Optional demo content (dev/testing only):

- `python manage.py seed_demo`

## Local run

- `python manage.py migrate`
- `python manage.py seed_demo`
- `python manage.py runserver`

## Backup (ZIP snapshot)

Creates a timestamped ZIP of the project into `backup/` (excludes `.venv`, `.git`, `__pycache__`, and the backup folders themselves):

- PowerShell (run from the project root):
  - `$ErrorActionPreference='Stop'; $root=(Get-Location).Path; $destDir=Join-Path $root 'backup'; if (!(Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir | Out-Null }; $timestamp=Get-Date -Format 'yyyyMMdd-HHmmss'; $zipPath=Join-Path $destDir "local_services-backup-$timestamp.zip"; $exclude=@('.venv','__pycache__','.git','backup','backups','staticfiles'); $items=Get-ChildItem -LiteralPath $root -Force | Where-Object { $exclude -notcontains $_.Name }; Compress-Archive -LiteralPath $items.FullName -DestinationPath $zipPath -CompressionLevel Optimal; Get-Item $zipPath | Select-Object FullName,Length,LastWriteTime`
