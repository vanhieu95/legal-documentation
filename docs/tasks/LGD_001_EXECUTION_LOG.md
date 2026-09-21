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
- **Status:** Approved and superseded by `CP-AUD-B` on 2026-09-02. `AUD-003` completed in the
  follow-on batch.
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
  `TEST_DATABASE_URL` is set. Milestone 3 is closed locally; `CASE-001` is the next eligible task.

## AUD-003 — Deliver authorized audit browsing

- **Completion date:** 2026-09-02
- **Outcome:** Authorized administrators can browse paginated, filterable audit metadata through a
  read-only full-page and HTMX fragment UI. Filters cover action, outcome, actor, target,
  correlation ID, UTC time range, sort, and page size with bounded validation. No mutation routes
  exist.
- **Important files changed:** `apps/audit/{forms,selectors,views,urls}.py`,
  `apps/audit/tests/test_views.py`, `templates/audit/{list,_audit_filters,_audit_results}.html`,
  `static_src/css/app.css`, `locale/vi/LC_MESSAGES/django.po`, and
  `apps/accounts/tests/test_shell.py` (forbidden-probe update).
- **Migrations created:** None.
- **Focused tests executed:** 23 audit view/selector tests plus 59 total audit-app tests passed;
  permission, pagination, filter/sort allowlists, HTMX `Vary`, empty/error states, query-count bound,
  and mutation rejection verified.
- **Broader checks executed:** Full repository suite reported `194 passed`, `2 skipped`, `95.34%`
  coverage with Ruff, mypy, Django checks, CSS build, i18n extraction/compilation, and synthetic
  production `check --deploy`/`collectstatic` passing (`security.W004` only).
- **Security/privacy review:** Audit list requires `accounts.view_audit`; unauthorized principals
  receive generic denial without event disclosure; metadata is escaped in templates; filter inputs
  are bounded; datetime-local filters are interpreted as UTC wall-clock instants; ordinary audit-list
  GET requests do not record audit events.
- **Commit:** `d81089f` (`feat(audit): deliver authorized audit browsing`).
- **Deviations or blockers:** None.

## CP-AUD-B — Checkpoint closure

- **Completion date:** 2026-09-02
- **Status:** Local implementation and verification complete; Milestone 3 closed.
- **Completed tasks:** `AUD-001`, `AUD-002`, `AUD-003`.
- **Checkpoint evidence:** Append-only immutability preserved; authorized browsing is paginated and
  filterable with no POST/PUT/PATCH/DELETE routes; full Q gates passed (`194 passed`, `95.34%`
  coverage, Ruff, mypy, Django drift check, CSS, i18n, deploy check).
- **Security/privacy review:** `audit` app imports only Django, `core`, and `accounts`; sensitive
  payloads never appear in browse UI; shell error-page probe updated to use a still-forbidden
  destination after audit browsing became authorized for administrators.
- **Commits:** `434879f` (`AUD-001`); `e0d1c96` (`AUD-002`); `4f765c6` (CP-AUD-A evidence);
  `d81089f` (`AUD-003`); `eb7c78b` (CP-AUD-B evidence).
- **Deviations or blockers:** PostgreSQL index-profile verification remains skipped unless
  `TEST_DATABASE_URL` is set. `CASE-001` is eligible next.

## CASE-001 — Model courts, entities, addresses, and officials

- **Completion date:** 2026-09-07
- **Outcome:** Added UUID-backed `Court`, `Entity`, `EntityAddress`, and `Official` models with
  stable court codes, kind-dependent identity/registration validation, historical addresses,
  active-state rules, protected relationships, synthetic factories, and privacy-conscious Django
  Admin configuration.
- **Important files changed:** `apps/cases/{models,forms,admin}.py`,
  `apps/cases/migrations/0001_initial.py`, `apps/cases/tests/test_reference_models.py`,
  `tests/factories.py`, and the Vietnamese catalog.
- **Migrations created:** `cases.0001_initial`, containing UUID primary keys, conditional unique
  identity/registration constraints, court hierarchy and address-date checks, protected foreign
  keys, and the reviewed court/entity/address/official indexes.
- **Focused tests executed:** 13 focused model/form/migration tests passed on PostgreSQL, covering
  Unicode preservation, boundary lengths, kind-dependent validation, direct database constraints,
  inactive relational choices, migration state, index columns, factories, and safe admin search
  fields. Empty-database migration, reversal to `cases zero`, and reapplication all passed.
- **PostgreSQL evidence:** `sqlmigrate` and live catalog inspection confirmed UUID columns,
  constraints, foreign keys, and indexes. On a 3,000-row-per-model synthetic dataset, `EXPLAIN
  (ANALYZE, BUFFERS)` used `case_court_active_name_idx`, `case_entity_kind_name_idx`,
  `case_address_history_idx`, and, under selective court/active distribution,
  `case_official_court_active_idx`; representative executions were 0.028 ms, 0.015 ms, 0.479 ms,
  and 0.044 ms respectively.
- **Security/privacy review:** Identity and registration values are absent from URLs, logs, audit
  metadata, and list/admin search fields; fixtures use explicit synthetic placeholders only. Test
  data is synthetic and Vietnamese Unicode is preserved without destructive normalization. No JSON
  business payload, signal workflow, hard deletion, or `documents` dependency was introduced.
- **Commit:** `1e243df` (`feat(cases): model reusable reference records`).
- **Deviations or blockers:** None.

## CASE-002 — Deliver reference-entity maintenance workflows

- **Completion date:** 2026-09-07
- **Outcome:** Administrators can list, search, filter, create, edit, and confirm deactivation of
  courts, entities, historical addresses, and officials through explicit transactional services.
  Ordinary requests return full pages; HTMX returns narrow fragments with swappable `422`
  validation, same-origin redirects, canonical filter URLs, and `Vary: HX-Request`. All workflows
  retain a JavaScript-disabled path.
- **Important files changed:** `apps/cases/{audit,forms,policies,selectors,services,views,urls}.py`,
  `templates/cases/references/`, reference workflow tests, local CSS/JavaScript and built assets,
  browser fixtures/tests, audit action contracts, and the Vietnamese catalog.
- **Migrations created:** None. Query-count and PostgreSQL plan evidence did not justify an
  additional CASE-002 index.
- **Focused tests executed:** 58 cases tests passed on SQLite. The final PostgreSQL profile passed
  63 tests covering all cases tests plus audit migration and database integration profiles. Tests
  exercise anonymous/inactive/non-Administrator/missing-permission/Administrator/superuser access,
  view and service permission boundaries, object-policy lookup, CSRF on every unsafe route in
  normal and HTMX modes, all-resource valid create/edit/deactivate flows, invalid value
  preservation, inactive and cross-object choices, UUID-safe not-found handling, empty/filter/error
  states, bounded pagination, and success/failure/denied audit events.
- **Broader checks executed:** Ruff lint/format, mypy, Django system and migration-drift checks,
  Tailwind build, exact asset verification, message extraction/compilation, and the full ordinary
  coverage command passed (`252 passed`, two intentional PostgreSQL-profile skips, 95.03% branch
  coverage). The complete PostgreSQL run passed `253` tests with no skips and 95.28% coverage
  before the final UI and identifier-autocomplete refinements; the final focused PostgreSQL profile
  then passed again.
- **Browser and accessibility verification:** All 39 pinned-Chromium tests passed. Reference pages
  were exercised at 375px, 768px, and 1440px with no page overflow and responsive labelled-card or
  table presentation. Runtime checks covered HTMX form loading, swappable `422` validation,
  preserved Unicode, linked and focused error summaries, fragment-heading focus, a named native
  confirmation dialog, focus restoration, local no-eval assets, and JavaScript-disabled editing.
  Screenshot inspection of compact/tablet/wide lists, the long form, and confirmation found no
  blocking reflow, clipping, hierarchy, or focus issue.
- **Authorization, CSRF, and audit evidence:** Reference view/add/change/deactivate permissions are
  checked by both views and sensitive services; posted relations are rebound to active authorized
  querysets and target objects are policy-scoped and re-fetched. Every unsafe normal/HTMX route
  rejects missing CSRF. Audit success stores target UUID and sorted changed field names only;
  validation failure stores only bounded reason/type codes; permission denial uses the existing
  domain-neutral contract. Repeated deactivation is idempotent and emits one transition event.
- **Performance evidence:** The reference list uses two bounded selector queries and preloads its
  displayed relationships; a complete authenticated rendered request is capped at 15 queries with
  no row-dependent growth. Search input is limited to 100 characters and results to 25 per page.
- **Security/privacy review:** No identity/registration value appears in list output, logs, URLs,
  errors, or audit metadata; fixtures contain synthetic placeholders only. Autocomplete is disabled
  for identity/registration controls. Sensitive browser history/cache remains disabled; error states
  disclose no exception detail; state-changing GET, `csrf_exempt`, direct POST-to-model assignment,
  signals, hard deletion, debug output, test suppression, and document-domain imports are absent.
- **Commit:** `fdb7ae9` (`feat(cases): deliver reference maintenance workflows`).
- **Deviations or blockers:** The PostgreSQL gate exposed an approved-audit test that inferred
  columns from PostgreSQL-truncated index names. Catalog evidence proved the composite index was
  present; the test now asserts introspected index columns and passes on PostgreSQL. Chrome DevTools
  MCP was unavailable, so the repository's pinned real Playwright Chromium supplied runtime DOM,
  keyboard, focus, viewport, CSP, and no-JavaScript evidence.

## CP-CASE-A — Checkpoint closure

- **Completion date:** 2026-09-07
- **Status:** Approved. Local implementation and verification completed on 2026-09-07; approval was
  confirmed before CP-CASE-B implementation began.
- **Completed tasks:** `CASE-001`, `CASE-002`.
- **Checkpoint evidence:** Reference invariants and indexes are live in a reversible sequential
  `cases.0001` migration; authorized full-page and HTMX maintenance, safe audit recording,
  confirmation-based deactivation, responsive Vietnamese presentation, and no-JavaScript fallback
  all pass. Final gates include 63 PostgreSQL profile tests, 39 Chromium tests, 95.03% ordinary
  branch coverage, and green lint, format, typing, Django, migration, CSS, asset, and i18n checks.
- **Dependency/migration review:** `cases` imports only Django, `core`, `accounts`, and `audit`; it
  imports no `documents` code. `audit` remains domain-neutral. The migration graph has one
  sequential cases leaf and migrated cleanly from empty PostgreSQL, reversed, and reapplied.
- **Commits:** `1e243df` for `CASE-001`; `fdb7ae9` for `CASE-002`.
- **Deviations or blockers:** No implementation blocker. `.codegraph/` remains an unrelated,
  pre-existing untracked directory and was not modified or committed. Approval was subsequently
  received and `CASE-003` through `CASE-005` proceeded under CP-CASE-B.

## CASE-003 — Model civil cases, acceptance rules, revisions, and archive metadata

- **Completion date:** 2026-09-08
- **Outcome:** Added UUID-backed `CaseRecord` with a unique internal reference, court and matter
  classification, finite procedural/status states, incomplete pre-acceptance support, grouped
  acceptance metadata, positive revision, creator/editor timestamps and actors, and complete
  archive metadata. Client forms exclude status, revision, actor, timestamp, and archive controls.
- **Important files changed:** `apps/cases/{models,forms,admin}.py`,
  `apps/cases/migrations/0002_add_case_record.py`,
  `apps/cases/tests/test_case_records.py`, test fixtures/factories, and the Vietnamese catalog.
- **Migration and constraints:** `cases.0002` adds acceptance-group, archive-group, positive-revision,
  finite-stage/status, and acceptance-year checks; unique/pattern indexes cover internal reference,
  with explicit court/status, status/stage, acceptance tuple, and update-time indexes. PostgreSQL
  SQL inspection confirmed UUID, `date`, and `timestamp with time zone` storage.
- **Focused tests:** The final combined PostgreSQL cases profile includes all CASE-003 tests. Its
  dedicated earlier run passed 53 tests; expanded boundary coverage subsequently passed in the
  complete profiles. Tests cover every partial acceptance combination at model and database level,
  form rejection, uniqueness, text/year/revision boundaries, actor requirements, archive
  consistency, Unicode, aware UTC timestamps, safe strings/admin fields, and live indexes.
- **Security/privacy:** Case details are excluded from `__str__`, admin list/search fields, logs,
  URLs, and audit metadata. Only synthetic values are used; actor/revision/archive fields cannot be
  submitted. No JSON, hard deletion, signal workflow, or `documents` dependency was added.
- **Commit:** `ab5abb3` (`feat(cases): model civil case records`).
- **Deviations or blockers:** Revision increment and archive transitions remain in their approved
  explicit-service tasks (`CASE-007` and `CASE-008`); this slice durably establishes their schema
  and valid states. No blocker remains.

## CASE-004 — Model participants and representation contracts

- **Completion date:** 2026-09-08
- **Outcome:** Added ordered, effective-dated `CaseParticipant` records for the eight approved core
  roles and `Representation` contracts for legal or authorized representation. Case-specific
  address, workplace, contact, authority, and description text preserves Unicode and meaningful
  line breaks independently from reusable entity data.
- **Important files changed:** `apps/cases/{models,forms,admin}.py`,
  `apps/cases/migrations/0003_add_participants_and_representations.py`,
  `apps/cases/tests/test_case_relationships.py`, factories, and the Vietnamese catalog.
- **Migration and constraints:** `cases.0003` adds finite role/type checks, non-negative ordering,
  effective-date ordering, partial unique indexes preventing duplicate active identical roles and
  representations, protected foreign keys, and case/entity/role/order/effective query indexes.
- **Forms/formsets:** Constructors own the case scope, relational choices are re-queried, inactive
  new entities and cross-case represented participants are rejected, posted case identifiers are
  ignored, and delete checkboxes perform deactivation rather than physical deletion.
