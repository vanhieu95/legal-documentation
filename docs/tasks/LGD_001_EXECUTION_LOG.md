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

## IAM-003 — Enforce inactivity and absolute session expiry

- **Completion date:** 2026-09-02
- **Outcome:** Added authoritative database-backed session lifetime enforcement with an exact
  30-minute inactivity limit and exact 8-hour absolute limit. Protected view callbacks cannot run
  after either deadline; activity refresh is capped by the absolute deadline. Normal expiry uses a
  data-free redirect to a safe reauthentication destination, while HTMX receives an empty `401`
  with a same-origin full-page redirect header and `no-store` caching.
- **Important files changed:** `apps/accounts/{sessions,services,views}.py`, session middleware and
  account-service tests, settings, the Vietnamese session-expired template/catalog, local HTMX
  response handling, Playwright expiry tests, and `docs/operations/session-management.md`.
- **Migrations created:** None. Django's database session backend and built-in `django_session`
  migration remain authoritative.
- **Focused tests executed:** 22 frozen-time session tests passed. They cover requests immediately
  before and exactly at both deadlines, activity refresh and absolute capping, concurrent sessions,
  login rotation, logout invalidation, password-change/reset invalidation across all sessions,
  isolation from another user's sessions, pre-view denial, CSRF ordering, normal/HTMX data-free
  expiry, hostile reauthentication destinations, cookie attributes, and cleanup operations. Two
  focused Chromium expiry tests also passed.
- **Broader checks executed:** Ruff lint/format, mypy, Django system and migration-drift checks,
  deployment settings, and the full branch-coverage suite passed before the standalone commit.
- **Browser and accessibility verification:** The Vietnamese expiry page is keyboard reachable,
  reflows without horizontal scrolling, retains no browser data, and uses a validated local
  reauthentication link. The CSP-compatible local HTMX handler performs a full navigation without
  rendering protected response data.
- **Security/privacy review:** Session timestamps and authentication state remain only in the
  server-side database session. Production cookies are Secure, HttpOnly, SameSite=Lax,
  host-scoped, and HTTPS-only. Password services invalidate only the target user's sessions; no
  credentials, unsaved form data, account data, or case data are persisted client-side. A no-op
  session-expiry notification boundary is present for `AUD-002`; no audit persistence was added.
- **Commit:** `e797412` (`feat(identity): enforce server-side session expiry`).
- **Deviations or blockers:** None. Password-reset delivery and session-expiry audit records remain
  deferred exactly as specified. Expired database sessions are documented for daily
  `clearsessions` execution.

## IAM-004 — Build the responsive application shell and global error states

- **Completion date:** 2026-09-02
- **Outcome:** Delivered a Vietnamese authenticated shell with semantic header/navigation/main and
  status landmarks, skip link, product/page/account context, CSRF-protected POST logout, named-URL
  active states, permission-aware navigation, a 240px desktop sidebar, compact/tablet drawer,
  light/dark/system themes, HTMX busy presentation, persistent live regions, and purpose-built
  generic `403`, `404`, `500`, and session-expired states. Safe permission-protected placeholder
  destinations provide navigation without implementing future workflows.
- **Important files changed:** `templates/base_authenticated.html`, theme/error/placeholder
  templates, `apps/accounts/context_processors.py`, protected placeholder URLs/views in
  `apps/{cases,documents,audit}`, local CSS/JavaScript, Vietnamese messages, browser-test fixtures,
  and focused shell/frontend/Playwright tests.
- **Migrations created:** None. No case, document, template, or audit domain model was added.
- **Focused tests executed:** 16 shell tests and 80 combined accounts/frontend tests passed. The
  final pinned-Chromium suite passed all 33 tests under non-debug settings.
- **Broader checks executed:** Ruff lint/format, mypy, Django system and migration-drift checks,
  Tailwind build, message extraction/compilation, and the full coverage suite passed. The final
  ordinary suite reported 117 passed, one PostgreSQL-profile skip, and 99.44% overall branch
  coverage; that profile was then exercised separately without a skip at checkpoint closure.
- **Browser and accessibility verification:** Chromium verified Administrator and active-superuser
  login, generic non-Administrator denial, compact 375px/tablet 768px/wide 1440px reflow,
  touch-sized controls, keyboard skip navigation, drawer focus trapping/Escape/restoration,
  off-canvas inert state, visible focus, 200% zoom, no page-level horizontal scrolling,
  light/dark/system themes, reduced motion, forced colors, live busy state, local no-eval CSP,
  JavaScript-disabled navigation/login/logout, logout-session replay denial, and live generic
  `403`/`404`/`500` pages.
- **Security/privacy review:** Navigation visibility calls the central policy but every destination
  independently rechecks server permission. HTMX history and cache snapshots remain disabled.
  Browser storage remained empty except for the explicit non-sensitive `vds-theme` presentation
  preference; no account, case, protected, or form data was persisted. Scripts are local and
  CSP-compatible, logout remains POST-only and CSRF-protected, and errors disclose no internal
  identifier or exception detail.
- **Commit:** `5b8cc3a` (`feat(identity): add responsive authenticated shell`).
- **Deviations or blockers:** Chrome DevTools MCP was unavailable, so the repository's pinned real
  Playwright Chromium suite supplied runtime DOM, keyboard, viewport, storage, CSP, and error-state
  verification. No implementation blocker remains.

## CP-IAM-B — Checkpoint closure

