# DOCX template authoring guide

Templates are versioned, code-contracted inputs. Authors should use a copy containing only
synthetic data while preparing or testing a template.

## Placeholders

- Enter each complete placeholder in one operation, with spaces inside the delimiters:
  `{{ document.title }}`.
- Apply formatting to the complete token. Do not partially style a placeholder or control tag.
- Do not split, paste fragments into, or otherwise edit only part of a token. Word can create
  separate XML runs even when text looks continuous.
- Use only variables and value kinds declared by the document registry. Required variables must
  appear; optional variables may be omitted.
- Use only the filters and globals explicitly approved by that registry contract. Calls,
  imports, subscripts, arbitrary attributes, and application objects are not supported.

## Loops, conditions, and structural tags

Keep ordinary loops and conditions within a complete compatible run. Repeated values must use
a registry-declared list as the loop source.

Follow the `docxtpl` container rules:

- `{%p ... %}` occupies its own paragraph.
- `{%tr ... %}` occupies its own table row.
- `{%tc ... %}` occupies its own table cell.
- `{%r ... %}` occupies its own run.

Put only one structural tag in each affected container. Opening and closing structural tags
therefore use separate containers. Do not put surrounding text in the same container.

## Validation lifecycle

The validator checks the main document, tables, numbered headers and footers, footnotes, and
endnotes. Template syntax in another part is rejected as unsupported. Unsupported run splitting
is rejected; the validator never silently repairs or rewrites the uploaded file.

Re-saving or changing an approved template creates a new immutable version. That version must
pass package, relationship, placeholder, Jinja, and run-boundary validation again before it can
be considered for activation or generation.