- **Focused tests:** 20 direct relationship tests passed; the CASE-003/004 PostgreSQL profile passed
  64 tests. Coverage includes every approved role, ordering and multiple legitimate roles,
  duplicate rejection/history reuse, effective dates, cross-case representation, tampering,
  inactive choices, add/update/reorder/removal behavior, Unicode/multiline text, constraints, and
  live index columns.
- **Security/privacy:** Protected relations and soft lifecycle fields retain legal history. Safe
  strings/admin lists expose only opaque IDs and categorical state; tests contain synthetic data
  only and no relationship values enter audit/log metadata.
- **Commit:** `da032f3` (`feat(cases): model participants and representations`).
- **Deviations or blockers:** PostgreSQL cannot express the cross-table represented-participant case
  equality as a row check; it is enforced by model validation and a case-scoped re-queried form
  choice, with future writes reserved for the explicit `CASE-011` service. No blocker remains.

## CASE-005 — Model assignments and hearings

- **Completion date:** 2026-09-08
- **Outcome:** Added ordered, effective-dated `CaseOfficialAssignment` records for judge,
  presiding-judge, clerk, and prosecutor roles, plus timezone-aware `Hearing` records with
  first-instance/appellate levels, lifecycle status, location, and creation/update timestamps.
  Reusable selectors return current assignments and upcoming scheduled hearings.
- **Important files changed:** `apps/cases/{models,forms,selectors,admin}.py`,
  `apps/cases/migrations/0004_add_assignments_and_hearings.py`,
  `apps/cases/tests/test_case_schedule.py`, factories, and the Vietnamese catalog.
- **Migration and constraints:** `cases.0004` adds finite role/instance/status checks,
  non-negative assignment ordering, effective-date ordering, active-assignment partial uniqueness,
  and composite indexes for case/role/order, official/role, current effective assignments, and
  case/status/scheduled hearing queries. PostgreSQL uses `timestamp with time zone` for hearings.
- **Forms/formsets/selectors:** Official choices are active and same-court scoped; posted case and
  official tampering is rejected. Assignment removal deactivates history and hearing removal marks
  it cancelled. Selectors distinguish current/historical assignments and upcoming/past hearings.
- **Focused tests:** 18 direct schedule tests passed; the combined CASE-003/004/005 PostgreSQL
  profile passed 82 tests, and the final complete cases PostgreSQL profile passed 140. Tests cover
  all approved roles, invalid roles/order/date ranges, inactive/cross-court officials, tampering,
  current/history queries, hearing choices, aware input, UTC persistence, Ho Chi Minh presentation,
  Unicode location, formsets, constraints, and live indexes.
- **Manual verification:** A synthetic `2026-09-08 08:30` Asia/Ho_Chi_Minh hearing rendered as
  `08:30 ngày 08/09/2026 +07`; persisted values were verified as UTC-aware.
- **Security/privacy:** No detailed minutes, template-specific roles, sensitive string rendering,
  hard deletion, JSON payload, logging, or document import was introduced. Admin lists use opaque
  identifiers and bounded categorical/schedule metadata.
- **Commits:** `8e85d7b` (`feat(cases): model assignments and hearings`); `360ee39`
  (`fix(cases): localize relationship form labels`).
- **Deviations or blockers:** Same-court membership is a cross-table invariant and therefore is
  enforced by model validation and case-scoped form re-querying rather than a PostgreSQL row check.
  No blocker remains.

## CP-CASE-B — Checkpoint closure

- **Completion date:** 2026-09-08
- **Status:** Local implementation and verification complete; `CASE-003`, `CASE-004`, and
  `CASE-005` are complete. Work stopped before `CASE-006`.
- **Checkpoint evidence:** Exact Ruff lint/format, mypy, Django system check, and migration-drift
  commands passed. The full ordinary coverage command passed `333` tests with two intentional
  PostgreSQL-profile skips and 95.64% branch coverage. The separate PostgreSQL 18.6 profile passed
  all 140 cases/integration tests with no skip. Vietnamese messages extracted and compiled with no
  fuzzy or untranslated application entry.
- **PostgreSQL verification:** A database at the committed CP-CASE-A `cases.0001` schema upgraded
  linearly through `0002`, `0003`, and `0004`. A second empty UTF-8 PostgreSQL database applied all
  project migrations through `cases.0004`. Reviewed SQL contains the expected UUIDs, protected
  foreign keys, check/partial-unique constraints, query indexes, dates, and aware timestamps;
  direct database tests rejected every expressible invalid state.
- **Security/privacy review:** Relational IDs are constructor-scoped and re-queried; cross-case and
  cross-court links are rejected; lifecycle/actor metadata is excluded from submitted fields;
  removals preserve history. Searches found no `cases` import of `documents`, JSON business field,
  signal workflow, hard-delete path, sensitive logging, secrets, real personal/legal data, debug
  output, new skipped tests, or weakening suppressions. Admin and string representations avoid
  unnecessary personal/legal values, and Unicode spelling is preserved without normalization.
- **Commits:** `ab5abb3` (`CASE-003`); `da032f3` (`CASE-004`); `8e85d7b` (`CASE-005`);
  `360ee39` (localized relationship form labels).
- **Deviations or blockers:** Cross-row case/court equality cannot be represented by ordinary
  PostgreSQL check constraints and is enforced at model/form boundaries pending the authorized
  transactional workflow in `CASE-011`. Service-owned revision/archive transitions remain in
  `CASE-007`/`CASE-008`. No CP-CASE-B blocker remains. `.codegraph/` is a pre-existing unrelated
  untracked directory and was not modified or committed. The next eligible tasks are `CASE-006`
  and `CASE-007` under `CP-CASE-C`; neither was started.

## CASE-006 — Deliver case creation and overview detail

- **Completion date:** 2026-09-08
- **Outcome:** Administrators can create incomplete pre-acceptance or fully accepted civil-matter
  cases at the named `/cases/new/` route and view a purpose-built overview at the canonical UUID
  detail route. Normal submissions use full pages and canonical redirects; HTMX submissions use a
  narrow `204` redirect or swappable `422` form fragment with preserved values, linked errors,
  focused summary, and `Vary: HX-Request`. The overview safely summarizes prefetched relationship
  counts without exposing relationship editing.
- **Important files changed:** `apps/cases/{audit,policies,selectors,services,views,urls}.py`,
  `apps/cases/tests/test_case_workflows.py`, `templates/cases/`, local CSS/JavaScript and built
  assets, Playwright configuration and smoke tests, audit action contracts, and the Vietnamese
  catalog.
- **Migrations created:** None. Existing `cases.0002` PostgreSQL acceptance and revision
  constraints remain the durable invariant layer; migration drift reported no changes.
- **Focused tests executed:** The creation/detail module passed 37 tests and the complete cases
  suite passed 176 tests after CASE-006. Coverage includes every partial acceptance group, model
  and database validation, server-owned revision/actors/timestamps, posted metadata tampering,
  active court re-querying, full/HTMX success and invalid behavior, CSRF, the complete principal
  and permission matrix, generic UUID failures, Unicode, bounded audit outcomes, and a fixed
  five-query overview relationship load.
- **Browser and accessibility verification:** The complete pinned-Chromium suite passed 45 tests.
  Live create/detail checks covered 375px, 768px, and 1440px layouts, no page-level overflow,
  visible keyboard focus, focused linked `422` summaries, 200% zoom/reflow, Vietnamese labels and
  Unicode, JavaScript-disabled creation/detail, local assets, and absence of case data from browser
  storage or HTMX history.
- **Authorization, CSRF, audit, and privacy:** Add/view permissions are enforced at views, add is
  rechecked by the atomic service, detail objects are policy-scoped, and court identifiers are
  rebound through active choices. Every unsafe normal/HTMX request retains Django CSRF protection.
  Creation audit rows contain only action/outcome, case UUID, correlation ID, and a bounded failure
  reason; no form values or case content are recorded.
- **Commit:** `ed36d6a` (`feat(cases): deliver case creation and overview`).
- **Deviations or blockers:** Chrome DevTools MCP was unavailable, so the repository's pinned real
  Playwright Chromium provided DOM, keyboard, focus, responsive, zoom, HTMX, storage, and no-script
  evidence. Environment port 8000 was occupied; Playwright gained an opt-in port setting and ran
  on isolated port 8010. No implementation blocker remains.

## CASE-007 — Deliver optimistic case editing and conflict recovery

- **Completion date:** 2026-09-08
- **Outcome:** Administrators edit cases through the named UUID edit route. The explicit service
  revalidates the form and object permission, then performs one conditional PostgreSQL update on
  the submitted expected revision. A success increments the server-owned revision exactly once
  and updates the server-owned editor/time; a stale request returns a full-page or swappable HTMX
  `409`, preserves submitted values, and offers Vietnamese reload/compare guidance without
  overwriting the winner.
- **Important files changed:** `apps/cases/{forms,audit,services,views,urls}.py`,
  `apps/cases/tests/test_case_editing.py`, shared case templates, local JavaScript and built asset,
  browser smoke tests, and the Vietnamese catalog.
- **Migrations created:** None. The compare-and-swap uses the existing positive revision column and
  database constraints.
- **Focused tests executed:** The edit module passed 16 tests on the lightweight profile with one
  explicit PostgreSQL-only skip, then all 17 tests on PostgreSQL. The complete cases suite passed
  192 tests with the PostgreSQL concurrency test skipped only on SQLite. Tests cover successful
  edit and one increment, editor/time ownership, invalid preservation and `422`, two stale clients,
  repeated conflict, normal/HTMX `409`, expected-revision and actor/archive tampering, full access
  matrix, direct-service denial, CSRF, guessed UUID, Unicode, `Vary`, and safe success/conflict/
  validation/denial audits.
- **PostgreSQL concurrency evidence:** Two genuine concurrent connections submitted different
  values against revision 1. Exactly one conditional update succeeded, the other raised the
  conflict outcome, durable revision became 2, and the winning database value remained intact.
  The complete CASE-007 PostgreSQL module passed 17/17.
- **Browser and accessibility verification:** The complete pinned-Chromium suite passed 47 tests.
  Two tabs loaded revision 1; the first keyboard submission succeeded and the second received a
  focused HTMX conflict summary with its input retained, then reload displayed the first tab's
  value at revision 2. A JavaScript-disabled two-tab flow returned a real full-page `409` and kept
  the stale submitted value. Compact and wide layouts, 200% zoom/reflow, visible focus, Vietnamese
  guidance, and no horizontal overflow passed.
- **Authorization, CSRF, audit, and privacy:** Change permission is required independently by view
  and service, objects are policy-scoped, and posted related values are rebound. Submitted revision
  is comparison-only; creator, editor, timestamp, archive fields, and arbitrary next revision are
  ignored. Audits contain target UUID, outcome, correlation ID, safe changed field names, or a
  bounded reason code only—never changed values or payloads.
- **Commits:** `82bc070` (`feat(cases): add optimistic case editing`); `c69aece`
  (`fix(cases): stabilize checkpoint verification`).
- **Deviations or blockers:** The full default coverage run exposed transactional test isolation
  after Django flush; the test fixture now idempotently seeds the approved permission group and the
  entire gate passes. No product behavior or approved feature commit was amended. No blocker
  remains.

## CP-CASE-C — Checkpoint closure

- **Completion date:** 2026-09-08
- **Status:** Local implementation and verification complete; `CASE-006` and `CASE-007` are
  complete. Work stopped before `CASE-008`.
- **Checkpoint evidence:** Ruff lint and format, mypy, Django system and migration-drift checks,
  Tailwind build, message extraction/compilation, exact frontend asset verification, and sensitive
  coverage passed. The mandated full ordinary coverage command passed 386 tests with three
  intentional PostgreSQL-profile skips at 95.68% branch coverage. The complete PostgreSQL 18.6
  run passed all 389 tests plus two parameter subtests with no skips. The complete live Chromium
  suite passed 47 tests.
- **PostgreSQL and migration verification:** A disposable UTF-8 PostgreSQL database applied all
  migrations from zero through `cases.0004`; a second migrate reported no migrations to apply.
  The full PostgreSQL suite exercised constraints and the concurrent compare-and-swap. No schema
  change or migration drift exists in CP-CASE-C.
- **HTTP, authorization, and audit verification:** Normal/HTMX create, detail, edit, invalid `422`,
  and stale `409` paths passed, as did anonymous, inactive, non-Administrator, missing-permission,
  Administrator, superuser, direct-service denial, CSRF, and generic object-failure checks. Audit
  success/failure/conflict/denial metadata remains bounded and content-free.
- **Performance, accessibility, and privacy review:** Overview relationship reads are fixed at five
  queries with no row-dependent N+1 behavior; edit reads are bounded. Browser checks cover
  compact/tablet/wide rendering, keyboard and visible focus, error/conflict focus, 200% zoom,
  reflow, HTMX and JavaScript-disabled workflows, and sensitive-history/storage protections.
  Searches found no `cases` import of `documents`, case values in logs/audits/query strings/browser
  storage, secrets, real personal/legal data, debug output, weakened assertions, archive/restore,
  relationship editing, or document functionality.
- **Commits:** `ed36d6a` (`CASE-006`); `82bc070` (`CASE-007`); `c69aece` (verification isolation and
  catalog refresh). Checkpoint record commit follows this entry.
- **Deviations or blockers:** Chrome DevTools MCP was unavailable; pinned Playwright Chromium was
  used as the real-browser fallback. The optional production deployment check passed with only the
  existing `security.W004` HSTS warning intentionally deferred to `SEC-002`; static collection
  copied 133 files. `.codegraph/` remains a pre-existing unrelated untracked directory and was not
  modified or committed. No CP-CASE-C blocker remains. The next eligible tasks are `CASE-008` and
  `CASE-009` under `CP-CASE-D`; neither was started.

## CASE-008 — Deliver confirmed archive and restore

