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
