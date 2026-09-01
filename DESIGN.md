---
name: Cross-Platform Administration Dashboard Design System
version: "1.0"
scope: "Framework-agnostic administration dashboards"
platforms:
  - responsive web
  - desktop webview or native shell
  - tablet
  - mobile
colors:
  primary:
    light: "#2563eb"
    dark: "#60a5fa"
    hover-light: "#1d4ed8"
    hover-dark: "#3b82f6"
  success:
    light: "#16a34a"
    dark: "#4ade80"
  danger:
    light: "#dc2626"
    dark: "#f87171"
  warning:
    light: "#d97706"
    dark: "#fbbf24"
  info:
    light: "#0284c7"
    dark: "#38bdf8"
  neutral:
    light: "#6b7280"
    dark: "#9ca3af"
text:
  strong-light: "#18181b"
  strong-dark: "#fafafa"
  body-light: "#27272a"
  body-dark: "#f4f4f5"
  muted-light: "#71717a"
  muted-dark: "#a1a1aa"
  placeholder-light: "#a1a1aa"
  placeholder-dark: "#71717a"
border:
  light: "#e4e4e7"
  dark: "#3f3f46"
background:
  screen-light: "#f8fafc"
  screen-dark: "#09090b"
  surface-light: "#ffffff"
  surface-dark: "#18181b"
  subtle-light: "#f1f5f9"
  subtle-dark: "#27272a"
typography:
  font-family: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
  base-size: "14px"
  base-line-height: "1.5"
spacing:
  unit: "4px"
  control-gap: "8px"
  group-gap: "16px"
  section-gap: "24px"
  section-padding: "24px"
radius:
  control: "6px"
  surface: "8px"
breakpoints:
  compact: "< 640px"
  medium: "640px–1023px"
  wide: ">= 1024px"
---

# Cross-Platform Administration Dashboard Specification

This document defines a portable design system and interaction specification for administration dashboards. It is intentionally independent of any language, framework, component library, rendering model, or icon package. Teams may implement it with server-rendered HTML, progressive enhancement, a client-side framework, a desktop shell, or native controls, provided the behavior and accessibility contracts remain consistent.

Framework-specific code, class names, and components belong in separate adapter documentation. This file is the product-level source of truth.

## 1. Design principles

### 1.1 Optimize for administrative work

- Prioritize clarity, scanability, predictable placement, and safe data entry over decorative effects.
- Keep common actions visible and place rare actions in an overflow menu.
- Preserve context during multi-step work. Return users to the same filters, sort, page, and scroll position where practical.
- Make system status explicit: loading, saving, saved, empty, offline, partial failure, and permission denied must have distinct states.
- Prefer progressive disclosure for advanced filters and uncommon fields.

### 1.2 Use portable semantic tokens

Application code should consume semantic tokens such as `color-primary`, `surface-default`, `text-muted`, and `space-4`, not framework palette names. Tokens may map to CSS custom properties, theme objects, design-system variables, or native platform resources.

The values in the front matter are defaults, not a dependency on Tailwind or any other utility framework. Brand themes may replace them if contrast and state differentiation are preserved.

### 1.3 Follow a 4px spacing grid

Use multiples of 4px for margins, padding, gaps, control heights, and layout offsets:

- 4px: tight icon or indicator spacing.
- 8px: label-to-control and icon-to-label spacing.
- 12px: compact action groups.
- 16px: related controls and grid gutters on compact screens.
- 24px: section spacing and default panel padding.
- 32px: large-screen gutters or major page divisions.

Exceptions are allowed for platform safe areas, one-device-pixel borders, and touch-target compliance.

### 1.4 Typography

- Use the system font stack with Inter as an optional first choice.
- Default body and data text: 14px with 1.5 line height.
- Page title: 24px, weight 600.
- Section title: 16px, weight 600.
- Labels and table headers: 12–14px, weight 500–600.
- Supporting text and badges: 12px; never reduce essential information below 12px.
- Do not rely on font weight or color alone to communicate state.

### 1.5 Theme support

- Support light, dark, and system-preference themes.
- Use theme tokens rather than hard-coded foreground/background pairs.
- Maintain at least WCAG 2.2 AA contrast for text and meaningful controls.
- Test high-contrast and forced-colors modes where the platform supports them.
- Persist an explicit theme choice without overriding the operating-system preference by default.

## 2. Responsive application shell

### 2.1 Top bar