- **Completion date:** 2026-09-08
- **Outcome:** Added stable archive and restore routes with safe full-page and HTMX confirmation
  flows. Explicit services perform atomic status/revision compare-and-swap transitions, own actor
  and timestamps, increment revision exactly once, and preserve the existing model's current-state
  archive metadata contract. Archived cases remain readable, become immutable, and fail the stable
  document-generation eligibility predicate until restored; no hard-delete route or service exists.
- **Important files changed:** `apps/cases/{forms,policies,services,views,urls,audit}.py`,
  `apps/audit/actions.py`, archive/restore templates, local source/built JavaScript, Vietnamese
  messages, `apps/cases/tests/test_case_archive.py`, and Playwright smoke coverage.
- **Migrations and indexes:** None. CASE-008 uses the existing `CaseRecord` status, archive
  metadata, revision, and update columns and creates no schema drift.
- **Focused tests:** The PostgreSQL archive module passed 34 tests. Coverage includes success,
  exact revision increments, server actor/time, bounded Vietnamese reasons, restore metadata,
  repeated and stale requests, genuine concurrent archive and restore races, archived detail/edit
  behavior, restored editing, the future-generation predicate, the complete principal/permission
  matrix, direct-service denial, normal/HTMX CSRF, generic inaccessible UUIDs, safe audit metadata,
  and absence of hard deletion.
- **PostgreSQL concurrency:** For both archive and restore, two independent connections submitted
  the same expected revision. Exactly one transition succeeded, exactly one returned the conflict
  outcome, and the durable status changed with one revision increment and no overwrite.
- **Authorization, CSRF, and audit:** Separate archive/restore permissions are enforced by both
  view decorators and service decorators; objects are policy-scoped before transition. Mutations
  are POST-only and Django CSRF protection rejects normal and HTMX requests without a token.
  Success, conflict, validation, and denied outcomes are bounded to action/outcome, case UUID,
  actor, correlation ID, changed field names, reason code, and reason-presence boolean. Archive
  reason text and case content never enter audit metadata.
- **Browser and accessibility:** Pinned Playwright Chromium verified dialog initial focus, explicit
  focus trapping, cancel, Escape, trigger-focus restoration, HTMX completion, and no horizontal
  overflow at 375px, 768px, and 1440px. A JavaScript-disabled archive-and-restore flow completed
  through full pages. The final complete browser suite passed 51 tests.
- **Security/privacy review:** UUID knowledge does not grant access; stale or repeated transitions
  return safe conflicts and never overwrite newer state. Confirmation truth and permission checks
  remain server-side. No protected payload is stored in browser storage or HTMX history, and no
  document dependency or actual generation behavior was introduced.
- **Commit:** `21e0844` (`feat(cases): add archive and restore workflows`). Accessibility matrix
  coverage was finalized in `180db82` (`test(cases): verify archive dialog across viewports`).
- **Deviations or blockers:** The model's approved constraint defines archive columns as current
  state: restoration clears those columns, while the bounded audit stream retains the historical
  transition. Chrome DevTools MCP was unavailable, so the repository's pinned real Chromium
  runner supplied browser-runtime evidence. No implementation blocker remains.

## CASE-009 — Build indexed case search, filter, sort, and pagination selectors

- **Completion date:** 2026-09-08
- **Outcome:** Added a bounded query form and read-only, permission/object-policy-scoped selector.
  Search covers internal reference, acceptance number/year/type, matter type, court name/code,
  participant names, and representative-entity names. Identifiers use exact-compatible prefix
  matching; Vietnamese names and matter text use PostgreSQL case-insensitive containment without
  stripping or altering diacritics. Relational joins are duplicate-free.
- **Filters, sorting, and pagination:** Court, status, procedural stage, acceptance type/year,
  inclusive acceptance-date bounds, and archive state are explicit validated filters. Updated,
  created, acceptance date/number, court, and matter type support allowlisted ascending/descending
  forms with UUID tie-breaking. Page sizes are restricted to 10/25/50/100 with 25 as default;
  malformed, negative, excessive, reversed-range, arbitrary ORM, and traversal inputs are rejected.
- **Important files changed:** `apps/cases/{forms,selectors}.py`,
  `apps/cases/tests/test_case_search.py`, `docs/operations/CASE_009_QUERY_PLANS.md`,
  `pyproject.toml`, and the Vietnamese catalog.
- **Migrations and indexes:** None. PostgreSQL evidence selected the existing
  `case_record_state_stage_idx`; the measured cross-table Unicode containment OR cannot be served
  as a whole by an ordinary B-tree. At the measured target it did not justify a PostgreSQL trigram
  extension, changed semantics, or added write/storage cost.
- **Focused tests:** PostgreSQL passed all 50 active search tests with one intentionally disabled
  100,000-row profile; the explicit scale invocation separately passed. Tests cover every field,
  filter, combination, inclusive boundary, sort direction, malicious sort/traversal, bounded query,
  page/page-size contract, duplicate removal, stable tied pagination, policy scoping, archive state,
  fixed query counts, no N+1, inspectable plans, and absence of read-only audit events.
- **Query count and plan evidence:** The complete selector boundary is capped at seven queries:
  three uncached central authorization checks, count, page fetch, and two bounded prefetches.
  Reading court, participant-entity, and representative-entity data adds no queries. On 100,000
  synthetic cases, `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` returned 999 matches in 207.595 ms,
  used `case_record_state_stage_idx`, hit 2,210 shared buffers with no shared reads, and performed
  the deterministic sort in memory. Full evidence and trade-offs are recorded in the operations
  note.
- **Security/privacy review:** The selector requires `view_cases` before applying the object policy;
  inputs can reach only fixed ORM expressions and no raw SQL is used. Ordinary discovery emits no
  audit event and logs no query/results. All fixtures are explicitly synthetic; URLs are not built
  in this selector-only task. The `cases` app imports no `documents` code.
- **Commits:** `668b51e` (`feat(cases): add indexed case discovery selectors`); `c609475`
  (`test(cases): isolate PostgreSQL Unicode casefold checks`).
- **Deviations or blockers:** SQLite's `icontains` does not provide production-equivalent
  Vietnamese Unicode case folding. Those exact assertions run on PostgreSQL; ASCII correctness
  remains in the ordinary profile. This incompatibility and the no-new-index decision are
  documented. Target hardware load testing remains deferred to the approved performance phase;
  the 100,000-case architecture profile passes locally.

## CP-CASE-D — Checkpoint closure

- **Completion date:** 2026-09-08
- **Status:** Local implementation and verification complete; `CASE-008` and `CASE-009` are
  complete. Work stopped before `CASE-010`.
- **Checkpoint evidence:** Ruff lint/format, mypy, Django system and migration-drift checks,
  Tailwind build, message extraction/compilation, frontend asset verification, and diff checks all
  passed. The mandated ordinary coverage command passed 464 tests with ten intentional
  PostgreSQL/performance-profile skips at 95.06% branch coverage. The complete PostgreSQL 18.6
  profile passed 473 tests, one explicit scale-profile skip, and two parameter subtests. The final
  pinned-Chromium suite passed 51 tests.
- **PostgreSQL and migration verification:** `cp_case_d_empty` applied all 24 migrations from an
  empty database through `cases.0004`; the existing partially migrated `cp_case_b` database
  upgraded successfully and both reported zero unapplied migrations. The loader reported no
  conflicts and one linear cases leaf, `0004_add_assignments_and_hearings`. Concurrent archive and
  restore tests passed on separate PostgreSQL connections. No CP-CASE-D migration was needed.
- **Functional verification:** Archive/restore service/view authorization, normal/HTMX CSRF,
  immutable archived edits, readable archived details, restored edits, revision conflicts, safe
  audits, all required search fields and filters, every allowlisted sort direction and page size,
  malicious input rejection, duplicate elimination, deterministic pagination, fixed relation
  query counts, and no read-only audit spam all pass. Existing identity, audit, reference, create,
  detail, and edit suites remain green.
- **Security, privacy, and dependency review:** No hard deletion, unsafe state-changing GET, raw SQL
  interpolation, client-owned permission truth, submitted actor/timestamp/archive metadata,
  diacritic normalization, case-value audit/logging, protected browser storage, secrets, real
  personal/legal data, debug output, weakened assertions, or new suppression exists. All new data
  is synthetic. The `cases` dependency direction remains `core`/`accounts`/`audit` only and has no
  `documents` import.
- **Commits:** `21e0844` (`CASE-008`); `668b51e` (`CASE-009`); `c609475` (SQLite/PostgreSQL test
  profile correction); `180db82` (three-viewport archive accessibility coverage). Checkpoint
  record commit follows this entry.
- **Deviations or blockers:** Chrome DevTools MCP was unavailable; pinned Playwright Chromium was
  used as the real-browser fallback. SQLite Unicode case folding is not accepted as production
  evidence and is explicitly isolated/documented. `.codegraph/` remains a pre-existing unrelated
  untracked directory and was not modified or committed. No CP-CASE-D blocker remains. The next
  eligible tasks are `CASE-010` and `CASE-011` under `CP-CASE-E`; neither was started.

## CASE-010 — Deliver the responsive canonical case list with HTMX

- **Completion date:** 2026-09-09
- **Outcome:** The stable named `/cases/` route now renders the complete canonical list page for
  ordinary requests and the narrow results fragment for HTMX, with `Vary: HX-Request`. The URL is
  the source of truth for search, all approved filters, allowlisted sort direction, page size,
  pagination, and individual/all clearing. The view delegates validation and data retrieval to the
  CASE-009 query form and policy-scoped selector rather than duplicating query logic.
- **Important files changed:** Case list view/URL context, full and fragment templates, responsive
  styles, HTMX response/focus handling, Vietnamese catalog, focused view/frontend tests, and live
  Chromium workflows.
- **Migrations:** None; no index was added because CASE-009's PostgreSQL plan evidence and existing
  indexes remain the approved contract.
- **Verification:** Focused list, selector, authorization, locale, query-state, HTMX, and frontend
  tests passed. Full-page and HTMX results are behaviorally consistent; the baseline GET form and
  links work without JavaScript. Chromium verified debounce/synchronization, loading/busy state,
  reload/deep links/back/forward, keyboard operation and focus, compact/tablet/wide rendering,
  200% zoom/reflow, empty/error/forbidden states, and no page-level horizontal overflow.
- **Performance, authorization, and privacy:** The complete list view remains fixed at 18 queries
  for 25 rows and the CASE-009 selector boundary remains capped at seven, with no N+1. View
  permission and object policy are enforced, routine GETs emit no audit event, and the query
  contract excludes identity values, addresses, and relationship payloads. HTMX history snapshots
  are disabled and no filter state is stored in browser storage.
- **Commit:** `8c1c1e6` (`feat(cases): deliver canonical responsive case list`).
- **Deviations or blockers:** Chrome DevTools MCP was unavailable, so the repository's pinned real
  Chromium runner supplied browser-runtime evidence. No implementation blocker remains.

## CASE-011 — Deliver case relationships and sectioned detail editing

- **Completion date:** 2026-09-09
- **Outcome:** Case detail now exposes server-addressable overview, participants, representatives,
  officials/assignments, and hearings through canonical section query state. Ordinary requests get
  full-page fallbacks; HTMX gets a narrow section fragment with `Vary: HX-Request`. Accessible
  formsets support stable rows, ordering, progressive add/remove, linked error summaries, success
  announcements, and preserved validation/conflict submissions.
- **Relationship services:** Explicit participant, representation, assignment, hearing, and
  combined services recheck change permission and object policy, lock and compare the server case
  revision, re-query active case-scoped posted UUIDs, reject cross-case/inactive choices, preserve
  removal history, and commit all selected formsets atomically. Any invalid formset or stale
  revision writes nothing and does not increment revision; successful combined updates increment
  it once and record editor/time.
- **Important files changed:** `apps/cases/{forms,selectors,services,views,urls,audit}.py`, the audit
  action allowlist, case section/relationship templates, responsive styles and formset JavaScript,
  Vietnamese catalog, browser seed script, and focused service/view/section/frontend/browser tests.
- **Migrations:** None.
- **Focused and PostgreSQL evidence:** The final focused relationship/section/frontend run passed
  49 tests with one expected SQLite skip. The genuine two-connection PostgreSQL stale-revision race
  passed. The complete ICU-collated PostgreSQL cases profile passed 330 tests with only the explicit
  opt-in 100,000-row scale fixture skipped. An empty PostgreSQL 18.6 database applied all 24
  migrations; a database staged at `cases.0002` upgraded through the current graph successfully.
- **HTTP, authorization, CSRF, and audit:** Full-page and HTMX section/editor responses, `422`
  validation fragments, `409` conflicts, session-expired recovery, ordinary no-JavaScript
  submission, anonymous/inactive/non-Administrator/missing-permission/Administrator/superuser
  behavior, archived denial, direct-service denial, all unsafe normal/HTMX CSRF checks, management
  tampering, and cross-case injection passed. GETs produce no audit event; mutation audits contain
  bounded relationship categories/field names and never personal values.
- **Performance and accessibility:** Overview relationship reads remain fixed at five selector
  queries. Participant editor rendering uses the same query count for zero and 12 rows and stays
  within five queries, preventing N+1. Chromium verified keyboard section navigation and row
  controls, focus restoration, error/conflict/success announcements, long Vietnamese labels,
  compact/tablet/wide layouts, 200% zoom/reflow, no unintended page scroll, and no-JavaScript
  navigation/submission.
- **Commit:** `03c9336` (`feat(cases): deliver sectioned relationship editing`).
- **Deviations or blockers:** Chrome DevTools MCP was unavailable; pinned Playwright Chromium was
  used as the real-browser fallback. No implementation blocker remains.

## CP-CASE-E — Checkpoint closure

- **Completion date:** 2026-09-09
- **Status:** Local implementation and verification complete; `CASE-010` and `CASE-011` are
  complete. Work stopped before `CASE-012`.
