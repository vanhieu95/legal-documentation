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
npm run css:build

# Localization
python manage.py makemessages --all --no-obsolete
python manage.py compilemessages

# Tests and branch coverage
pytest --cov=apps --cov-branch --cov-report=term-missing

# Production checks (requires the documented production environment)
python manage.py check --deploy --settings=config.settings.production
python manage.py collectstatic --noinput
```

PostgreSQL-backed constraint, migration, integration, and concurrency checks must run against
PostgreSQL rather than SQLite once those behaviors are introduced.
