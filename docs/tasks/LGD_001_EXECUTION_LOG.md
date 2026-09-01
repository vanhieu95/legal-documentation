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

## FND-003 — Build the test, coverage, and CI quality gate

- **Completion date:** 2026-09-01
- **Outcome:** Added a blocking GitHub Actions quality job with restricted permissions, full-SHA
  action pins, Python 3.13, Node.js 22, PostgreSQL 17, locked installs, migration-from-zero,
  branch-coverage, Python/Django, CSS, i18n, static/deploy, and Playwright gates. Added PostgreSQL
  test settings, synthetic non-privileged factories, a CSRF-enforcing client, and an automatically
  armed 95% sensitive-module branch gate on top of the 85% overall threshold.
- **Important files changed:** `.github/workflows/ci.yml`, `pyproject.toml`, `config/settings/test.py`,
  `tests/conftest.py`, `tests/factories.py`, PostgreSQL/quality/coverage tests,
  `scripts/check_sensitive_coverage.py`, `playwright.config.js`, browser smoke, locks, and `README.md`.
- **Dependencies and locks changed:** Added exact `factory-boy==3.3.3` (and locked Faker 40.37.0)
  and `@playwright/test` 1.62.1. Python hashes and npm integrity metadata are committed; npm audit
  reported zero vulnerabilities.
- **Tests and commands executed:** The task run passed 38 PostgreSQL-backed tests at 100% current
  `apps` branch coverage, sensitive coverage activation, Ruff lint/format, mypy, Django checks,
  migration drift, Tailwind, message extraction/compilation, deploy checks, static collection, CI
  YAML parsing, and the Playwright health smoke. The final checkpoint run passed 44 tests.
- **Migration verification:** A disposable PostgreSQL 18.6 database applied all 18 built-in Django
  migrations from zero; the PostgreSQL integration test ran without a skip and drift remained empty.
- **Security/privacy review:** CI has `contents: read`, checkout credentials are not persisted,
  untrusted pull requests do not receive secrets, no allow-failure/advisory gate or retained artifact
  exists, and only synthetic `example.invalid` identities and environment values are used.
- **CI status:** Workflow syntax, ordering, service configuration, and every equivalent gate passed
  locally. No remote GitHub Actions run was observable, so the remote result remains **pending**.
- **Commit:** `150ecac` (`build(quality): establish blocking CI gate`).
- **Remaining blockers:** Remote CI observation only; no implementation blocker.

## FND-004 — Implement local frontend assets and design-system primitives

- **Completion date:** 2026-09-01
- **Outcome:** Delivered the Tailwind 4 CLI foundation, 4px semantic tokens, light/dark/system themes,
  accessible buttons/forms/alerts/badges/table/dialog/status states, a no-JavaScript baseline, and a
  Vietnamese component gallery at `/foundation/components/` without Vite or an application shell.
- **Important files changed:** `static_src/{css,js}/`, generated first-party `static/js/app.js`,
  checksummed `static/vendor/`, deterministic vendor script, `templates/base.html`,
  `templates/components/`, gallery template/view/URL, frontend/browser tests, CI, npm lock, and docs.
- **Dependencies and locks changed:** Replaced standard Alpine 3.16.3 with exact CSP-friendly
  `@alpinejs/csp` 3.17.1; retained exact HTMX 2.0.10 and Tailwind 4.3.3. The manifest records source,
  SPDX license, version, destination, and SHA-256 for both vendored runtime files.
- **Tests and commands executed:** Six frontend foundation tests, 11 Playwright tests, `npm ci`,
  `npm run assets:verify`, `npm run css:build`, Tailwind watch startup, full Python coverage and
  quality commands, Django/i18n/static/deploy commands, development server startup, and secret/CDN
  scans passed.
- **Browser and accessibility checks:** Pinned Chromium passed compact 375px, tablet 768px, and wide
  1440px reflow; keyboard skip-link and dialog focus containment/Escape/restore; visible focus;
  200% zoom; light/dark/system; reduced motion; forced colors; strict no-eval CSP; and JavaScript-off
  rendering. Temporary compact-light, tablet-dark, and wide-light screenshots were manually
  inspected and were not retained in the repository. Chrome DevTools MCP was unavailable, so the
  configured real Playwright browser was used instead.