- **Checkpoint evidence:** Ruff lint/format, mypy, Django system and migration-drift checks,
  Tailwind build, message extraction/compilation, frontend asset verification, sensitive-module
  coverage, and diff checks passed. The mandated ordinary coverage command passed 516 tests with
  11 intentional PostgreSQL-profile skips at 95.15% branch coverage. The complete ICU PostgreSQL
  cases profile passed 330 tests with one opt-in scale skip. The complete pinned-Chromium suite
  passed all 61 tests.
- **Functional and transaction verification:** Canonical list and section state survive ordinary
  navigation and enhanced swaps; full-page, HTMX, and no-JavaScript paths agree. `422` and `409`
  targets swap correctly. Multi-formset invalid submissions and stale revisions roll back every
  related write, while successful submissions commit once. Existing identity, audit, reference,
  case model, creation, editing, archive/restore, selector, permission, and CSRF suites remain
  green.
- **Security, privacy, and dependency review:** Both view and write-service boundaries enforce
  permission and object policy; related UUIDs are re-queried and case-scoped; archived cases cannot
  use relationship mutations. No unsafe GET, read-audit spam, hard deletion, raw query error,
  browser-owned authorization/validation/revision truth, sensitive URL/storage/log/audit content,
  real personal/legal fixture data, secret, debug output, weakened assertion, unrelated cleanup,
  or new index exists. The `cases` app imports no `documents` code.
- **Commits:** `8c1c1e6` (`CASE-010`); `03c9336` (`CASE-011`). Checkpoint record commit follows this
  entry.
- **Deviations or blockers:** The host provides only a C locale, so the complete PostgreSQL cases
  verification used a disposable ICU `vi` database to exercise production-equivalent Vietnamese
  case folding. Chrome DevTools MCP was unavailable and pinned Chromium supplied the required
  browser evidence. `.codegraph/` remains a pre-existing unrelated untracked directory and was not
  modified or committed. No CP-CASE-E blocker remains. The next eligible task is `CASE-012` under
  `CP-CASE-F`; it was not started.

## CASE-012 — Add case activity selectors for the dashboard

- **Completion date:** 2026-09-10
- **Outcome:** Replaced the dashboard placeholder with permission- and object-policy-scoped active
  and archived totals plus five deterministic recent case activities. Cards link through the exact
  CASE-010 `archive_state=active|archived` contract; recent items expose only safe reference,
  status/category, localized activity time, and authorized named detail URLs. Document areas remain
  explicitly unavailable and contain no invented counts or document business code.
- **Important files changed:** `apps/cases/{selectors.py,tests/test_dashboard.py}`,
  `apps/accounts/views.py`, dashboard full/fragment templates, responsive CSS, HTMX loading/error
  handling, Vietnamese catalog, browser tests, and
  `docs/operations/CASE_012_QUERY_PLANS.md`.
- **Migrations and indexes:** None. PostgreSQL plan evidence confirmed that the existing
  `case_record_updated_idx` serves bounded recent activity; the exact two-status aggregate is
  appropriately a single scan and did not justify another index.
- **Focused tests:** The final dashboard/shell/frontend run passed 37 tests with one expected
  SQLite-only PostgreSQL-plan skip. The focused PostgreSQL dashboard profile passed all 15 tests.
  Tests cover mixed/empty totals, limit and deterministic order, object-policy scope, every
  principal/permission state, exact canonical links and reproduced list state, authorized detail
  URLs, full/fragment responses and `Vary`, loading/empty/error/unavailable states, no GET audit,
  privacy, Vietnamese rendering, and fixed query counts.
- **Query count and plan evidence:** The selector boundary executes exactly two case-data queries
  and at most six queries including uncached authorization. The complete dashboard request is
  capped at 16 including session, shell, and repeated deny-by-default permission checks; rendering
  more source rows adds no queries. On 10,000 synthetic PostgreSQL 18 cases, recent activity used a
  backward scan of `case_record_updated_idx`, examined six rows, returned five, used 12 shared
  buffer hits and 25 kB peak sort memory, and completed in 0.111 ms. The aggregate used 213 shared
  buffer hits and completed in 1.775 ms.
- **Authorization, audit, and privacy:** Anonymous and inactive principals redirect to login;
  non-Administrators and Administrators missing `view_cases` receive the generic denial;
  Administrators and superusers succeed. Both selectors independently enforce the central
  permission before applying the object policy. Allowed GETs create no audit event. HTML, query
  strings, errors, browser storage, and HTMX history exclude addresses, identity/participant data,
  matter text, archive reasons, and legal content.
- **Browser and accessibility:** Pinned Chromium passed seven focused dashboard tests and all 68
  repository browser tests. Evidence covers semantic headings/regions, accessible card count
  names, keyboard focus, compact/tablet/wide reflow, 200% zoom through the shared shell, no page
  overflow, Vietnamese text, loading and error announcements, live HTMX refresh, ordinary links
  without JavaScript, and absence of case state in browser storage/history snapshots.
- **Commit:** `a0aad5f` (`feat(cases): add policy-scoped dashboard activity`).
- **Deviations or blockers:** Chrome DevTools MCP was unavailable, so the repository's pinned real
  Chromium runner supplied runtime evidence. The production deployment check retains the existing
  HSTS warning because HSTS requires deployment-domain rollout decisions; production settings were
  not weakened. No CASE-012 blocker remains.

## CP-CASE-F and Milestone 4 — Checkpoint closure

- **Completion date:** 2026-09-10
- **Status:** Local CP-CASE-F and Milestone 4 verification are complete. `CASE-001` through
  `CASE-012` and the `AC-05` through `AC-07` outcome gate pass; work stopped before `DOC-001`.
- **Quality suite:** Ruff lint and format, mypy over `apps config`, Django system and migration
  drift checks, Tailwind build, message extraction/compilation, frontend asset verification,
  production deploy check, collectstatic, and diff checks passed. The required ordinary coverage
  command passed 530 tests with 12 environment-profile skips at 95.18% branch coverage. The full
  PostgreSQL cases profile passed 345 tests with only the non-required opt-in 100,000-row CASE-009
  scale fixture skipped. The complete pinned-Chromium suite passed all 68 tests. Collectstatic
  copied 133 files to an isolated synthetic production root.
- **PostgreSQL and migrations:** PostgreSQL 18 applied all 24 migrations to an empty database. A
  second database staged at `cases.0002` upgraded through `cases.0004` and the complete current
  graph; both reported no unapplied migrations. The current model graph has no drift and CASE-012
  adds no migration. PostgreSQL Unicode, transaction, and genuine independent-connection conflict
  profiles passed.
- **AC-05 — Case lifecycle:** HTTP/service and browser evidence creates, views, edits, and maintains
  participants, representatives, official assignments, and hearings; archive and restore preserve
  the approved revision rules. Invalid full-page and HTMX submissions preserve entered Unicode
  values and expose linked error summaries. Relational writes are atomic, case-scoped, and reject
  cross-case identifiers; archived cases remain readable and immutable until restored.
- **AC-06 — Discovery and URL state:** Search, every approved filter, both directions of every
  allowlisted sort, deterministic pagination, bounded page sizes, individual/all clearing, reload,
  back/forward, and direct-link reproduction pass. The canonical query string is the sole state
  source. Full-page, narrow HTMX, and JavaScript-disabled results agree; dashboard cards reproduce
  the intended active and archived result sets without unnecessary or sensitive parameters.
- **AC-07 — Optimistic concurrency:** PostgreSQL independent-connection tests prove two actors can
  submit the same revision and exactly one compare-and-swap update succeeds. The stale update
  returns conflict and cannot overwrite the winner. Independent-browser-client tests pass both
  enhanced `409` fragment recovery and full-page no-JavaScript conflict recovery; the same rules
  also protect archive/restore and relationship mutations.
- **Cross-cutting security and correctness:** View and sensitive service boundaries enforce
  permissions and object policy. Every unsafe normal and HTMX route retains CSRF rejection;
  inaccessible UUIDs remain generic. Mutation audits are bounded and ordinary reads do not audit.
  Server-owned actor/time/revision/archive truth, UTC storage with Ho Chi Minh City presentation,
  Vietnamese Unicode, atomic relational writes, fixed query budgets, and no N+1 behavior pass.
  PostgreSQL plans support the approved case-search and dashboard activity shapes.
- **Privacy and dependency review:** All fixtures and plan data are explicitly synthetic. No real
  personal/legal data, secret, sensitive URL/storage/log/audit value, document statistic,
  placeholder document record, new suppression, or unrelated cleanup was introduced. `cases`
  imports no `documents` code, and no document-platform implementation has started.
- **Commits:** `a0aad5f` (`CASE-012`); checkpoint record commit follows this entry.
- **Deviations or blockers:** Chrome DevTools MCP was unavailable and pinned Chromium supplied the
  browser evidence. The deploy check passed with the pre-existing HSTS warning; enabling HSTS is a
  deployment-level decision and settings were not weakened. The explicit CASE-009 100,000-row
  design-target plan remains evidenced by its approved checkpoint and was not rerun; CASE-012's
  new 10,000-row PostgreSQL plan was measured in this checkpoint. No M4 blocker remains. The next
  eligible task is `DOC-001`, which was not started.

## DOC-001 — Define the stable registry and synthetic test document type

- **Completion date:** 2026-09-12
- **Outcome:** Added a frozen, typed, code-owned registry contract for stable keys, official and
  localized names, enabled/schema state, Django form and formset providers, context and filename
  providers, required/optional placeholders with value kinds, filter/global allowlists, synthetic
  fixture providers, and explicitly named post-processors. The only entry is
  `synthetic-platform-test`; it is marked non-production and cannot count toward MVP VDS coverage.
- **Contract enforcement:** Construction rejects malformed or duplicate keys/codes, mutable or
  incomplete contracts, missing/invalid providers, invalid fixtures or formsets, mapper name/kind
  mismatches, unsafe filenames, and undeclared/non-callable post-processors. No mapping loader,
  runtime registration, import resolver, or expression evaluator exists. Lookup explicitly conveys
  neither authorization nor active-template availability.
- **Architecture and privacy:** Automated import guards prove that `cases` imports no `documents`
  code and `audit` imports no document models. Fixtures contain synthetic platform text only; no
  case, legal, credential, path, or file-byte data was added.

## DOC-002 — Model immutable template versions and private storage keys

- **Completion date:** 2026-09-12
- **Outcome:** Added immutable `TemplateVersion` metadata with UUID identity, registry key and
  version, opaque server-generated private key, sanitized display filename, SHA-256, bounded byte
  size, lifecycle status, fixed-schema bounded validation report, uploader/time, protected
  activation actor/time, and approval reference.
- **Durable invariants:** PostgreSQL enforces unique type/version, a partial unique active version
  per type, status/key/version/storage/checksum/size/display-name/activation checks, and exact
  storage-key identity. A PostgreSQL history trigger requires initial `uploaded` state, permits only
  declared transitions, bounds report writes, freezes completed reports and identity/file/approval
  metadata, preserves first activation metadata, and rejects deletion. Model transitions lock and
  re-read the row so stale instances cannot overwrite committed state; supported ORM update,
  bulk-create, bulk-update, and delete paths are blocked.
- **Private storage:** Keys contain only validated server-owned components and random UUID material.
  Existing private filesystem storage produced `0600` files and `0700` directories, exposes no URL,
  and never derives a storage path from the sanitized display filename.

## CP-DOC-A — Checkpoint closure

- **Completion date:** 2026-09-12
- **Status:** Local implementation and verification complete; `DOC-001` and `DOC-002` are complete.
  Work stopped before `DOC-003` as required; human approval is pending.
- **Focused and coverage evidence:** The final focused SQLite profile passed 77 tests with two
  intentional PostgreSQL-only skips. The final PostgreSQL 18.6 profile passed all 79 tests. The
  mandated full coverage command passed 606 tests with 14 intentional environment-profile skips at
  94.89% branch coverage; `apps/documents/registry.py` reached 98.59%, above the 95% sensitive-module
  threshold.
- **Migration and schema evidence:** PostgreSQL applied the complete migration graph from an empty
  database, reversed `documents.0001_initial` to zero, and reapplied it successfully. Direct schema
  inspection confirmed the history trigger, both uniqueness guarantees, all declared checks and the
  bounded lookup index. Migration drift is empty.
- **Quality commands:** Ruff lint and format, mypy over `apps config`, Django system and migration
  checks, Tailwind build, vendored-asset verification, message extraction, Vietnamese compilation,
  sensitive-module coverage, and diff checks passed. English gettext source and Vietnamese catalog
  entries were added together.
- **Security and adversarial review:** Tests cover unknown/request-like identifiers, traversal and
  Windows filename hazards, storage-prefix wildcard attacks, checksums and 10 MiB size bounds,
  report shape/size/sensitive-field rejection, stale transitions, activation metadata injection,
  raw-SQL immutable updates/deletion, unsupported ORM bulk writes, and restrictive filesystem
  permissions. Two fresh-context review cycles found and drove fixes for lifecycle locking,
  database history durability, placeholder kinds, formsets, report safety, storage-key equality and
  bulk-write bypasses. The authorized Codex CLI second-opinion attempt remained read-only but failed
  to return findings because it recursively paused for another review choice; no external finding
  was treated as verification.
- **HTTP, authorization, CSRF, IDOR, audit and DOCX:** Not applicable at this metadata-only
  checkpoint: no views, unsafe endpoints, object selectors, audit workflow, upload handling, or DOCX
  parsing/rendering was introduced. Those gates begin with `DOC-003` through `DOC-006`. Registry
  lookup remains deliberately separate from authorization and template availability.
- **Full-page, HTMX, no-JavaScript and browser evidence:** Not applicable because CP-DOC-A adds no
  user-facing route or interactive behavior. Existing frontend assets and full application tests
  remain green.
