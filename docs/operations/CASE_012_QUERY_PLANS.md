# CASE-012 dashboard query-plan evidence

Recorded: 2026-09-10

## Scope and budgets

The dashboard uses two case-data queries after applying the central `view_cases` permission and
case object policy:

- one conditional aggregate for active and archived counts;
- one projection of `id`, `internal_reference`, `status`, and `updated_at`, ordered by descending
  activity time and UUID, limited to five rows.

The selector boundary is capped at six queries including uncached authorization checks. The full
dashboard request is capped at 16 queries including session loading, authentication, navigation
permissions, both selector authorization boundaries, and template rendering. The number of
queries does not grow with the number of recent cases, and rendering the five activity items adds
no related-object queries.

## Recorded PostgreSQL plan

`EXPLAIN (ANALYZE, BUFFERS)` was run on PostgreSQL 18 against 10,000 wholly synthetic cases. The
bounded recent-activity query used a backward index scan on `case_record_updated_idx`, followed by
an incremental sort for the UUID tie-breaker and a five-row limit. It examined six index rows,
returned five rows, used 12 shared-buffer hits, 25 kB peak sort memory, and completed in 0.111 ms.

The combined active/archived aggregate used one sequential scan, as expected for totals over the
complete visible scope. It used 213 shared-buffer hits and completed in 1.775 ms. Timings describe
the captured disposable local environment and are evidence about plan shape rather than a
production latency guarantee.

## Index decision

No index is added by CASE-012. The existing updated-time index supports the bounded recent query.
An index cannot avoid reading the complete visible scope for exact active and archived totals, and
the measured aggregate does not justify additional write or storage cost. The focused PostgreSQL
test keeps the recent query plan inspectable, while fixed query-count tests guard against N+1
regressions in both the selector and rendered dashboard boundaries.
