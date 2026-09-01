# Agent Instructions — VDS Document Administration Application

## Mission

Build and maintain a secure, accessible Django administration application for Vietnamese civil-matter (`VDS`) document workflows. Authorized staff must be able to sign in, browse and search records, complete validated forms, and export accurate `.docx` documents from approved templates, including forms `01-VDS` through `33-VDS`.

Treat this file as the project-wide source of truth. More specific instructions in `.cursor/rules/*.mdc` apply to matching files. If an instruction conflicts with an explicit user request, follow the user request and record the trade-off.

## Product Boundaries

- This is a server-rendered, progressively enhanced application—not a single-page application.
- The UI is a cross-platform administration dashboard for responsive web, desktop/native shells, tablets, and mobile. Do not couple the design to Filament or another vendor-specific admin framework.
- Authentication, authorization, validation, and business rules always execute on the server.
- JavaScript enhances usability; core create, edit, view, and export workflows must remain understandable and recoverable without it.
- Do not add public registration, a REST/GraphQL API, Celery, Redis, WebSockets, a frontend framework, or cloud storage unless a concrete requirement justifies it.

## Approved Stack

- Python and Django
- PostgreSQL in production; SQLite may be used for lightweight local development and tests when compatible
- Django templates and forms
- HTMX for server-driven partial updates
- Alpine.js for small, local UI state only
- Tailwind CSS for styling
- `docxtpl` for rendering Word templates
- `python-docx` for narrowly scoped inspection or post-processing that `docxtpl` cannot handle
- `pytest`, `pytest-django`, and project-configured quality tools

Use the versions already pinned by the repository. When adding a dependency, choose a currently supported version, pin it through the existing dependency workflow, explain why it is needed, and avoid duplicating standard-library or Django functionality.

## Architecture

Prefer a conventional Django project with focused apps and explicit boundaries:

- `core`: shared primitives, base templates, common validators, and utilities
- `accounts`: authentication, staff profiles, roles, and permissions
- `cases`: courts, cases/matters, parties, representatives, and related domain data
- `documents`: document definitions, drafts, template rendering, generated-file metadata, and downloads
- `audit`: append-only records for security- and document-relevant actions, if not kept within the owning app

Adapt names to an established repository rather than reorganizing working code solely to match this example.

### Dependency Direction

- Views coordinate HTTP concerns; they do not contain document-generation or complex domain logic.
- Django forms validate and normalize user input.
- Services perform multi-model writes, workflow transitions, and document generation.
- Selectors/query helpers encapsulate reused or non-trivial read queries.
- Models enforce durable invariants with field constraints, database constraints, and small domain methods.
- Templates present data and must not perform business logic.
- External side effects occur after validation and, when coupled to database writes, after a successful transaction.

Avoid generic `utils.py`, oversized “service” modules, hidden signals for primary workflows, and premature repository-pattern abstractions over the Django ORM.

## VDS Data and Form Model

Use normalized reusable domain concepts from the 33-form inventory, including namespaces such as `court.*`, `document.*`, `case.*`, `party.*`, `search.*`, `decision.*`, `appeal.*`, and `fee.*`.

Use a hybrid model:

- Persist shared, searchable business entities—court, case, party, representative, decision, and similar concepts—in typed relational models.
- Persist document-specific draft values in a versioned payload only when they do not justify reusable relational fields.
- Every payload must be validated by a versioned Django form or schema before storage or rendering. Never treat arbitrary JSON as trusted input.
- Store stable document type/template keys and explicit schema/template versions. Do not use display labels as identifiers.
- Keep field-to-template-variable mappings explicit and testable. Do not infer mappings from human-readable Vietnamese labels.
- Preserve an immutable input snapshot and template version for every finalized export so the generated document can be reproduced and audited.
- Use deliberate workflow states such as `draft`, `ready`, `generating`, `generated`, and `failed`; enforce valid transitions in one service boundary.

Do not create one database table per Word template unless its data has genuinely distinct lifecycle, constraints, and query needs.

## Django Implementation Rules

- Keep views thin and use class-based or function-based views consistently with the surrounding app.
- Use `ModelForm` or `Form` for all writes. Never build model writes directly from `request.POST`.
- Wrap multi-record writes in `transaction.atomic()`.
- Use `select_related()` and `prefetch_related()` deliberately; verify query counts on list/detail pages.
- Paginate unbounded lists and debounce search inputs.
- Use timezone-aware datetimes and Django timezone helpers.
- Use `TextChoices`/`IntegerChoices` for finite persisted states and database constraints for important invariants.
- Keep migrations small, deterministic, reversible where practical, and committed with model changes. Review data migrations for production volume.
- Configure Django admin as an operational aid, not as the product UI.
- Prefer explicit URLs with stable names and reverse them; never hard-code internal paths in templates or Python.
- Preserve user input and show field-level errors after failed submissions.

## HTMX and Alpine.js

- Every HTMX endpoint returns either a documented partial or a full-page response when directly visited where practical.
- Give partial templates a leading underscore and keep them beside the owning feature, for example `documents/_draft_form.html`.
- Use `hx-target`, `hx-swap`, indicators, and history behavior explicitly. Avoid replacing broad page regions when a narrow component is sufficient.
- Return appropriate HTTP status codes and render useful validation/error fragments; do not encode failure as a successful empty response.
- Send CSRF tokens through Django-supported mechanisms on all unsafe requests.
- Prevent duplicate submissions by disabling or marking the initiating action while a request is pending.
- Use Alpine.js only for ephemeral client state such as disclosure, tabs, focus, and lightweight previews.
- Do not duplicate authoritative data, permissions, validation, or workflow state in Alpine stores.
- Prefer custom events with clear names for the few places HTMX and Alpine must coordinate.