- **Commit:** Checkpoint implementation commit follows this entry.
- **Deviations or blockers:** No implementation blocker remains. PostgreSQL-only durability is
  additionally protected by application checks under SQLite. The next eligible checkpoint is
  `CP-DOC-B` (`DOC-003`, `DOC-004`), which was not started.

## DOC-003 — Validate hostile OPC/ZIP packages and relationships

- **Completion date:** 2026-09-12
- **Outcome:** Added a pure byte/bounded-stream validator that authenticates ZIP structure and the
  readable central directory, validates required OPC and WordprocessingML parts, normalizes entry
  and relationship targets, parses bounded XML without DTD/entity resolution, and returns only
  stable categories with bounded structural locations. It performs no extraction, persistence,
  request/user lookup, rendering, activation, logging, or temporary-file creation.
- **Explicit limits:** 10 MiB compressed input, 512 entries, 50 MiB total expanded data, 10 MiB per
  expanded entry, 100:1 per-entry compression ratio, 2 MiB per XML part, XML depth 64, and at most
  50 returned findings. Limits are immutable, centrally declared, reject fail-open values, and are
  tested below, at, and above applicable boundaries.
- **Threat coverage:** Synthetic fixtures cover renamed/corrupt/truncated packages, required-part
  loss, absolute/traversing/backslash/encoded/NUL/unsafe names, duplicates and case collisions,
  entry/expanded/compression limits, encrypted flags, macro/VBA, ActiveX, OLE, embedded packages,
  executables and prohibited binaries, disguised binary magic, malformed/ambiguous content types,
  malformed/internal/external/unsafe/missing relationship targets, DTD/entities/network references,
  UTF-16/32 evasion, malformed/oversized/deep XML, interrupted or non-byte streams, deterministic
  output, bounded reports, and absence of content in logs.
- **Important files changed:** `apps/documents/{limits.py,package_validation.py,models.py}`,
  `apps/documents/tests/{docx_fixtures.py,test_package_validation.py}`, and
  `docs/architecture/TEMPLATE_VALIDATION.md`.
- **Verification and security review:** 86 focused threat tests passed. Focused combined coverage
  reported 95.81% for the package module; the dedicated branch-only gate reported 95.21%. The
  documents suite, Ruff, mypy, Django checks, migration drift, and the then-current 693-test full
  suite passed. An adversarial review produced actionable fixes for wide-encoding entity bypasses,
  magic/content-type ambiguity, relationship semantics, Word root/body structure, recursive path
  decoding, bounded findings, pre-tree XML depth, limit validation, stream failures, OPC declaration
  coverage, and optional relationship semantics.
- **Commit:** `fb0e663e8de4f346a82e89f1d9d78a05e67873b0` (`DOC-003`).
- **Deviations or blockers:** No implementation blocker remains. No temporary resources exist to
  leak on success or failure. Only synthetic generated packages were used; the repository's legal
  DOCX source was not opened or processed.

## DOC-004 — Validate Jinja syntax, contracts, related text parts, and split runs

- **Completion date:** 2026-09-12
- **Outcome:** Added package-first placeholder discovery and contract validation across the main
  document, table paragraphs/rows/cells, numbered headers and footers, footnotes, and endnotes.
  Supported parts are an explicit allowlist; template syntax in other XML parts or outside supported
  visible run text is rejected rather than ignored. The same pure validator is reusable immediately
  before future generation.
- **Jinja restrictions:** The sandbox uses `StrictUndefined`, always-on XML autoescaping, no loader,
  no tests or default globals, fixed registry-and-platform filter/global intersections, no callable
  or Python attribute access, and finalization that converts pre-marked safe values back to escaped
  data. Validation rejects missing/unknown variables, unsafe or loop-local attributes, calls,
  imports, includes/inheritance, assignments/macros, subscripts, tests, disallowed filters/globals,
  type-incompatible filters/loops, dynamic arithmetic/collection expressions, malformed syntax,
  and malformed delimiters. Case values are data and are never reparsed as source.
- **Parser limits:** Per supported part: 256 KiB reconstructed source, 4,096 tokens, 4,096
  characters per token, 32 control/expression nesting levels, 8,192 AST nodes, and AST depth 64.
  Limit failure returns the stable bounded `complexity_limit` category.
- **Run and structure coverage:** Paragraph text is reconstructed with run/style boundaries,
  including compatible tab and break nodes. Tests reject split opening/closing delimiters, split
  variable names, partial styling, hidden/non-visible tokens, and invalid/multiple paragraph, row,
  cell, or run structural tags without rewriting source; whole-token formatting and valid
  structural containers pass.
- **Important files changed:** `apps/documents/{limits.py,template_validation.py}`,
  `apps/documents/tests/test_template_validation.py`,
  `docs/{architecture/TEMPLATE_VALIDATION.md,templates/TEMPLATE_AUTHORING_GUIDE.md}`, and the
  sensitive coverage selector/tests.
- **Verification and security review:** 53 focused template tests and 139 combined package/template
  tests passed. Focused combined coverage reported 99.59% for the template module; the dedicated
  branch-only gate reported 99.21%. The final documents suite passed 216 tests with two expected
  environment-profile skips. Adversarial TDD cycles closed hidden UTF-16 part syntax, non-visible
  XML tokens, local attribute traversal, parser complexity, value-kind/filter mismatches, empty-tag
  exception escape, coverage-gate selection, and pre-marked safe-value bypasses.
- **Commit:** `dbdc34bc50d15f5c430b5e16fefce11728a96d5d` (`DOC-004`).
- **Deviations or blockers:** No implementation blocker remains. A requested fresh-context final
  reviewer could not run because its model account hit a usage limit; the earlier fresh-context
  review and subsequent single-model adversarial TDD cycles were completed, and the user explicitly
  directed continuation with a single model.

## CP-DOC-B — Checkpoint closure

- **Completion date:** 2026-09-12
- **Status:** Local CP-DOC-B implementation and verification are complete. `DOC-003` and `DOC-004`
  are complete, and work stopped before `DOC-005`.
- **Quality and coverage:** Ruff lint and format, mypy over `apps config`, Django system and migration
  drift checks, and diff checks passed. The required full coverage command passed 749 tests with 14
  expected environment-profile skips at 95.34% overall combined branch coverage. The dedicated
  branch-only gate passed package validation at 95.21%, the registry at 97.56%, and template/Jinja
  validation at 99.21%. The gate now includes validator modules while excluding test modules.
- **Cross-task security:** Package validation is called before any Jinja environment is created or
  source parsed; an invalid package test proves that short circuit. Validators accept no paths,
  actors, requests, cases, drafts, or database rows. No archive extraction, network/entity access,
  arbitrary import/call/global/attribute traversal, uploaded-byte/XML/placeholder logging, document
  content in reports, or temporary resources exist. External relationships, macros, VBA, ActiveX,
  OLE, embedded packages/executables, encryption, and unsupported split runs all fail closed.
- **Privacy, scope, and dependencies:** Every fixture is synthetic and no real legal template or
  personal data was used. No upload orchestration, persistence transition, UI, activation, draft,
  rendering, or generation behavior was introduced. `cases` imports no `documents` code. No
  migrations, dependency changes, secrets, debug output, broad ignores, test suppression, hardcoded
  Vietnamese application strings, or unrelated cleanup were added.
- **Temporary cleanup:** Both validators operate in memory and create no temporary directories or
  files, so success and every tested failure leave no temporary resource. Stream interruption and
  failure paths return safe deterministic categories without exception or content leakage.
- **Commits:** `fb0e663e8de4f346a82e89f1d9d78a05e67873b0` (`DOC-003`);
  `dbdc34bc50d15f5c430b5e16fefce11728a96d5d` (`DOC-004`). Checkpoint record commit follows this
  entry.
- **Deviations or blockers:** The final fresh-context reviewer was unavailable because of its model
  usage limit; this is recorded rather than treated as review evidence. The user chose single-model
  continuation. No implementation or verification blocker remains. The next tasks are `DOC-005`
  and `DOC-006` for `CP-DOC-C`; neither was started.

## DOC-005 — Orchestrate upload validation and synthetic renders

- **Completion date:** 2026-09-12
- **Outcome:** Added an explicit authorized upload service for enabled code-registry types. It
  validates version and approval provenance, bounded-streams at the 10 MiB compressed limit into a
  process-private temporary directory while calculating SHA-256 and size, assigns an opaque
  server-generated private storage key, and preserves accepted bytes plus immutable identity facts.
- **Validation order and lifecycle:** The service invokes the existing OPC/ZIP security validator
  before the existing restricted Jinja/placeholder validator, then renders both registry-supplied
  minimal and representative synthetic contexts. Every output is reopened and rechecked as DOCX,
  including relevant Word parts, unresolved template tokens, and expected Vietnamese Unicode.
  Outcomes persist only as `uploaded` to `valid` or `uploaded` to inactive `invalid`; no version is
  activated or made available to case generation.
- **Storage, reports and audit:** Invalid accepted uploads follow the configured private-retention
  policy. Reports contain only fixed schema, bounded categories and counts. Upload and validation
  each produce exactly one bounded audit event without bytes, paths, filenames, exception text, or
  rendered content. Tests force interrupted input, storage and rendering and confirm temporary-file
  cleanup on every success and failure path.
- **Tests and review:** Fifteen orchestration integration tests cover valid/invalid outcomes,
  unknown/disabled types, duplicate versions, absent approval references, both service permissions,
  exact bytes/checksum, safe report/audit cardinality, storage/render interruption, hostile package
  short-circuiting, split-run ordering, and meaningful inspection of both synthetic outputs. The
  complete documents suite later passed 249 tests with two environment-profile skips, and the
  PostgreSQL documents profile passed all 252 tests.
- **Migration:** None. Existing `TemplateVersion` constraints and private storage contract are
  reused unchanged.
- **Commit:** `0073172b936311530eeb5884225d47c3950ef61b` (`DOC-005`).
- **Deviations or blockers:** None. Only the non-production synthetic registry entry and generated
  synthetic DOCX fixtures were used; no approved VDS template was read or uploaded.

## DOC-006 — Deliver template list, upload, and validation UI

- **Completion date:** 2026-09-12
- **Outcome:** Replaced the document placeholder with Vietnamese Administrator pages for enabled
  registry types: a paginated type/version list, selected-type upload form, validation outcome, and
  bounded safe report. Valid, invalid, unavailable/empty, busy, success, field-error and generic
  server-error states are explicit. Valid versions are labelled only as candidates for later
  activation, and the UI exposes no activation action.
- **Progressive enhancement and authorization:** Ordinary navigation and multipart POST/redirect/get
  work without JavaScript. HTMX responses use narrow fragments, `Vary: HX-Request`, no-store,
  swappable `422` errors, CSRF, disabled submit/busy presentation, live regions, and focusable linked
  error summaries and outcomes. View permissions cover list/upload/validation while the service
  repeats upload/validation authorization. Unknown keys return the established generic not-found
  policy, and expired sessions redirect without processing an upload.
- **Privacy and safe presentation:** Views call the `DOC-005` service and never write
  `TemplateVersion` directly. Templates display translated allowlisted category summaries only;
  they do not expose storage keys, private paths or URLs, uploaded filenames, package content,
  tracebacks, raw findings, or exception strings. Safe version and approval text survives form
  correction, while file inputs are not repopulated.
- **Tests, coverage and browser:** Eighteen focused view/form tests passed; focused forms/views branch
  coverage was 93.60%. Five focused Chromium tests passed across compact, tablet and wide layouts,
  covering keyboard focus, HTMX busy/error/outcome announcements, safe value preservation, invalid
  package presentation, no page overflow, JavaScript-disabled submission, and 200% zoom. The final
  full pinned-Chromium suite passed all 73 tests.
- **Migration:** None. The existing registry, model lifecycle and constraints are unchanged.
- **Commit:** `15aeda1723dbae269eb6782749d7d5fc6923a252` (`DOC-006`).
- **Deviations or blockers:** Chrome DevTools MCP was not available in this environment; the
  repository's pinned Playwright/Chromium fallback supplied the browser evidence.

## CP-DOC-C — Checkpoint closure

- **Completion date:** 2026-09-12
- **Status:** Local implementation and verification are complete for `DOC-005` and `DOC-006`.
  Work stopped before `DOC-007`; no template was activated. Human review is pending.
- **Required quality gates:** Ruff lint and format, mypy over `apps config`, Django system and
  migration-drift checks, Tailwind build, gettext extraction and Vietnamese message compilation all
  passed. Vendored frontend asset pins/checksums and diff checks also passed. The mandated full
  branch-coverage command passed 782 tests with 14 intentional environment-profile skips at 95.34%
  overall coverage.
- **PostgreSQL and migrations:** A disposable UTF-8 PostgreSQL 18.6 database applied the complete
  migration graph from zero and reported no drift. The complete documents plus PostgreSQL
  integration profile passed all 252 tests, exercising existing registry/template uniqueness,
  lifecycle, immutability, report, private-key and database constraints. No checkpoint migration was
  created.
- **Validation, storage and audit:** Regression tests prove package validation precedes Jinja parsing
  and rendering, hostile and split-run packages fail on the established paths, minimal and
  representative outputs reopen and pass structural/Unicode/token checks, and all process-private
  temporary files are cleaned after success and forced read/storage/render failures. Valid immutable
  versions alone become later activation candidates; invalid versions remain inactive and
  unavailable. Audit/report assertions exclude uploaded content, filenames, private paths and raw
  errors and prove one upload plus one validation event per accepted outcome.
- **HTTP and browser security:** Full-page, HTMX and JavaScript-disabled flows pass alongside
  permission-matrix, direct-service denial, normal/HTMX CSRF, expired-session, duplicate/version,
  file-size boundary, generic not-found, safe `422`, safe `500`, focus, reflow and no-horizontal-
  overflow checks. The full Playwright suite passed 73 tests. No direct private-file URL or public
  template storage exists.
