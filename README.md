# Local Services

Django-based local service finder with a public search page, optional external provider lookups (OSM/Google), theming, ads, and basic analytics.

## Deploy on Render (from GitHub)

### Required settings (Render → Environment)

- `SECRET_KEY`: set to a long random value
- `DEBUG`: `False`
- `ALLOWED_HOSTS`: include your Render hostname (e.g. `your-service.onrender.com`)

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

- `pip install -r requirements.txt`

### Start command

- `gunicorn app.wsgi:application`

### One-time / per-deploy commands

Run migrations at least once after deploy:

- `python manage.py migrate`

Optional demo content (dev/testing only):

- `python manage.py seed_demo`

## Local run

- `python manage.py migrate`
- `python manage.py seed_demo`
- `python manage.py runserver`
