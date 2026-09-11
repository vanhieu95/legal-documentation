# CASE-009 PostgreSQL query-plan evidence

Recorded: 2026-09-08

## Scope and representative data

The explicit `performance` test profile creates 100,000 synthetic `CaseRecord` rows in the
PostgreSQL test database. All values use the `SYN-` namespace. The measured query combines:

- active archive state;
- the `SYN-SCALE-099` identifier prefix across the allowlisted relational search fields;
- descending `updated_at` order with UUID as the deterministic tie-breaker.

Run:

```text
RUN_CASE_SCALE_TESTS=1 TEST_DATABASE_URL=postgresql://... pytest \
  apps/cases/tests/test_case_search.py::test_case_search_plan_at_100000_case_design_target
```

## Recorded plan

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` on PostgreSQL 18 reported:

- 100,000 base cases and 999 matches;
- `Bitmap Index Scan` on `case_record_state_stage_idx` for `status = active`;
- `Bitmap Heap Scan` of the matching active cases;
- bounded hash joins to court, participant, representation, and entity relations;
- in-memory quicksort for the deterministic result order;
- 2,210 shared-buffer hits and no shared-buffer reads;
- 207.595 ms execution time in the captured disposable-database run.

The ordinary selector boundary is capped at seven queries: three uncached central authorization
queries, one count, one page query, and two bounded prefetches. Accessing each returned case's
court, participant entities, and representative entities adds no queries.

## Index decision

No index is added by CASE-009. The existing composite `case_record_state_stage_idx` is selected
for the archive-state restriction, while the existing acceptance and updated-date indexes remain
available for their corresponding filter and sort paths.

The combined text predicate intentionally includes leading-wildcard Unicode containment and ORs
across related tables. A conventional B-tree functional index would not serve that whole query.
Effective containment acceleration would require PostgreSQL-specific trigram infrastructure and
changed operational/storage assumptions; adding an extension or changing search semantics is
outside the approved task. The measured 100,000-case plan remains comfortably below the
specified two-second list-page target, so an extra write/storage cost is not justified here.

SQLite is retained only for fast correctness feedback. Its case-folding and query planner are not
accepted as evidence for Vietnamese Unicode behavior, concurrency, or production performance;
the focused search and plan profiles therefore run on PostgreSQL.