- **Scope and repository review:** No activation/deactivation, document-type creation, real VDS
  onboarding, draft, generation, PDF, background-job, object-storage, case dependency, schema
  change, secret, personal data, test suppression, debug artifact, or unrelated edit was added.
  `cases` remains independent of `documents`, and audit remains independent of business models.
- **Commits:** `0073172b936311530eeb5884225d47c3950ef61b` (`DOC-005`);
  `15aeda1723dbae269eb6782749d7d5fc6923a252` (`DOC-006`). Checkpoint record commit follows this
  entry.
- **Deviations or blockers:** No implementation or local verification blocker remains. Chrome
  DevTools MCP and external CI were unavailable and are not claimed; pinned local Chromium and the
  complete local quality/PostgreSQL gates passed. The next `CP-DOC-D` tasks are `DOC-007` and
  `DOC-008`; neither was started.

## DOC-007 — Implement atomic activation and confirmed deactivation

- **Completion date:** 2026-09-13
- **Outcome:** Added explicit activation and deactivation services plus purpose-built confirmation
  views. Transitions resolve deployed registry keys, require distinct permissions at both HTTP and
  service boundaries, validate lifecycle and approval state, preserve immutable version identity
  and bytes, and expose only committed active versions to future selection.
- **Concurrency and recovery:** PostgreSQL advisory transaction locking serializes each registry
  type without locking its complete history. The existing conditional unique constraint remains the
  final zero-or-one-active invariant. A type-level expected-active token detects stale requests;
  ordinary and HTMX callers receive recoverable conflict handling, while repeated transitions are
  deterministic. No migration was required because real concurrent service and HTTP races proved
  the lock and existing constraint sufficient.
- **HTTP, security and audit:** Mutations are POST-only and CSRF-protected. Full-page, HTMX and
  JavaScript-disabled confirmation flows identify only the type and safe version label. Audit events
  include actor, time, safe version identity, outcome and approval-reference identifier, including
  replacement deactivation, without storage keys, private paths, filenames or package content.
- **Tests and browser:** Focused service/view testing passed 28 tests with two PostgreSQL-profile
  skips; the broader document regression profile passed 89 tests with four profile skips. The final
  PostgreSQL checkpoint profile passed all four selected database tests, including different-version
  activation races and concurrent HTMX requests. Focused Playwright/Chromium confirmation checks
  passed 2/2 for HTMX focus and no-JavaScript fallback.
- **Commit:** `570bd84` (`DOC-007`).
- **Deviations or blockers:** None. A cross-model Codex CLI review and fresh-context adversarial
  review were applied; their actionable concurrency, bounded-lock, audit and recovery findings were
  resolved before completion.

## DOC-008 — Model versioned mutable drafts and form contracts

- **Completion date:** 2026-09-13
- **Outcome:** Added `DocumentDraft` and a version-aware service contract for bounded, validated
  document-specific JSON in `draft` and `ready` states. Stable case/type/schema identity, revision,
  creator/editor and timestamps are explicit; finalized snapshots and generation remain separate.
- **Validation, authorization and concurrency:** Every create, update and ready transition resolves
  the exact registry form/formsets, rejects unknown or incompatible schema, revalidates normalized
  data, batch re-queries declared related identifiers within the case, rechecks case permission and
  archive state, and performs a direct atomic revision-guarded update. Concurrent PostgreSQL updates
  prove one success and one recoverable stale conflict with no lost write.
- **Migration and storage:** `apps/documents/migrations/0002_add_document_drafts.py` creates the
  draft table, case/type/schema indexes, one-draft identity policy, state/revision/type/schema
  constraints, and PostgreSQL JSON-object and 65,536-byte payload checks. The linear graph applied
  successfully both to an empty PostgreSQL 17 database and as an upgrade from the committed
  `CP-DOC-C` schema. Inspection confirmed all expected constraints and indexes. A stored synthetic
  draft contained only the approved document-specific fields.
- **Security and audit:** Writes require draft add/change permission plus case access; reads require
  draft view permission plus case access. Archived or inaccessible cases, cross-case related IDs,
  prohibited graph/snapshot keys and direct unauthorized service calls are rejected. Audit events
  contain bounded field names or categories only; forced validation and audit failures roll back,
  and tests exclude payload values and personal case data from logs.
- **Tests:** Focused registry/model/service testing passed 84 tests with two PostgreSQL-profile skips;
  the complete documents/storage regression profile passed 316 tests with six profile skips. The
  final PostgreSQL checkpoint profile passed its draft JSON-constraint and concurrent-revision tests
  alongside the DOC-007 races.
- **Commit:** `8dfa93f` (`DOC-008`).
- **Deviations or blockers:** None. Fresh-context review findings for disabled historical schemas,
  identity immutability, batch related-ID validation and formset error preservation were resolved.

## CP-DOC-D — Checkpoint closure

- **Completion date:** 2026-09-13
- **Status:** Local implementation and verification are complete for `DOC-007` and `DOC-008`;
  human review is pending. Work stopped before `DOC-009` and `DOC-010`.
- **Required quality gates:** Ruff lint and format, mypy over `apps config`, Django system and
  migration-drift checks, Tailwind CSS build, and the mandated full branch-coverage command passed.
  The full suite reported 845 passed, 18 intentional environment-profile skips, and 94.48% overall
  branch coverage, above the 85% project threshold.
- **PostgreSQL and migrations:** The final real-PostgreSQL profile passed 4/4 selected tests covering
  database payload enforcement, service activation races, concurrent HTMX activation and optimistic
  draft updates. Empty-database and `CP-DOC-C`-schema upgrade paths both applied the linear graph
  through documents migration `0002`; Django reported no migration drift.
- **Security and scope review:** Separate transition and draft permissions are enforced at service
  and view boundaries; CSRF and POST-only behavior pass; historical template identity, checksum and
  bytes remain unchanged; audit, response and log assertions exclude private paths, package content,
  draft payload and sensitive case data. `cases` imports no `documents` code. No selector UI,
  generation workflow, finalized snapshot, real VDS form or other `CP-DOC-E` work was introduced.
- **Browser and review evidence:** The final focused Playwright suite passed both activation
  confirmation checks. Cross-model Codex CLI and independent fresh-context reviews were completed
  and all accepted findings were retested. External CI and Chrome DevTools MCP were unavailable and
  are not claimed.
- **Commits:** `570bd84` (`DOC-007`); `8dfa93f` (`DOC-008`). Checkpoint record commit follows this
  entry.
- **Deviations or blockers:** No implementation or local-verification blocker remains. The next
  `CP-DOC-E` tasks are `DOC-009` and `DOC-010`; neither was started.

## DOC-009 — Deliver document selector and draft form framework

- **Completion date:** 2026-09-13
- **Outcome:** Added stable case-scoped selector and draft routes. The selector intersects the
  immutable code registry with enabled registrations and the database-enforced single active
  template version. Unknown, disabled, invalid, inactive and template-less types remain absent and
  direct access returns the established generic unavailable behavior without resolving executable
  behavior from request data.
- **Draft workflow:** Full pages and narrow HTMX fragments load the registry-owned versioned form
  and formsets, create or update the one compatible draft through the `DOC-008` service, preserve
  submitted field and repeated-row values, support `draft` and `ready`, and return intentional
  `422` validation, recoverable `409` revision/schema, and generic recoverable `500` fragments.
  Responses vary on `HX-Request`, disable caching and HTMX history, retain server/URL ownership,
  and keep ordinary navigation and submission functional without JavaScript.
- **Authorization, privacy and accessibility:** Views require case-object access and draft-view
  permission; services repeat add/change/view enforcement, related UUID case scoping, schema
  validation and archive restrictions. Normal and HTMX unsafe requests remain CSRF protected.
  Audit metadata contains safe type/schema/state/revision and field names or categories only.
  Source sections, semantic formset fieldsets, linked summaries, focusable conflict/server states,
  busy labels, empty/unavailable states and translated Vietnamese copy were verified without
  persisting case or draft values in browser storage or query strings.
- **Tests and browser:** TDD began with nine expected route failures. The completed focused profile
  passed 84 tests with one environment-profile skip; the documents regression profile passed 321
  with six profile skips. Four pinned Chromium tests covered compact, tablet and wide long-content
  draft layouts, keyboard focus, server-side validation, Vietnamese expansion, reflow/no horizontal
  overflow, and a no-JavaScript 200% workflow.
- **Migration:** None. Existing `TemplateVersion` and `DocumentDraft` lifecycle, uniqueness and
  schema contracts are reused.
- **Commit:** `d134e5a` (`DOC-009`).
- **Deviations or blockers:** Chrome DevTools MCP was unavailable; the repository's pinned local
  Playwright/Chromium suite supplied browser evidence. No generation, snapshot, artifact, download,
  legal formatter or real VDS form was added.

## DOC-010 — Define the case transfer value and explicit prefill boundary

- **Completion date:** 2026-09-13
- **Outcome:** `cases` now exports frozen, slotted Court, Case, Participant, Representation,
  OfficialAssignment and Hearing transfer values from an already authorized case context.
  `documents` consumes that typed value through an explicit type/schema mapper for form/formset
  initial data, field source labels and override comparisons. Draft overrides remain isolated from
  ORM case state and future snapshot behavior remains outside this checkpoint.
- **Determinism and query behavior:** The selector preserves Vietnamese Unicode, prefers
  case-specific participant address/contact values, and orders participants, representations,
  assignments and hearings explicitly. It performs a fixed seven queries after authorization with
  eight participants, including a defense-in-depth permission/object-policy recheck; participant
  growth adds no queries. No query-plan evidence justified a new index or migration.
- **Dependency and privacy boundary:** `cases` imports no `documents` module; an AST dependency guard
  proves the one-way edge and absence of a circular application import. Mapping uses no reflection,
  `model_to_dict`, naming coincidence or arbitrary ORM traversal. Tests prove no case write service,
  ORM mutation, cache, logging or browser storage receives transfer or draft values; no sensitive
  value appears in audit metadata or captured logs.
- **Tests and review:** TDD began with expected missing-module import failures. The final focused
  transfer/mapping/workflow profile passed 29 tests; the combined cases/documents profile passed 677
  with 16 environment-profile skips. Coverage includes minimal and complete cases, all core roles,
  deterministic multiples, addresses/contacts, representations, officials, hearings, archived read,
  forged/unauthorized contexts, immutability, Unicode, overrides, formsets, cross-case identifiers,
  schema/revision conflicts and service/view permission agreement. Multi-axis code, API, security,
  privacy, query and accessibility review found no remaining actionable issue.
- **Migration:** None. PostgreSQL query-count evidence did not justify an index.
- **Commit:** `70af71a` (`DOC-010`).
- **Deviations or blockers:** None in implementation. The final review corrected valid-formset error
  summary detection before this commit and its 11 workflow tests passed.

## CP-DOC-E — Checkpoint closure

- **Completion date:** 2026-09-13
- **Status:** Local implementation and verification are complete for `DOC-009` and `DOC-010`;
  human review is pending. Work stopped before `DOC-011` and `DOC-012`.
- **Required quality gates:** Ruff lint and format, mypy over `apps config`, Django system and
  migration-drift checks, Tailwind CSS build, gettext extraction and Vietnamese catalog compilation
  passed. The mandated final branch-coverage command passed 874 tests with 18 intentional
  environment-profile skips at 94.64% overall, above the 85% project gate. The sensitive-module
  guard separately passed every measured module at or above 95% branch coverage.
- **PostgreSQL and migrations:** An isolated UTF-8 PostgreSQL 18.6 database applied all migrations
  from zero through `documents.0002`, reversed the documents leaf to zero, reapplied it, and then
  reported no migrations to apply. The selected transfer, workflow, draft and PostgreSQL integration
  profile passed 57/57. Django reports no migration drift; no checkpoint migration was created.
- **Browser and progressive enhancement:** The complete pinned Chromium suite passed 79/79,
  including the four new document tests at compact/tablet/wide widths and no-JavaScript 200% zoom.
  It verified keyboard activation, linked/focused summaries, long Vietnamese content, reflow,
  `422` behavior, ordinary redirects and absence of case-prefill values from local/session storage.
  The complete suite preceded a final one-line formset error-count correction; that correction then
  passed all 11 workflow tests. A redundant browser rerun was attempted but could not launch because
  the execution tool reported its usage limit, so no post-correction browser rerun is claimed.
- **Security, privacy and scope:** Registry/type allowlisting, single-valid-active availability,
  draft/schema/revision recovery, view/service permissions, case-object policy, CSRF, archived-case
  write denial and cross-case related-ID rejection pass. Prefill and draft data are absent from logs,
  audit metadata, cache, cookies, browser storage and query strings. No database-defined executable
  mapping, cross-application case write, generation reservation, renderer, artifact, download,
  formatter or real legal form was introduced.
- **Commits:** `d134e5a` (`DOC-009`); `70af71a` (`DOC-010`). Checkpoint record commit follows this
  entry.
- **Deviations or blockers:** Chrome DevTools MCP, external CI and the redundant final browser rerun
  were unavailable and are not claimed. Pinned Chromium already passed the complete pre-correction
  suite, and focused post-correction behavior is green. No implementation blocker remains. The next
  `CP-DOC-F` tasks are `DOC-011` and `DOC-012`; neither was started.

## DOC-011 — Implement deterministic Vietnamese legal formatters

- **Completion date:** 2026-09-14
- **Outcome:** Added the explicit `vi-legal-v1` formatter contract for legal dates, date-only values,
  Ho Chi Minh City datetimes, personal and organization names, addresses, generic identifiers,
  numeric currency, Vietnamese currency words, reviewed word overrides, and controlled multiline
  Word XML text. Frozen result values retain independently reviewable raw input and deterministic
  formatted output without database, actor, network, audit, or locale state.