- **Security/privacy review:** No CDN, Vite, SPA, client router, public media route, runtime eval,
  sensitive persistence, or client authority was added. HTMX history is disabled and its path key
  cleared; only the non-sensitive `vds-theme` preference may persist. No case/legal/personal data,
  domain models, workflows, screenshots, or debug artifacts are present.
- **Commit:** `2413bc5` (`feat(frontend): add accessible local design primitives`).
- **Remaining blockers:** None.

## CP-FND-B — Checkpoint closure

- **Completion date:** 2026-09-01
- **Outcome:** Local CP-FND-B gates passed and `FND-003`/`FND-004` are complete. `FND-001` and
  `FND-002` remained unchanged after regression verification.
- **Checkpoint evidence:** A newly empty PostgreSQL database applied migrations from zero; locked
  Python/npm installs, asset hashes, CSS, i18n, 44 tests with 100% branch coverage, sensitive gate,
  Ruff, mypy, Django system/drift/deploy checks, static collection, runserver/watch startup, CI YAML,
  11 browser tests, and security/privacy scans passed. Deploy check retained only the expected HSTS
  warning assigned to `SEC-002`.
- **CI status:** All local equivalents passed; remote GitHub Actions result is **pending** and the
  corresponding Milestone 1 checkbox remains open rather than being reported as passed.
- **Commits:** `150ecac` (FND-003) and `2413bc5` (FND-004).
- **Unresolved blockers:** Remote CI observation only. The next eligible task is `IAM-001`; it was
  not started.

## IAM-001 — Define Administrator permissions and deny-by-default policy

- **Completion date:** 2026-09-01
- **Outcome:** Added a table-free permission anchor, the exact 21-permission application contract,
  deterministic Administrator group seeding, an idempotent synchronization command, and one
  deny-by-default policy shared by view decorators, direct service checks, object-scoped lookup,
  presentation hints, and superuser-only account administration.
- **Important files changed:** `apps/accounts/{models,permissions,policies}.py`, the account
  management command, permission template tag, Vietnamese generic `403`/`404` handlers/templates,
  focused account tests, and the Playwright non-disclosure smoke.
- **Migrations created:** `apps/accounts/migrations/0001_seed_administrator_permissions.py` creates
  only a proxy-model content type and permission/group data; it creates no business table. Forward,
  repeat, absent-state, member-preservation, and practical reverse behavior are tested.
- **Focused tests executed:** 14 SQLite permission/policy/migration tests passed; the same suite plus
  the PostgreSQL migration-profile test passed against an isolated PostgreSQL 18.6 cluster (15
  passed). The principal matrix covers anonymous, inactive, non-Administrator, Administrator,
  missing permission, active/inactive superuser, inaccessible/nonexistent object, direct service,
  UUID knowledge, hidden presentation, and account-administration denial paths.
- **Broader checks executed:** Full suite: 57 passed and 1 PostgreSQL-profile skip in the ordinary
  SQLite run, 99.78% overall branch coverage, and 100% sensitive permission/migration branch
  coverage. Ruff lint/format, mypy, Django check, migration drift, Tailwind build, and diff checks
  passed.
- **Browser and accessibility verification:** The isolated Chromium suite passed 12 tests under
  non-debug settings. The Vietnamese 404 redacts the requested identifier, loads all local assets,
  has no failed subresources or compact-width page overflow, and retains the foundation keyboard,
  focus, theme, reduced-motion, CSP, no-JavaScript, and 200% zoom checks. Chrome DevTools MCP was not
  available, so the repository's pinned real Playwright browser was used.
- **Security/privacy review:** Views and services use the same server policy; object lookup scopes
  before retrieval and returns identical generic failures; presentation helpers fail closed and are
  not enforcement; normal Administrators receive no user/group administration authority. No
  future business model/table, audit infrastructure, secret, credential, personal data, debug
  output, CSRF bypass, test suppression, or sensitive browser persistence was introduced.
- **Commits:** `203d25b` (permission seed), `945bb85` (central enforcement), `8c5a6d3` (browser
  verification).
- **Deviations or blockers:** None. A temporary local PostgreSQL cluster was used because no system
  server was listening; it was stopped after the tests.

## IAM-002 — Deliver secure Vietnamese login and POST logout

