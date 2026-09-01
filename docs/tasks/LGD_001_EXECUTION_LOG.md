# LGD-001 Execution Log

This log records implementation evidence for the approved task backlog. It contains no case data,
credentials, generated-document content, or other sensitive payloads.

## FND-001 — Scaffold the reproducible Django and dependency baseline

- **Completion date:** 2026-09-01
- **Outcome:** Added a reproducible Python 3.13.15 / Django 5.2.17 monolith scaffold,
  hash-locked Python environments, an npm lock, five acyclic application namespaces, PostgreSQL URL
  parsing, Django entry points, and a non-disclosing placeholder response.
- **Important files changed:** `manage.py`, `config/`, `apps/`, `requirements/`, `pyproject.toml`,
  `package.json`, `package-lock.json`, `.python-version`, `.gitignore`, `.env.example`, `README.md`,
  bootstrap smoke tests, and the Tailwind input.
- **Migrations created:** None. Django's 18 built-in `admin`, `auth`, `contenttypes`, and `sessions`
  migrations applied successfully to the ignored development database.
- **Focused tests executed:** Bootstrap, dependency-version, Django entry-point/URL/command, and
  PostgreSQL profile tests: 12 passed plus 2 parameter subtests.
- **Broader checks executed:** `npm ci` (0 vulnerabilities), `npm run css:build`, `python manage.py
  check`, `python manage.py makemigrations --check --dry-run`, `ruff check .`, `ruff format --check
  .`, and `mypy apps config` passed.
- **Manual or visual verification:** Django 5.2.17 development server started on Python 3.13.15;
  an HTTP request to `/` returned `200`, `text/plain; charset=utf-8`, and exactly `OK`.
- **Security or privacy review:** Only fake development placeholders are present; runtime private,
  environment, database, compiled-static, and dependency directories are ignored. No public media
  or admin route, CDN, domain model, cross-app import, personal data, debug output, or test
  suppression was introduced.
- **Approved deviations:** None.
- **Remaining blockers:** None.

## FND-002 — Establish settings, locale, storage, and HTTP baselines

- **Completion date:** 2026-09-01
- **Outcome:** Split base/development/test/production settings; made production inputs fail closed;
  configured Vietnamese-only locale, UTC-aware storage and Ho Chi Minh presentation; added
  non-public private storage and overlap checks; and delivered generic liveness/readiness endpoints.
- **Important files changed:** `config/settings/`, `config/environment.py`, `config/urls.py`, Django
  entry points, `apps/core/{storage,checks,views}.py`, `locale/`, `pyproject.toml`, `.env.example`,
  `README.md`, and focused core tests.
- **Migrations created:** None. Migration drift check reported no changes.
- **Focused tests executed:** Settings, environment validation, locale/time-zone, private storage,
  deployment check, and health tests: 15 passed.
- **Broader checks executed:** Full pytest/branch-coverage gate: 27 passed and 100% current `apps`
  branch coverage. `ruff check .`, `ruff format --check .`, `mypy apps config`, `python manage.py
  check`, migration drift, `npm run css:build`, `makemessages`, `compilemessages`, and production
  `collectstatic` passed. Production `check --deploy` exited successfully with only `security.W004`;
  the check remains enabled and HSTS is intentionally deferred until the HTTPS validation required
  by `SEC-002`.
- **Manual or visual verification:** Development server returned generic `200 OK` responses for
  `/`, `/health/live/`, and `/health/ready/` with `Content-Language: vi` and `Cache-Control:
  no-store`. A synthetic UTC instant displayed as `2026-01-01T07:00:00+07:00` under the Vietnamese
  runtime. There is no user interface at this checkpoint requiring responsive visual inspection.
- **Security or privacy review:** Production rejects absent values and wildcard hosts/origins;
  private and static paths must not overlap; stored private files/directories were verified as
  `0600`/`0700`; URL generation and direct private/media routes are denied; readiness failures
  return no exception or database detail. No personal data, credentials, sensitive logging, public
  media route, test suppression, or business model was introduced.
- **Approved deviations:** None.
- **Remaining blockers:** None. Production HSTS rollout remains assigned to `SEC-002` after HTTPS
  validation, as required by the locked specification.
