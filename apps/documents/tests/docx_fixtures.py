from __future__ import annotations

from collections.abc import Iterable, Mapping
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

CONTENT_TYPES = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="rels" '
    b'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    b'<Default Extension="xml" ContentType="application/xml"/>'
    b'<Override PartName="/word/document.xml" '
    b'ContentType="application/vnd.openxmlformats-officedocument.'
    b'wordprocessingml.document.main+xml"/>'
    b"</Types>"
)
ROOT_RELS = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    b'officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    b"</Relationships>"
)
DOCUMENT_RELS = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""


def word_document(paragraphs: Iterable[Iterable[str]] = (("Synthetic document",),)) -> bytes:
    rendered_paragraphs = "".join(
        "<w:p>"
        + "".join(f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>' for text in runs)
        + "</w:p>"
        for runs in paragraphs
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{rendered_paragraphs}<w:sectPr/></w:body></w:document>"
    ).encode()


def minimal_docx(
    *,
    entries: Mapping[str, bytes] | None = None,
    extra_entries: Iterable[tuple[str, bytes]] = (),
    compression: int = ZIP_DEFLATED,
    encrypted_names: frozenset[str] = frozenset(),
    omit_names: frozenset[str] = frozenset(),
) -> bytes:
    package_entries = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": ROOT_RELS,
        "word/document.xml": word_document(),
        "word/_rels/document.xml.rels": DOCUMENT_RELS,
    }
    if entries:
        package_entries.update(entries)
    for name in omit_names:
        package_entries.pop(name, None)
    output = BytesIO()
    with ZipFile(output, "w", compression=compression) as archive:
        for name, content in (*package_entries.items(), *extra_entries):
            info = ZipInfo(name)
            info.compress_type = compression
            if name in encrypted_names:
                info.flag_bits |= 0x1
            archive.writestr(info, content)
    return output.getvalue()


def stored_docx(**kwargs: object) -> bytes:
    return minimal_docx(compression=ZIP_STORED, **kwargs)  # type: ignore[arg-type]


def relationships(*relationships_xml: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(relationships_xml)
        + "</Relationships>"
    ).encode()


def mark_first_entry_encrypted(package: bytes) -> bytes:
    altered = bytearray(package)
    local_header = altered.index(b"PK\x03\x04")
    central_header = altered.index(b"PK\x01\x02")
    for flag_offset in (local_header + 6, central_header + 8):
        flags = int.from_bytes(altered[flag_offset : flag_offset + 2], "little") | 0x1
        altered[flag_offset : flag_offset + 2] = flags.to_bytes(2, "little")
    return bytes(altered)


def replace_raw_entry_name(package: bytes, old: bytes, new: bytes) -> bytes:
    if len(old) != len(new):
        raise ValueError("Synthetic ZIP entry names must have equal lengths.")
    return package.replace(old, new)