The top bar is 56–64px high and contains, in priority order:

1. Navigation toggle on compact layouts.
2. Product or workspace identity.
3. Page-level global search, when available.
4. Notifications and background-job status.
5. Account and session actions.

It may be sticky, but it must not obscure focused elements, validation messages, or anchored content. Global search should expose its keyboard shortcut visually and remain usable without the shortcut.

### 2.2 Primary navigation

- Wide screens: a 240px sidebar, optionally collapsible to an icon rail.
- Medium screens: a collapsible sidebar or temporary drawer, based on available width.
- Compact screens: an off-canvas drawer closed by default.
- Preserve expanded groups and the collapsed state per user when appropriate.
- Mark the current destination programmatically, not by color alone.
- Trap focus only while a modal navigation drawer is open; restore focus to its trigger when closed.

### 2.3 Content region

- Use a centered, fluid container with 16px compact gutters, 24px medium gutters, and 32px wide gutters.
- Default forms to one column on compact screens.
- On wide screens, use a 2:1 layout only when secondary metadata benefits the task; otherwise use full width.
- Avoid horizontal page scrolling. Data grids may scroll within a labeled region when column reduction is not possible.
- Respect device safe-area insets in installed web apps and native shells.

### 2.4 Page header

Each page header should contain a title, optional concise description or breadcrumb, and the primary page action. On compact screens, actions may wrap beneath the title or move to an accessible overflow menu.

## 3. Foundations and components

### 3.1 Surfaces and sections

Sections group related information and may include a title, description, actions, and collapsible content.

- Default padding: 24px wide, 16px compact.
- Default vertical separation: 24px.
- Border: one device pixel using the neutral border token.
- Radius: 8px.
- Use elevation sparingly; borders are preferred for data-dense interfaces.
- Collapsible sections must expose expanded/collapsed state to assistive technology and remain operable by keyboard.

### 3.2 Buttons

| Size | Visual height | Minimum target | Typical use |
| --- | ---: | ---: | --- |
| Compact | 32px | 40 × 40px hit area | Dense table actions |
| Regular | 40px | 44 × 44px hit area | Forms, filters, dialogs |
| Large | 48px | 48 × 48px hit area | High-emphasis workflow action |

Button variants:

- Primary: one dominant action per region.
- Secondary: alternative or supporting action.
- Quiet: low-emphasis action with visible hover and focus states.
- Danger: destructive action; require confirmation when impact is difficult to reverse.

Use concise verb-first labels such as “Create record”, “Save changes”, “Export CSV”, and “Delete”. Labels may wrap on compact screens if necessary; never reduce font size or change to a smaller button merely to fit a translation. Icon-only buttons require an accessible name and a tooltip for sighted users.

### 3.3 Icons

- Use one icon family per product, but do not prescribe a library in this specification.
- Default sizes: 16px inline, 20px in regular controls, 24px in navigation.
- Maintain an 8px gap between an icon and its label.
- Use familiar symbols consistently. Do not use icons as the only signal for status or destructive intent.
- Decorative icons must be hidden from assistive technology; meaningful icons need an accessible label.

### 3.4 Status badges

Badges use a short text label plus a semantic color. Recommended mappings:

| Meaning | Examples | Token |
| --- | --- | --- |
| Success | Active, Completed, Shipped | `status-success` |
| Attention | Pending, In progress, On hold | `status-warning` |
| Information | New, Draft, Scheduled | `status-info` |
| Danger | Failed, Cancelled, Blocked | `status-danger` |
| Neutral | Archived, Unknown, Disabled | `status-neutral` |

Colors must remain distinguishable in both themes. Always include text; color alone is insufficient.

### 3.5 Forms

- Associate every control with a persistent visible label. Placeholder text is supplementary, not a label.
- Place helper text before validation text and bind both to the control programmatically.
- Validate on blur or submission unless immediate validation clearly helps; do not show errors before a user has interacted.
- Keep entered values after validation or server errors.
- Mark optional fields explicitly when most fields are required; otherwise mark required fields.
- Group related inputs with semantic field groups and legends.
- Use platform-appropriate input types, autocomplete attributes, and virtual keyboards.
- Do not disable submit controls merely because a form is incomplete; allow submission to reveal actionable validation unless duplicate submission is the risk.

Field layout spacing:

- Label to control: 8px.
- Control to helper/error text: 4–8px.
- Related controls: 16px.
- Field groups: 24px.