## UI and Accessibility

- Use Tailwind CSS and semantic design tokens; avoid scattered arbitrary colors and spacing values.
- Follow a 4px spacing grid, Inter with system fallbacks, and light/dark/system themes.
- Target WCAG 2.2 AA: semantic HTML, visible focus, full keyboard operation, labelled controls, useful error summaries, sufficient contrast, and reduced-motion support.
- Interactive targets must be at least 44×44 CSS pixels where feasible.
- Use a 56–64px top bar, an approximately 240px wide-screen sidebar, and a drawer/navigation pattern on compact screens.
- Use fluid gutters and a single-column form layout on compact screens.
- Tables must remain usable on narrow screens through responsive column prioritization, cards, or intentional horizontal scrolling.
- Show explicit loading, saving, success, empty, error, offline, and conflict states where relevant.
- Keep important page titles, context, and primary actions visible and consistent.
- Write user-facing copy in clear Vietnamese unless the product requirement says otherwise. Keep code identifiers and developer documentation in English.

## DOCX Generation

- Store approved `.docx` templates in a controlled, versioned location outside user-writable paths.
- Resolve templates from an allowlisted document-type registry; never accept a filesystem path from a request.
- Build rendering context in a dedicated function/service with typed or validated inputs.
- Use `docxtpl` as the primary renderer. Use `python-docx` only for explicit post-render changes and test those changes against representative documents.
- Normalize dates, names, court/case identifiers, currency, and optional values in Python before rendering.
- Escape or safely wrap user-provided content according to the template engine’s rules. Never allow user input to become template syntax.
- Preserve required Word formatting, headers, footers, tables, page breaks, fonts, and Vietnamese diacritics.
- Render to a unique temporary file or in-memory stream; clean up temporary files in `finally` blocks.
- Use sanitized download filenames and standards-compliant `Content-Disposition`, including UTF-8 filename support.
- Set the correct DOCX content type and require object-level download permission.
- Record success/failure metadata without logging confidential document content.
- For long-running exports, use a durable job record and explicit status UI. Add a worker queue only after measurement shows synchronous generation is insufficient.

## Security and Privacy

- Deny access by default. Enforce login plus model/object-level permissions in views and services; hiding a button is not authorization.
- Use Django’s CSRF, session, password-hashing, clickjacking, host validation, secure-cookie, and HTTPS protections as intended.
- Prevent IDOR by scoping every record lookup and download to the requesting user’s permissions.
- Validate uploaded template type, size, and structure if template upload is ever introduced; store it outside executable/static paths.
- Never commit secrets or place personal/legal data in logs, fixtures, screenshots, exception messages, or analytics.
- Treat exported documents and draft payloads as sensitive. Define retention, backup, deletion, and access-audit behavior explicitly.
- Audit sign-in-sensitive events, permission changes, template changes, workflow transitions, generation, download, and deletion with actor and timestamp.
- Keep audit history append-only for normal application users.

## Testing

Use a risk-based test pyramid:

- Unit tests for validators, formatting, schema/version rules, filename handling, and workflow transitions
- Model tests for constraints and permissions-related invariants
- Form tests for valid, invalid, optional, and Vietnamese Unicode input
- View tests for authentication, authorization, CSRF behavior, status codes, redirects, full-page responses, and HTMX partials
- Service/integration tests for atomic writes and DOCX generation
- Query-count tests for important list/detail screens
- A small number of end-to-end tests for sign-in → select record → complete form → export/download

For each supported document template, maintain at least:

- a minimal valid context fixture;
- a representative full context fixture;
- a render smoke test that opens the result as a ZIP/DOCX and verifies expected text and required parts;
- focused regression tests for tables, loops, optional paragraphs, page breaks, and post-processing when used.

Do not compare complete DOCX binary files byte-for-byte. Inspect document XML/text and structural parts, because metadata and ZIP ordering may vary.

## Quality Workflow

Before changing code:

1. Read this file, matching Cursor rules, nearby code, tests, dependency configuration, and any nested agent instruction file.
2. Restate the requested behavior and identify security, data-migration, template-version, and compatibility risks.
3. Make the smallest coherent change that follows existing patterns.

Before declaring completion:

1. Run the repository’s configured formatter, linter, type checker, and relevant tests.
2. Run the full test suite when practical; otherwise state exactly what was and was not run.
3. Run `python manage.py check` and `python manage.py makemigrations --check --dry-run` when Django models/settings are affected.
4. Verify both normal and HTMX response paths when an interactive view changes.
5. Render and inspect representative DOCX output when generation code or templates change.
6. Check keyboard behavior and responsive layouts when UI changes.
7. Review the diff for secrets, personal data, debug output, unrelated formatting churn, missing migrations, and missing tests.

Never claim a command passed unless it was executed successfully.

## Change Discipline

- Preserve existing behavior unless the task explicitly changes it.
- Do not modify generated files, vendored code, migrations already deployed, or approved Word templates casually.
- Do not silently rename template variables, persisted keys, URLs, permissions, or document states. Provide a compatible migration plan.
- Avoid speculative abstractions. Prefer clear duplication until a stable shared concept is demonstrated.
- Update documentation and sample environment files when configuration changes; never put real credentials in examples.
- Use comments for intent and constraints, not to narrate obvious code.
- Stop and ask when requirements affect legal wording, retention policy, permission boundaries, destructive migrations, or compatibility with existing template versions.

## Definition of Done

A change is complete only when the requested behavior works, server-side validation and authorization are enforced, relevant tests pass, accessibility and responsive behavior are preserved, document output is verified when applicable, migrations/configuration/docs are included, and remaining risks are clearly reported.
