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