### 3.6 Form actions

Place actions in normal document flow beneath the form. A sticky action bar is acceptable for long forms only when it:

- does not cover content or validation messages;
- accounts for mobile safe areas and the on-screen keyboard;
- has a clear boundary from page content; and
- duplicates or remains linked to the canonical form actions.

Order actions consistently for the product and locale. Show an in-progress state, prevent accidental duplicate submission, and report success or failure in a live status region.

### 3.7 Tooltips and help

- Tooltips contain brief, non-essential help and appear on hover and keyboard focus.
- They must not contain interactive elements.
- Use inline helper text, disclosure panels, or documentation links for essential or detailed information.
- Do not hide required instructions exclusively behind hover.

## 4. Data lists and tables

### 4.1 Table toolbar

The toolbar may contain search, filters, saved views, column controls, export, and a create action. Keep the highest-frequency controls visible and move secondary controls into an overflow menu on compact screens.

- Search may be debounced locally or remotely and must communicate loading state.
- Active filters appear as removable chips with a clear-all action.
- Filters, sorting, and pagination should be reflected in the URL or another restorable navigation state when technically feasible.

### 4.2 Table structure

- Left-align text, right-align numeric and financial values, and use locale-aware formatting.
- Sorting controls must expose direction and be keyboard operable.
- Keep column headers concise and allow wrapping rather than truncating essential labels.
- Sticky headers and first columns are optional; test them with zoom and small viewports.
- Reserve zebra striping for long, dense tables. Row borders and hover highlighting are acceptable alternatives.
- Do not encode meaning solely through row color.

### 4.3 Compact-screen alternatives

Choose the behavior that best preserves the task:

1. Hide low-priority columns behind a row details disclosure.
2. Transform rows into labeled record cards.
3. Allow contained horizontal scrolling with a visible cue.

Never silently remove primary identifiers, status, or the main row action.

### 4.4 Selection and bulk actions

- Selecting rows reveals a bulk-action bar near the table toolbar.
- Announce the selection count and clarify whether “select all” means the visible page or the full filtered result set.
- Keep destructive bulk actions visually separate and confirm their scope.
- After completion, report successes, failures, and partial results instead of presenting partial failure as success.

### 4.5 Pagination and large datasets

Show the visible range, total when known, page navigation, and page-size choices such as 10, 25, 50, and 100. Cursor pagination or infinite loading is acceptable when page numbers are not meaningful, but keyboard access, back navigation, and position restoration must still work.

Use virtualization only for genuinely large datasets and verify compatibility with screen readers, browser find, selection, and row-height changes.

### 4.6 Empty, loading, and error states

- Empty state: explain why the list is empty and offer the next relevant action.
- Filtered empty state: offer to clear or adjust filters.
- Loading: preserve layout to reduce movement and expose a programmatic busy state.
- Error: retain prior data when safe, state what failed, and provide retry or recovery guidance.

## 5. Feedback, dialogs, and overlays

### 5.1 Notifications and alerts

- Use inline alerts for page-specific issues and transient notifications for completed background actions.
- Alerts include a concise title, helpful message, semantic icon, and recovery action when available.
- Do not auto-dismiss errors. Success messages may dismiss after enough time to read, but must also remain available in an activity log when operationally important.
- Announce asynchronous feedback without unexpectedly moving focus.

### 5.2 Dialogs

Use dialogs for focused decisions or short tasks. Use a full page or side panel for complex, multi-section workflows.

- Default maximum width: approximately 600–720px for standard dialogs.
- Constrain height to the viewport and scroll the dialog body, not the header or actions.
- Apply a backdrop that clearly separates the underlying interface without relying on an exact opacity.
- Move focus into the dialog, keep it within the modal, support Escape when safe, and return focus to the trigger.
- Destructive confirmation identifies the affected object and consequence. For unusually high-impact actions, add a stronger verification step.

### 5.3 Side panels

Side panels preserve page context for record previews, filters, and moderate editing tasks. They become full-screen on compact devices. Browser back behavior should close the panel when it represents a navigable state.

## 6. Interaction and data behavior

### 6.1 Progressive enhancement

Core navigation, reading, data entry, and submission should work with standard platform semantics. Client-side enhancement may add optimistic updates, inline editing, live filtering, transitions, and shortcuts, but must not weaken error recovery or accessibility.

### 6.2 Network and asynchronous operations

