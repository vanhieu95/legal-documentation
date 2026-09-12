# Document registry contract

The document registry is reviewed application code in `apps/documents/registry.py`. It describes
which document types the deployed application understands; it does not authorize a user and does
not assert that a valid active template exists. Permission checks and template-availability
selectors remain separate boundaries.

Each production registration must use a stable `vds-NN` key and include its official code,
Vietnamese name, optional English name, enabled state, schema version, Django form/formset
provider, context mapper, safe filename builder, placeholder definitions with value kinds,
filter/global allowlists, and minimal and representative synthetic fixture providers. Registry
construction fails during import if an entry is duplicate, incomplete, malformed, or inconsistent
with its fixtures. A post-processor is absent by default and may only be referenced by an explicit
name from the registry's reviewed allowlist.

Construction validates the minimal and representative form inputs, mapped placeholder names and
declared value kinds, display filenames, and every named formset using its stable default prefix.
Cleaned formset rows are passed to the mapper under that prefix. Providers still execute again
with runtime data, so upload and generation services must revalidate their outputs against the
same contract before use; the eager checks do not turn a provider into trusted request data.

The registry deliberately has no mapping loader, mutation method, import-path resolver, expression
evaluator, or database-defined form mechanism. Adding or changing a document type therefore
requires a reviewed code deployment. Request data may select an existing key for later validation,
but it cannot create a type, provider, global, filter, or post-processor.

`synthetic-platform-test` is the only non-production registration. It exists solely to prove the
document platform in Milestone 5 and must never count toward the 12 MVP VDS types or be represented
as an approved legal form.

Template bytes and lifecycle metadata do not belong in the registry. `TemplateVersion` stores
those facts with a server-generated private key under
`templates/<type-key>/<version>/<opaque-uuid>.docx`. The original filename is retained only as a
sanitized display value and is never used as a storage path.

PostgreSQL constraints enforce key, version, checksum, size, activation-metadata, uniqueness and
single-active-version invariants. A database history guard additionally requires the initial
`uploaded` state, permits only declared lifecycle transitions, freezes identity/file/approval and
completed-validation metadata, and rejects row deletion. Registry membership remains a code-level
invariant because a database constraint cannot safely call the deployed Python registry.

Validation reports are either empty while validation has not completed or use the fixed `v1`
shape: `schema_version`, `result`, `categories`, and `counts`. Categories and count keys are bounded
machine codes, not package excerpts, filenames, paths, stack traces, or user content.