- **Completion date:** 2026-09-01
- **Outcome:** Delivered purpose-built Vietnamese Administrator login, a protected dashboard
  placeholder, and authenticated POST-only logout using Django authentication and database-backed
  sessions. Active Administrator-group users and active superusers can sign in; unknown, inactive,
  and non-Administrator principals receive the same generic response with cleared fields. Login
  rotates the session identifier, logout flushes the session, and validated local `next` targets
  fail closed for external, protocol-relative, control-character, backslash, and malformed values.
- **Important files changed:** `apps/accounts/{forms,views,urls}.py`, focused authentication tests,
  Vietnamese login/dashboard-placeholder templates, auth CSS and local CSP-compatible JavaScript,
  root URLs/settings, and Playwright/frontend tests. A non-debug browser-test settings profile uses
  a migrated disposable SQLite database so runtime auth tests do not depend on an in-memory
  runserver database.
- **Migrations created:** None.
- **Focused tests executed:** 21 authentication tests passed, covering Administrator and superuser
  success, unknown/wrong/inactive/non-Administrator generic failure, CSRF on login and normal/HTMX
  logout, safe and hostile redirects, session rotation, logout invalidation/replay, `GET` logout
  rejection, forced-session authorization denial, Vietnamese labels/locale, credential clearing,
  and non-cacheable auth responses. The combined accounts/frontend suite passed 38 tests; the full
  accounts suite passed 35 on SQLite and 36 tests including the migration-profile integration test
  passed on isolated PostgreSQL 18.6.
- **Broader checks executed:** Ruff lint and format, mypy, Django system check, migration drift,
  Tailwind build, vendored-asset verification, message extraction/compilation, and the full
  coverage suite passed. The final ordinary suite reported 79 passed, one intentionally skipped
  PostgreSQL-profile test, and 99.42% overall branch coverage; the PostgreSQL profile was exercised
  separately without a skip.
- **Browser and accessibility verification:** All 16 pinned-Chromium tests passed. Login was checked
  at 375px and 1440px with keyboard navigation, visible focus, no page overflow, generic error
  summary focus, cleared fields, empty local/session storage, local assets, strict no-eval CSP, and
  JavaScript-disabled failure. A live-server workflow additionally passed Administrator login,
  non-Administrator denial, local/external redirect behavior, dashboard access, POST logout,
  logged-out session replay denial, and JavaScript-disabled successful login/logout at wide width.
  Chrome DevTools MCP was unavailable, so the repository's pinned real Playwright browser was used.
- **Security/privacy review:** Server policy remains the enforcement boundary; logout is
  authenticated, POST-only, and CSRF-protected; successful login uses Django session cycling and
  logout uses session flushing. Auth responses are `no-store`; submitted credentials and usernames
  are not re-rendered, logged, or persisted; only synthetic identities were used. No remember-me,
  registration, password delivery, MFA/SSO, audit infrastructure, business model, public storage,
  `csrf_exempt`, state-changing GET, debug artifact, test suppression, or unrelated edit was added.
- **Commit:** `a3aefb7` (`feat(identity): deliver secure administrator login`).
- **Deviations or blockers:** The environment has no global `python`, so all required Django
  commands used the equivalent locked `.venv/bin/python`. No implementation blocker remains.

## CP-IAM-A — Checkpoint closure

- **Completion date:** 2026-09-01
- **Status:** Local implementation and verification are complete; human approval is pending at the
  mandatory checkpoint pause.
- **Completed tasks:** `IAM-001`, `IAM-002`.
- **Checkpoint evidence:** Focused identity suites passed on SQLite and isolated PostgreSQL 18.6;
  Ruff lint/format, mypy, Django system/drift checks, Tailwind, i18n extraction/compilation, 99.42%
  branch coverage, 16 browser tests, the live identity workflow, migration graph inspection, and
  security/privacy/diff scans all passed. `accounts.0001` depends only on `auth.0012` and
  `contenttypes.0002`; no migration drift or future domain dependency exists.
- **Commits:** `203d25b`, `945bb85`, and `8c5a6d3` for IAM-001; `c9b9f6c` for IAM-001 evidence;
  `a3aefb7` for IAM-002.
- **Deviations or blockers:** Audit-event assertions remain intentionally deferred to `AUD-002` as
  locked. The next task is `IAM-003`, but it is not eligible until human approval of CP-IAM-A.