- Show progress for operations that are not immediate.
- Use optimistic updates only when reversal is reliable and failure is clearly communicated.
- Prevent duplicate mutations with idempotency or server-side safeguards, not only a disabled button.
- Handle offline, timeout, conflict, expired session, and partial-success states explicitly.
- For background exports or imports, show job status and provide a durable way to retrieve results.

### 6.3 Permissions and auditability

- Enforce authorization on the server or trusted backend; hidden UI is not a security boundary.
- Hide actions a user can never perform and disable actions only when explaining a temporary condition is useful.
- Confirm sensitive mutations and record audit details appropriate to the domain.
- Avoid exposing secrets, internal identifiers, or sensitive fields in URLs, logs, notifications, or client state.

### 6.4 Internationalization

- Support text expansion, right-to-left layout, locale-aware numbers and dates, plural rules, and time zones.
- Store timestamps in a canonical format and display the user’s relevant time zone.
- Do not concatenate translated fragments to build sentences.
- Allow button and navigation labels to wrap or reflow; do not shrink controls to accommodate translation.

## 7. Accessibility and input methods

- Target WCAG 2.2 AA.
- Support keyboard-only operation with a logical focus order and visible focus indicator.
- Prefer semantic elements and native control behavior before adding ARIA.
- Provide skip links or equivalent navigation landmarks.
- Ensure touch targets are at least 44 × 44px where space permits.
- Support pointer, touch, keyboard, screen reader, browser zoom to 200%, and text reflow to 400%.
- Respect reduced-motion preferences; animation must not be required to understand state.
- Avoid unexpected focus changes after filtering, validation, saving, or deleting.

## 8. Performance and resilience

- Prioritize useful content and primary controls in the initial render.
- Avoid layout shifts by reserving space for tables, charts, images, and loading indicators.
- Debounce high-frequency searches and cancel obsolete requests.
- Paginate, stream, or progressively load large datasets.
- Preserve unsaved form work during recoverable navigation or session interruption where feasible.
- Establish measurable budgets appropriate to the product for initial load, interaction latency, and data-grid response.

## 9. Cross-platform implementation contract

Every implementation must provide mappings for:

| Concern | Required mapping |
| --- | --- |
| Tokens | Colors, spacing, typography, radius, elevation, breakpoints |
| Components | Buttons, fields, sections, badges, tables, alerts, dialogs, navigation |
| States | Default, hover, focus, active, disabled, loading, error, empty, offline |
| Input | Pointer, touch, keyboard, assistive technology |
| Themes | Light, dark, system preference, high contrast where supported |
| Navigation | Deep links, back behavior, state restoration, unsaved changes |
| Data | Loading, optimistic update, validation, conflict, partial failure |
| Security | Authentication, authorization, CSRF/session protection, audit logging |
| Localization | Text expansion, RTL, dates, numbers, pluralization, time zones |

Adapter documentation may show concrete implementation examples, but it must reference these contracts and avoid redefining product behavior.

## 10. Review checklist

Before release, verify that:

- The dashboard works at compact, medium, and wide sizes without page-level horizontal scrolling.
- Primary workflows work with keyboard and touch input.
- Light and dark themes meet contrast requirements.
- Loading, empty, error, offline, permission, and partial-success states are designed.
- Filters and navigation state can be restored where appropriate.
- Forms retain input after errors and expose actionable validation.
- Destructive actions communicate object, scope, and consequence.
- Authorization is enforced outside the presentation layer.
- Labels survive localization and text expansion.
- Reduced motion, zoom, screen readers, and high-contrast modes have been tested.
- Framework-specific details are isolated in adapters rather than embedded in this specification.

## 11. Do and do not

### Do

- Use semantic design tokens and native platform semantics.
- Keep primary actions predictable and secondary actions grouped.
- Design explicitly for asynchronous, empty, error, and partial-failure states.
- Preserve context and user input across recoverable failures.
- Test with real data density, long labels, narrow screens, and non-pointer input.

### Do not

- Couple the design system to one framework, component library, CSS utility set, or icon pack.
- Treat hidden controls as authorization.
- Rely on color, hover, or animation as the only way to communicate information.
- Place essential instructions only in tooltips.
- Force desktop tables unchanged onto compact screens.
- Use fixed overlays that cover content, focused controls, or the on-screen keyboard.
- Claim success when an asynchronous or bulk operation partially failed.
