# Vietnamese Civil-Matter Document Administration

This repository contains the approved Django monolith for administering Vietnamese civil-matter
cases, templates, and generated DOCX records. Implementation is proceeding in the mandatory
micro-checkpoints defined in `docs/tasks/LGD_001_TASKS.md`.

## Supported toolchain

- Python 3.13.15
- Django 5.2.17 LTS
- PostgreSQL 14 or newer for integration and production use
- Node.js 22 or newer with npm

## Clean development installation

Create and activate an isolated Python environment, then install only from the committed lock:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements/development.txt
npm ci
npm run css:build
python manage.py check
python manage.py runserver
```

The temporary root response is `OK`. It is intentionally not an application page. Stop the server
with <kbd>Ctrl</kbd>+<kbd>C</kbd>.

Never use values from `.env.example` in production. It contains development-only placeholders and
is not loaded automatically. Runtime private files, generated static files, virtual environments,
and local environment files are excluded from version control.

## Settings and runtime boundaries

`manage.py` defaults to `config.settings.development`, pytest uses `config.settings.test`, and the
WSGI/ASGI entry points default to `config.settings.production`. Production refuses to start unless
all of these values are present and valid:

| Environment variable | Required shape |
| --- | --- |
| `DJANGO_SECRET_KEY` | Secret value supplied outside source control |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated explicit host names; no wildcard |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated explicit HTTPS origins |
| `DATABASE_URL` | Complete `postgresql://` URL; optional `sslmode` query value |
| `DJANGO_PRIVATE_STORAGE_ROOT` | Absolute private-volume path |
| `DJANGO_STATIC_ROOT` | Absolute collected-static path, separate from private storage |

The application creates private files with mode `0600` and private directories with mode `0700`.
Provision the private volume for only the application and backup identities, keep it outside every
static/web root, and do not add a media route. Both the default and `private` Django storage aliases
deny direct URL generation.

The content-free health contracts are `GET /health/live/` and `GET /health/ready/`. Readiness checks
the configured database but returns only `OK` or `Unavailable`; neither endpoint returns paths,
versions, counts, configuration, or credentials.

## Dependency maintenance

Direct dependencies are exact pins in `requirements/*.in` and `package.json`. Regenerate and review
Python locks with the same Python release used by the application:

```bash
pip-compile --generate-hashes --strip-extras --output-file requirements/base.txt requirements/base.in
pip-compile --generate-hashes --strip-extras --output-file requirements/development.txt requirements/development.in
pip-compile --generate-hashes --strip-extras --output-file requirements/production.txt requirements/production.in
npm install --package-lock-only --ignore-scripts
```

## Command mapping

```bash
# Python quality
ruff check .
ruff format --check .
mypy apps config

# Django configuration
python manage.py check
python manage.py makemigrations --check --dry-run

# Frontend assets
npm run assets:verify
npm run css:build

# Localization
python manage.py makemessages --all --no-obsolete
python manage.py compilemessages

# Tests and branch coverage
pytest --cov=apps --cov-branch --cov-report=term-missing
python scripts/check_sensitive_coverage.py

# Browser smoke (install the pinned Chromium build once, then run)
npm run browser:install
npm run browser:test

# Production checks (requires the documented production environment)
python manage.py check --deploy --settings=config.settings.production
python manage.py collectstatic --noinput
```

PostgreSQL-backed constraint, migration, integration, and concurrency checks must run against
PostgreSQL rather than SQLite. Set `TEST_DATABASE_URL` to a disposable PostgreSQL database before
running pytest; the default in-memory SQLite profile remains available for lightweight unit tests.
The integration profile applies migrations to a pytest-managed test database and marks its checks
with `postgresql`. Shared fixtures include a CSRF-enforcing `csrf_client` and an explicit,
non-privileged `user_factory` that creates only synthetic `example.invalid` identities.

The blocking GitHub Actions quality gate uses Python 3.13, Node.js 22, and PostgreSQL 17. It installs
only the committed dependency locks, applies migrations from zero, and propagates failures from
tests, overall and sensitive-module branch coverage, linting, formatting, typing, Django checks,
migration drift, CSS, localization, static collection, deployment checks, and the browser smoke.
Remote CI does not retain test artifacts or application data.

## Frontend foundation

The component gallery is served at `/foundation/components/`. It demonstrates semantic buttons,
form help and validation, live alerts, text-labeled status badges, a contained responsive table,
a native dialog, and loading/empty/offline/conflict states. It is a design-system fixture, not an
application dashboard or workflow.

Tailwind CSS 4 builds directly with its pinned CLI; no Vite or frontend application runtime is
used. HTMX and the Alpine CSP build are served only from committed local static files. Their npm
provenance and SHA-256 values are recorded in `static/vendor/manifest.json` and can be reproduced
with `npm run assets:vendor`. `npm run assets:verify` fails if a committed asset, exact package pin,
or checksum drifts. The application script disables HTMX history and runtime evaluation, clears
HTMX path metadata, and persists only the non-sensitive `vds-theme` preference; it never persists
application records or form values and treats client-side visibility only as presentation.