- **Completion date:** 2026-09-02
- **Status:** Complete. Milestone 2 and `IAM-003`/`IAM-004` are complete; approved `IAM-001` and
  `IAM-002` behavior remained intact.
- **Checkpoint evidence:** All exact local gates passed: Ruff lint/format, mypy, Django system and
  migration-drift checks, Tailwind build, message extraction/compilation, 117 passing ordinary
  tests with 99.44% branch coverage, static collection, and 33 pinned-Chromium tests. A disposable
  PostgreSQL 18.6 cluster additionally ran all 74 focused accounts and migration-profile tests with
  no skip, then was stopped and removed.
- **Security/deployment evidence:** Synthetic production values passed `check --deploy`; the only
  retained warning is the already-approved `security.W004`, because HSTS rollout remains assigned
  to `SEC-002` after HTTPS validation. Session/cookie/CSRF/redirect/HTMX/storage/CSP/authorization,
  dependency direction, secrets/personal data, debug output, suppressions, migrations, and the
  final diff were reviewed without a blocking finding.
- **Commits:** `e797412` for `IAM-003`; `5b8cc3a` for `IAM-004`.
- **Deviations or blockers:** No implementation blocker. Chrome DevTools MCP and a remote CI result
  were not available; local pinned Chromium and all repository-equivalent gates passed. The next
  eligible task is `AUD-001`, which was not started.

## AUD-001 — Create the append-only audit model and recorder

- **Completion date:** 2026-09-02
- **Outcome:** Added the append-only `AuditEvent` model, stable action/outcome contract, bounded
  metadata recorder, request correlation middleware, read-only Django admin, and focused immutability
  and migration-index tests without importing business-domain models.
- **Important files changed:** `apps/audit/{actions,models,recorder,admin}.py`,
  `apps/audit/migrations/0001_initial.py`, `apps/audit/tests/`, `apps/core/{correlation,middleware}.py`,
  and `config/settings/base.py`.
- **Migrations created:** `apps/audit/migrations/0001_initial.py` with actor-marker consistency
  constraint and indexes for timestamp, action, outcome, actor, correlation ID, and target tuple.
- **Focused tests executed:** 36 audit tests passed with one PostgreSQL index-profile skip when
  `TEST_DATABASE_URL` is unset; immutability, metadata bounds, transaction commit/rollback, admin
  read-only, correlation propagation, and business-domain import absence were verified.
- **Broader checks executed:** Ruff lint/format, mypy, Django system and migration-drift checks, and
  audit-focused coverage passed before the standalone commit.
- **Security/privacy review:** Recorder rejects prohibited metadata keys, arbitrary object
  serialization, and oversized or over-nested metadata; update/delete paths raise
  `ImmutableAuditEventError`; no credentials, request bodies, or business-model foreign keys were
  introduced.
- **Commit:** `434879f` (`feat(audit): add append-only audit model and recorder`).
- **Deviations or blockers:** None.

## AUD-002 — Integrate identity and denied-access audit events

- **Completion date:** 2026-09-02
- **Outcome:** Integrated explicit identity and authorization audit recording for login success and
  failure, inactive and non-Administrator denial, logout, session expiry, password change/reset,
  account activation/deactivation, group and permission changes, and denied full-page, HTMX, and
  service-boundary access attempts.
- **Important files changed:** `apps/accounts/{audit,forms,views,sessions,services,policies}.py`,
  `apps/accounts/tests/test_audit_integration.py`, and focused session-test updates.
- **Migrations created:** None.
- **Focused tests executed:** 20 identity audit integration tests plus updated session and
  authentication suites passed; defensive assertions verified absence of submitted credentials and
  protected content anywhere in serialized audit payloads.
- **Broader checks executed:** Full repository coverage suite reported 171 passed, 2 skipped, and
  96.92% branch coverage with Ruff, mypy, Django checks, CSS build, and i18n commands passing.
- **Security/privacy review:** Failed-login audit metadata uses bounded reason codes only; user-facing
  errors remain generic; session-expiry responses remain data-free; audit rows store correlation IDs
  and route/permission metadata without usernames, passwords, tokens, or protected fragments.
- **Commit:** `e0d1c96` (`feat(audit): integrate identity and denied-access audit events`).
- **Deviations or blockers:** None.

## CP-AUD-A — Checkpoint closure

- **Completion date:** 2026-09-02
- **Status:** Local implementation and verification are complete; human approval is pending at the
  mandatory checkpoint pause. `AUD-003` has not started.
- **Completed tasks:** `AUD-001`, `AUD-002`.
- **Checkpoint evidence:** Focused audit and identity integration suites passed; Ruff lint/format,
  mypy, Django system and migration-drift checks, Tailwind build, message extraction/compilation,
  and the full coverage suite passed (`171 passed`, `96.92%` branch coverage). Manual synthetic
  exercise recorded one event each for account activation, successful login, failed login, and
  logout with correlation IDs and bounded metadata. Append-only deletion was rejected at the ORM
  layer during manual inspection.
- **Security/privacy review:** `audit` imports only Django, `core`, and `accounts`; audit browsing
  remains deferred to `AUD-003`; identity audit integration preserves IAM behavior and does not add
  signal-based duplicate events.
- **Commits:** `434879f` for `AUD-001`; `e0d1c96` for `AUD-002`.
- **Deviations or blockers:** PostgreSQL index-profile verification remains skipped unless
  `TEST_DATABASE_URL` is set. The next eligible task after approval is `AUD-003`; `CASE-001` remains
  out of scope until Milestone 3 closes.
