# Template validation boundaries

Template validation is a pure platform operation over untrusted bytes or a bounded binary
stream. It does not accept filesystem paths and does not require an HTTP request, user, case,
draft, or database record. Package validation must succeed before any placeholder/Jinja
validation and before any future rendering or activation workflow.

## OPC package limits

The canonical limits are `PackageValidationLimits` in `apps/documents/limits.py`:

| Resource | Limit |
| --- | ---: |
| Compressed upload | 10 MiB |
| ZIP entries | 512 |
| Total uncompressed data | 50 MiB |
| One uncompressed entry | 10 MiB |
| Compression ratio per entry | 100:1 |
| One XML part | 2 MiB |
| XML element depth | 64 |
| Returned findings | 50 |

The validator inspects entries in memory without extracting them. It normalizes ZIP and
relationship paths, rejects ambiguous or unsafe names, verifies OPC declarations and required
WordprocessingML parts, restricts relationship types and targets, and prohibits external
relationships, encryption, macros, ActiveX, OLE, embedded packages, executables, and other
binary content. XML is bounded and preflighted with DTD, entity, external-resource, and depth
handlers before a tree is built.

Results contain only stable error categories and bounded structural locations. Package bytes,
XML, filenames, relationship targets, parser exceptions, and placeholder values are not
included or logged. The implementation creates no temporary resources.

## Placeholder and Jinja boundary

The supported text-part allowlist is the main document, numbered headers and footers,
footnotes, and endnotes. Paragraph traversal also covers table rows and cells. Template syntax
in any other XML part or outside visible Word run text is rejected rather than ignored.

The validator reconstructs paragraph text while retaining run boundaries. A token crossing
runs is rejected, and differing run properties additionally identify partial styling. The
source package is never rewritten. `docxtpl` paragraph, row, cell, and run tags must occupy
their complete matching structural container.

Every dotted variable must be declared by the selected immutable registry contract. Required
variables must be present; filters and globals must be allowed by both the registry and the
fixed platform catalog. Loop sources must have the declared list kind. Imports, calls,
subscripts, unsafe or loop-local attributes, assignments, macros, includes, inheritance,
tests, and dynamic arithmetic or collection expressions are rejected.

The reusable environment has `StrictUndefined`, XML-safe autoescaping, no loader, no tests,
no default globals, fixed filter/global catalogs, and denies callable and attribute access.
Only source from a package that has just passed both validation stages may be compiled. Case
values are supplied afterward as data and are never reparsed as template source.

Jinja parsing is additionally bounded per supported part: 256 KiB of reconstructed source,
4,096 tokens, 4,096 characters per token, 32 nested control/expression levels, 8,192 AST
nodes, and AST depth 64. Exceeding any limit returns the stable `complexity_limit` category.