- **Formatting decisions:** Date-only inputs never receive timezone conversion; aware datetimes are
  converted to `Asia/Ho_Chi_Minh` and reject unsupported precision. Authoritative Unicode spelling,
  normalization, diacritics, uppercase, and mixed case are preserved. Only contract-declared
  whitespace is normalized; address components are joined without guessing missing administrative
  units. Currency keeps `Decimal` numeric facts separate from Vietnamese words and from an explicit
  reviewed override; no currency or template suffix is guessed.
- **XML and privacy:** The typed multiline adapter rejects arbitrary construction, validates XML 1.0
  characters and bounded input, escapes XML-sensitive characters, encodes Jinja delimiters as data,
  and preserves only approved line or paragraph breaks. It does not use `safe`, `mark_safe`, template
  execution, database access, logging, or other side effects.
- **Tests and coverage:** TDD covered Vietnamese dates and edge cases, timezone conversion and
  date-only invariance, locale independence, Unicode/name casing, addresses, identifiers, currency
  boundaries and overrides, multiline/XML/Jinja input, length bounds, raw-value retention, and
  representative synthetic Vietnamese strings. The final focused formatter profile passed 83 tests;
  `apps/core/legal_formatters.py` reached 99.01% branch coverage in the checkpoint-wide run.
- **Review and legal boundary:** Two fresh-context reviews and an authorized cross-model Codex CLI
  review found and corrected typed-adapter, XML-character, datetime-precision, raw-override, and
  paragraph-break issues. Exact template-specific wording, identifier patterns, suffixes, and legal
  approval remain deferred to each later VDS onboarding contract.
- **Migration:** None.
- **Commit:** `7588496` (`DOC-011`).
- **Deviations or blockers:** No implementation blocker remains. No real VDS form, legal wording, or
  generated document was introduced.

## DOC-012 — Model generation attempts and reserve idempotently

- **Completion date:** 2026-09-14
- **Outcome:** Added `GeneratedDocument` with UUID identity, protected case/template/actor references,
  stable type and schema, source revisions, lifecycle timestamps, versioned input/resolved/override/
  template snapshots, actor-scoped SHA-256 idempotency identity, safe failure fields, future output
  metadata, and case/type/status/actor history indexes. Supported model/query paths cannot rewrite or
  delete reservation history; retries use a new token and row.
- **Reservation and idempotency:** `reserve_generation` enforces generation permission and scoped case
  access, rejects archived cases, resolves the enabled registry schema, locks case and draft in a
  consistent order, revalidates the exact ready draft, serializes template activation through the
  shared type advisory lock, and pins the expected active valid template. It freezes exact cleaned
  input, resolved shared values, override provenance, template identity/checksum, revisions, and
  actor. A 256-bit URL-safe opaque token is validated and stored only as an actor-scoped hash;
  repeats return the original authorized row and audit event without refreshing facts.
- **Migration and database invariants:** `documents.0003_generated_document` creates the table,
  protected foreign keys, unique actor/token-hash scope, lookup indexes, status/output/path/checksum
  checks, strict numeric versioned JSON envelopes, and PostgreSQL triggers that enforce immutable
  reservation facts, one-way lifecycle changes, protected template type/identity/version/checksum
  agreement, and delete denial. Output-key identity works consistently with PostgreSQL and SQLite
  UUID representations. The graph remains linear.
- **Concurrency and snapshots:** A disposable PostgreSQL 18.6 database applied the full graph from
  zero and the migration test upgraded from the committed `CP-DOC-E` leaf. The final 53-test
  PostgreSQL profile passed sequential and genuine concurrent duplicate tokens, distinct tokens,
  cross-case token reuse, activation races, case/draft edit races, the draft-service lock-order race,
  stale revisions, malformed raw inserts, lifecycle constraints, immutability, and migration graph
  checks. Successful attempts remained pinned after later case, draft, and template changes.
- **Authorization, audit, and privacy:** Direct permission denial and object-scope denial pass at the
  service boundary. Reservation creates exactly one bounded audit event. Correlation identifiers are
  normalized and replaced when they equal a token, case/draft identifier, or reserved snapshot
  value; raw database exception causes are suppressed. Tests prove tokens, snapshots, payloads, case
  values, and resolved values are absent from logs and audit metadata. Reservation imports no render,
  parser, temporary-file, checksum, or artifact-storage work.
- **Tests, coverage, and review:** The final combined document/formatter/sensitive profile passed 453
  tests with 15 environment-profile skips. `apps/documents/generation_reservations.py` reached 97.22%
  branch coverage in the full run. Fresh-context, security, and authorized cross-model Codex CLI
  reviews found and corrected generated-size NULL handling, weak JSON checks, a cross-case uniqueness
  race, correlation/token leakage, raw database exception chaining, case/draft lock inversion,
  database template inconsistency, and SQLite UUID constraint portability. The final third-cycle
  review found no PostgreSQL blocker.
- **Commit:** `75b5da1` (`DOC-012`).
- **Deviations or blockers:** The first exploratory empty-schema command accidentally targeted the
  ignored development SQLite database because test settings were omitted; it is not counted as
  PostgreSQL evidence. The corrected isolated PostgreSQL runner set test settings explicitly and
  passed from zero. Two early external CLI review attempts produced incomplete captured output; the
  authorized compact replacement completed after transient websocket retries. Template placeholder
  compatibility is deliberately rechecked immediately before rendering in `DOC-013`; no rendering
  occurred here. No implementation blocker remains.

## CP-DOC-F — Checkpoint closure

- **Completion date:** 2026-09-14
- **Status:** Local implementation and verification are complete for `DOC-011` and `DOC-012`; human
  review is pending. Work stopped before `DOC-013` and `DOC-014`.
- **Required quality gates:** Ruff lint and format, mypy over `apps config`, Django system and
  migration-drift checks, gettext extraction and Vietnamese catalog compilation all passed. The
  mandated full branch-coverage command passed 992 tests with 27 intentional environment-profile
  skips at 93.48% overall, above the 85% project threshold. The sensitive-module gate passed, with
  legal formatters at 99.01% and generation reservation at 97.22% branch coverage.
- **PostgreSQL evidence:** PostgreSQL 18.6 applied every migration from an empty database through
  `documents.0003`; the committed-schema upgrade and linear leaf were verified. The final focused
  PostgreSQL profile passed 53/53, including genuine idempotency, activation, case-edit, draft-edit,
  lock-order, immutable-snapshot, protected-reference, and status/output constraint cases.
- **Security, privacy, and scope:** Legal formatting is pure, versioned, locale-independent, bounded,
  and escaped. Reservation rechecks service and object permissions, freezes raw/resolved/provenance
  facts without rendering, and creates one attempt/audit per actor-scoped token. Audit and logs contain
  no tokens or snapshot values. `cases` imports no `documents` code. No filesystem artifact, DOCX
  render, checksum, download route, generation UI, real VDS implementation, or legal wording was
  added; no successful artifact exists yet.
- **Commits:** `7588496` (`DOC-011`); `75b5da1` (`DOC-012`). Checkpoint record commit follows this
  entry.
- **Deviations or blockers:** No implementation or local-verification blocker remains. External CI
  is not claimed. The next `CP-DOC-G` tasks are `DOC-013` and `DOC-014`; neither was started.

## DOC-013 — Render with restricted context and validate DOCX output structure

- **Completion date:** 2026-09-15
- **Outcome:** Added a pure renderer for reserved generation attempts. It re-verifies the pinned
  template identity and checksum, re-runs the registered template contract immediately before use,
  maps only declared typed snapshot values, rebuilds dotted names into a restricted nested context,
  renders through docxtpl with the existing StrictUndefined sandbox, and removes its process-private
  temporary directory on both success and failure. Post-processing remains absent by default and can
  run only by an approved name already registered in code.
- **Output integrity:** Added complete DOCX package and Word-part inspection for protected OPC parts,
  parseable XML, unresolved Jinja tokens or delimiters, paragraphs, tables, headers, footers, styles,
  sections and page breaks. Each code-owned document registration now declares its minimum output
  structure so legitimate conditional template branches are not compared to misleading raw-template
  counts. A dual-render shadow preserves real filter behavior and XML escaping while deriving
  per-part provenance for literal Jinja-looking user data; unresolved source markup and markup added
  by a post-processor still fail closed.
- **Tests and evidence:** Focused tests cover missing/unknown/wrong-shaped mapper values,
  StrictUndefined-compatible revalidation, checksum and schema mismatch, conditional structures,
  all supported text parts, lost structures, malformed packages, XML-attribute tokens, exact
  source-token collisions, complete and unmatched hostile delimiters, XML metacharacters, Unicode,
  `lower`/`upper`/`length` filter semantics, approved post-processing and temporary cleanup. The final
  renderer/artifact/registry profile passed 116 tests at 97.17% combined branch coverage; the renderer
  itself reached 95.77%, above the required 95% gate.
- **Files:** `apps/documents/generation_rendering.py`, `apps/documents/output_validation.py`,
  `apps/documents/registry.py`, `apps/documents/tests/test_generation_rendering.py`, and
  `apps/documents/tests/test_registry.py`.
- **Migration:** None.
- **Commit:** Not created; the user did not request commits.
- **Deviations or blockers:** No implementation blocker remains. The synthetic representative was
  inspected directly through its OPC/XML structure and reopen checks; a Word desktop visual review
  is not available in this environment and remains part of the pending human checkpoint review, not
  legal approval.

## DOC-014 — Finalize immutable artifacts and persist recoverable failures

- **Completion date:** 2026-09-15
- **Outcome:** Added the authorized artifact pipeline from a reserved attempt through bounded template
  read, safe render, checksum/size verification, unique private placement and a short locked success
  transition. Private filesystem writes now stage and fsync a mode-restricted sibling file, publish it
  with an atomic no-overwrite hard link, and remove staging files in `finally`. Successful metadata is
  immutable under the existing model/database lifecycle controls and repeated finalization returns the
  one winning artifact without creating a second success audit.
- **Failure recovery and naming:** Render, context, template, storage and integrity failures clean only
  server-generated keys scoped to the attempt, preserve the draft and snapshots, durably transition the
  attempt to a bounded failed category/correlation identifier, and emit one safe failure audit without
  payloads or exception causes. Races cannot rewrite a terminal success. Display names are NFC-normalized,
  bounded to 150 characters, unique per attempt, stripped of controls, separators and Windows-forbidden
  characters, and protect dotted as well as plain Windows device names. Retries remain new reservation
  rows/tokens under `DOC-012`.
- **Tests and evidence:** Failure injection covers template reads, mapping, rendering, output validation,
  storage writes, altered read-back bytes, invalid returned keys, finalization/audit rollback, cleanup
  failures, terminal races, permission/scope denial, safe correlations, immutable metadata, retry rows,
  filenames and private file/directory modes. The final isolated PostgreSQL 18.6 profile passed 118/118,
  including genuine two-connection success/success and success/storage-failure finalization races; both
  leave one artifact and one success audit with no failed-state rewrite.
- **Files:** `apps/audit/actions.py`, `apps/core/storage.py`,
  `apps/documents/generation_artifacts.py`, `apps/documents/storage_keys.py`,
  `apps/documents/tests/test_generation_artifacts.py`, and
  `apps/documents/tests/test_generation_artifact_postgresql.py`.
- **Migration:** None. Existing `GeneratedDocument` states, output constraints and failure categories
  from `documents.0003` are reused; Django reported no migration drift.
- **Commit:** Not created; the user did not request commits.
- **Deviations or blockers:** None.

## CP-DOC-G — Checkpoint closure

- **Completion date:** 2026-09-15
- **Status:** Approved by the user on 2026-09-16. Local implementation and verification are complete
  for `DOC-013` and `DOC-014`.
- **Incremental slices:** (1) restricted snapshot context, template identity revalidation and safe
  rendering; (2) code-owned output structure contracts plus OPC/XML/token verification; (3) atomic
  immutable storage, checksums, safe filenames and recoverable failure transitions; and (4) concurrency,
  hostile-input provenance, privacy and cross-platform hardening. Each slice received focused tests and
  diff review before the next slice.
- **Required quality gates:** The pre-change baseline passed 111 tests with one expected profile skip.
  Final Ruff lint and format, mypy over `apps config`, Django system and migration-drift checks passed.
  The checkpoint-sensitive profile passed 116 tests at 97.17% combined branch coverage. The broader
  application regression profile passed 937 tests with 28 profile skips. The exact `Q-TEST` command
  passed 1,059 tests with 29 intentional environment-profile skips at 93.56% overall branch coverage,
  above the 85% project threshold. The real-PostgreSQL focused profile passed 118/118. `Q-DEPLOY`
  exited successfully and collectstatic copied 133 files; its sole diagnostic was the intentionally
  deferred `security.W004` HSTS warning already documented by the production-settings plan.
- **Acceptance evidence:** `AC-12` and `AC-15` are covered by pre-render contract revalidation,
  StrictUndefined rendering, hostile-value tests and deep output OPC/XML/structure assertions. `AC-16`
  is covered by bounded unique NFC and Windows/macOS/Linux-safe names. `AC-17` through `AC-20` are
  covered by pinned snapshots/template identity, output SHA-256/size/key/name metadata, authorized
  server-side execution, terminal row locks, safe success/failure audits, durable recoverable failure
  states and new-row retries. `AC-22` is covered by private mode-restricted atomic placement,
  post-write checksum verification and partial/orphan cleanup tests.
- **Security, privacy and scope:** No payload, snapshot value, generated text, raw exception, private
  path or unsafe correlation value is logged or audited. No suppressions, skipped acceptance tests,
  hardcoded Vietnamese UI strings, schema changes, UI/download workflow, real VDS type, legal wording,
  queue, network integration or unrelated refactor was introduced. `Q-CSS` and `Q-I18N` are not
  applicable because this checkpoint changes no UI assets or localized messages.
- **Review:** Multiple fresh-context adversarial cycles found and drove fixes for conditional structure
  validation, Windows dotted device names, per-part literal provenance, chained sensitive causes,
  real PostgreSQL concurrency, filter-preserving/XML-safe literal handling and standalone delimiters.
  No high-severity blocker remains. External CI and Word desktop are not claimed.
- **Files changed:** `apps/audit/actions.py`, `apps/core/storage.py`,
  `apps/documents/generation_artifacts.py`, `apps/documents/generation_rendering.py`,
  `apps/documents/output_validation.py`, `apps/documents/registry.py`,
  `apps/documents/storage_keys.py`, `apps/documents/tests/test_generation_artifact_postgresql.py`,
  `apps/documents/tests/test_generation_artifacts.py`,
  `apps/documents/tests/test_generation_rendering.py`, `apps/documents/tests/test_registry.py`,
  `docs/tasks/LGD_001_TASKS.md`, and this execution log.
- **Deviations or blockers:** The first broad regression invocation named a nonexistent
  `apps/core/tests` path and collected no tests; the corrected application profile passed and is the
  result reported above. An initial PostgreSQL socket-style URL was rejected by the repository's
  complete-URL parser; the corrected isolated TCP profile passed. No implementation or local automated
  verification blocker remains. External CI and Word desktop review are not claimed.

## DOC-015 — Deliver confirmed generation through full and HTMX workflows

- **Completion date:** 2026-09-16
- **Outcome:** Added a server-authorized synchronous generation workflow with an explicit confirmation,
  a fresh random idempotency token, named case/type/template details, full-page fallback and narrowly
  targeted HTMX results. The view revalidates case, draft revision, registry contract and active
  template immediately before reservation and generation. Duplicate submissions reuse the same
  attempt; invalid forms return `422`, stale/unavailable state returns recoverable `409`, and durable
  generation failures return a safe result without losing the draft.
- **Incremental slices:** (1) confirmation and normal/HTMX success paths; (2) validation, conflict,
  failure, authorization, CSRF and archived-case recovery; and (3) busy, focus/live-region, network,
  responsive and no-JavaScript behavior.
- **Files:** `apps/documents/forms.py`, `apps/documents/urls.py`,
  `apps/documents/workflow_views.py`, `apps/documents/tests/test_generation_workflow_views.py`,
  `templates/documents/_document_draft_form.html`, `templates/documents/document_draft.html`,
  `templates/documents/_generation_result.html`, `templates/documents/generation_result.html`,
  `static/js/app.js`, `locale/vi/LC_MESSAGES/django.po`,
  `scripts/prepare_browser_test_database.py`, and `tests/browser/smoke.spec.js`.
- **Acceptance evidence:** Focused workflow tests cover full and fragment success, idempotent duplicate
  POST, preserved invalid values, stale draft/template conflicts, archived cases, anonymous/session
  behavior, permission denial, CSRF and recoverable artifact failure. Existing generation-service tests
  cover mapper, render, validation, storage and finalization failure transitions. Browser coverage
  exercises HTMX generation, JavaScript-disabled fallback, keyboard-visible status and responsive
  layouts. These provide the `DOC-015` portions of `AC-03`, `AC-08`, `AC-09`, `AC-11`, and
  `AC-17`–`AC-20`.
- **Migration:** None; Django reported no model drift.
- **Commit:** Not created; the user did not request commits.
- **Deviations or blockers:** None for `DOC-015`.

## DOC-016 — Generation history and retry seeding

- **Completion date:** 2026-09-16
- **Outcome:** Added a case-scoped, permission-protected, newest-first history selector with a
  bounded 25-row page and safe attempt metadata only. Full and HTMX views expose generated/failed
  state, actor/time/template/schema/filename and bounded failure summaries without snapshots, storage
  keys or exceptions. Failed-attempt retry is POST/CSRF-only and creates a distinct token and attempt;
  no GET mutates data and no finalized row is rewritten.
- **Incremental slices:** (1) safe bounded selector and full/fragment history; (2) authorized retry
  seeding and idempotency; and (3) empty, loading/network, conflict, responsive and no-JavaScript
  presentation.
- **Files:** `apps/documents/forms.py`, `apps/documents/history_views.py`,
  `apps/documents/selectors.py`, `apps/documents/urls.py`,
  `apps/documents/tests/test_generation_history_views.py`,
  `templates/documents/_generation_history.html`, `templates/documents/generation_history.html`,
  `static/js/app.js`, `locale/vi/LC_MESSAGES/django.po`,
  `scripts/prepare_browser_test_database.py`, and `tests/browser/smoke.spec.js`.
- **Verification:** The initial focused baseline passed 69 tests. The generation workflow/history
  profile now passes 25 tests; the broader generation reservation/artifact/view profile passes 83.
  Ruff lint and format, mypy over `apps config`, `Q-CSS`, message extraction/compilation, Django system
  checks and migration-drift checks pass. Exact `Q-TEST` passes 1,084 tests with 29 intentional profile
  skips at 93.63% branch coverage. The final isolated Playwright run passes all 83 browser tests.
- **Acceptance evidence:** Tests prove newest-first pagination, safe metadata, full/fragment response
  and `Vary` behavior, permission and cross-case denial, constant query count, immutable source attempts,
  and distinct retry tokens/rows. This supplies the history/retry portions of `AC-14`, `AC-18`, and
  `AC-20`. Successful rows now expose the reverse-resolved canonical download supplied by `DOC-017`;
  failed and in-progress rows do not expose a link.
- **Pre-existing/transient failures:** An initial browser run contacted a stale process on port 8000.
  A fresh isolated run then exposed an invalid synthetic DOCX fixture and insufficient activation
  candidates; both test-fixture defects were corrected. One intermediate HTMX assertion matched two
  headings and was scoped to its fragment. The final complete browser run is green.
- **Dependency resolution:** `DOC-017` now supplies the complete canonical endpoint before the history
  template exposes its reverse-resolved URL, resolving the previously documented dependency cycle
  without introducing a partial or unaudited download route.
- **Migration:** None. Existing case/reservation ordering indexes are used; the query-count profile did
  not justify another index.
- **Commit:** Not created; the user did not request commits.

## DOC-017 — Serve only authorized canonical stored artifacts

- **Completion date:** 2026-09-16
- **Outcome:** Added the canonical `GET /documents/generated/<uuid>/download/` endpoint. It authorizes
  the download permission and case object scope again at the service boundary, selects generated rows
  only, opens the server-owned private key, verifies exact byte size and SHA-256 before delivery, and
  serves the stored binary without re-rendering.
- **Security and headers:** Anonymous, missing-permission, guessed, cross-scope and non-generated
  attempts fail closed. Missing or modified artifacts return the same generic not-found response after
  a bounded failure audit. Successful responses use the official DOCX media type, `nosniff`, private
  no-store/no-cache controls, exact length, and an attachment value containing both a conservative
  ASCII fallback and RFC 5987 UTF-8 filename. The private storage still has no public URL.
- **Audit and privacy:** Every endpoint attempt records one generated-document download action with a
  success, failure or denied outcome. Events contain only actor/system marker, opaque attempt UUID and
  correlation ID—never filename, storage key, case payload, bytes or exception content.
- **Files:** `apps/audit/actions.py`, `apps/documents/downloads.py`,
  `apps/documents/download_views.py`, `apps/documents/urls.py`,
  `apps/documents/tests/test_generated_document_download.py`,
  `apps/documents/history_views.py`, `apps/documents/tests/test_generation_history_views.py`,
  `templates/documents/_generation_history.html`, and `locale/vi/LC_MESSAGES/django.po`.
- **Verification:** The pre-change history/artifact baseline passed 39 tests. The focused final
  download/history profile passed 18 tests; the broader generation reservation/artifact/workflow/
  history/download profile passed 92. `Q-PY`, `Q-DJ`, `Q-I18N`, and `Q-CSS` passed. Exact `Q-TEST`
  passed 1,093 tests with 29 intentional environment-profile skips at 93.69% branch coverage.
- **Acceptance evidence:** Exact stored bytes, content type, length, cache and attachment headers cover
  `AC-16`. Historical generated rows remain immutable and linked to their original bytes for `AC-14`.
  Authentication, permission, guessed UUID, failed-state and object-scope tests cover `AC-21`.
  Missing, size-mismatched and checksum-mismatched content is rejected and audited for `AC-22`.
- **Migration:** None; Django reported no model drift.
- **Commit:** Not created; the user did not request commits.
- **Deviations or blockers:** None. Browser download/open was not separately rerun because the task's
  required local gate is the focused stored-byte/header/integrity profile; the existing CP-DOC-H
  browser history profile remained unchanged apart from the ordinary canonical link.

## CP-DOC-H — Checkpoint closure

- **Completion date:** 2026-09-16
- **Status:** Local implementation and verification are complete for `DOC-015` through `DOC-017`;
  human checkpoint review is pending.
- **Incremental slices:** (1) establish the existing history/artifact baseline; (2) add failing
  authorization, IDOR, integrity, header, audit and history-link tests; (3) implement the complete
  canonical stored-artifact path and localized history affordance; and (4) run focused, broader and
  repository-wide regression gates with diff review between slices.
- **Acceptance evidence:** `AC-03`, `AC-08`, `AC-09`, `AC-11`, and `AC-17`–`AC-20` retain the existing
  `DOC-015` evidence. `DOC-016` proves newest-first safe history, immutable retries and recovery for
  `AC-14`, `AC-18`, and `AC-20`. `DOC-017` adds exact canonical delivery and filename headers for
  `AC-14`/`AC-16`, deny-by-default UUID/object authorization for `AC-21`, and pre-delivery checksum/
  size verification for `AC-22`.
- **Quality gates:** Focused 18/18 and broader 92/92 profiles passed. Ruff lint and format, mypy over
  `apps config`, Django checks and migration drift, message extraction/compilation, and the production
  CSS build passed. Exact `Q-TEST` passed 1,093 tests with 29 intentional environment-profile skips at
  93.69% branch coverage, above the 85% project threshold.
- **Security, privacy and scope:** No schema, legal wording, registry key, generation snapshot,
  artifact metadata, public storage configuration or dependency changed. No confidential value enters
  UI, audit metadata or logs. No test was weakened or suppressed, and no unrelated refactor was added.
- **Commit:** Not created; the user did not request commits.
- **Deviations or blockers:** No implementation or repository-local verification blocker remains.

## DOC-018 — Reconcile database and private template/artifact storage

- **Completion date:** 2026-09-16
- **Outcome:** Added an idempotent `reconcile_private_files` management command and focused service.
  It streams every referenced template and finalized artifact through bounded chunks, verifies exact
  size and SHA-256, inventories the configured private root, and emits a single bounded JSON summary.
  Missing, modified, unreadable, orphaned, unsafe, stale, or partially scanned storage fails closed
  without exposing storage keys, filenames, file content, user values, or exception details.
- **Cleanup safety:** The default and `--check` modes are read-only. The explicit
  `--cleanup-stale-staging` mode removes only regular application staging files with the exact
  immutable-stage name contract after a fixed 24-hour age threshold and an immediate type/age recheck.
  It never follows symlinks or deletes final orphans, templates, or artifacts, and repeated cleanup is
  idempotent.
- **Incremental slices:** (1) referenced-file streaming integrity checks and bounded command result;
  (2) full-root orphan/staging inventory, validated root and narrow cleanup; and (3) operator runbook,
  broader validation and checkpoint closure.
- **Files:** `apps/documents/reconciliation.py`,
  `apps/documents/management/commands/reconcile_private_files.py`, management package markers,
  `apps/documents/tests/test_private_file_reconciliation.py`,
  `docs/operations/private-file-reconciliation.md`, `docs/tasks/LGD_001_TASKS.md`, and this log.
- **Verification:** Focused reconciliation tests pass 25 tests at 98.29% branch coverage across the
  service and command. The broader document/storage profile passed 489 tests with 17 intentional
  environment-profile skips before the final error-path additions. Ruff lint/format and full mypy pass;
  Django system and migration-drift checks pass. Repository-wide gates are recorded in the CP-DOC-I
  closure below.
- **Acceptance evidence:** Missing and modified template/artifact tests plus operational JSON/nonzero
  command results cover `AC-22`. The runbook requires coordinated database/private-file restore,
  post-restore reconciliation, representative checksum/download verification, and recording against
  the eight-hour RTO and 24-hour RPO portions of `AC-24`.
- **Migration:** None; Django reported no model drift.
- **Commit:** Included in the CP-DOC-I implementation commit at the user's request.
- **Deviations or blockers:** The incremental skill's referenced standalone Definition of Done file is
  absent at `.agents/references/definition-of-done.md`; the repository's `AGENT.md` Definition of Done
  and task-specific gates were applied. No implementation blocker remains.

## CP-DOC-I — Checkpoint closure

- **Completion date:** 2026-09-16
- **Status:** Local implementation and verification are complete for `DOC-018`; human checkpoint
  review is pending.
- **Security and privacy:** The command validates the configured root, treats database/filesystem state
  as untrusted, rejects symlinks and special entries, performs no broad glob/delete, and discloses only
  fixed-category aggregate counts. It adds no dependency, endpoint, permission, schema, legal wording,
  public storage route, or sensitive telemetry.
- **Operational evidence:** The structured event answers whether the scan completed, its duration, the
  bounded finding counts, and whether stale staging files were removed. The runbook defines routine
  scheduling, alert conditions, quiescence, investigation, coordinated restore, and post-restore
  verification.
- **Quality gates:** Focused service/command coverage is 98.29%, above the 95% integrity-module target.
  Exact `Q-TEST` passes 1,118 tests with 29 intentional environment-profile skips at 93.85% branch
  coverage, above the 85% project threshold. Repository-wide Ruff lint and format, mypy over
  `apps config`, Django checks, migration drift, diff whitespace checks, command help discovery, and
  development-server startup pass. CSS, browser and message-catalog gates are not applicable because
  this checkpoint changes no UI, static asset, translated application copy, or HTTP workflow.
- **Commit:** Included in the CP-DOC-I implementation commit at the user's request.
