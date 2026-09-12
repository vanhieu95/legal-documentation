from __future__ import annotations

from apps.documents.models import TemplateVersion
from apps.documents.registry import UnknownDocumentTypeKey, document_registry


def get_active_template(type_key: str) -> TemplateVersion | None:
    """Return the committed active version for an enabled deployed type."""
    try:
        registration = document_registry.get(type_key)
    except UnknownDocumentTypeKey:
        return None
    if not registration.enabled:
        return None
    return TemplateVersion.objects.filter(
        type_key=registration.key,
        status=TemplateVersion.Status.ACTIVE,
    ).first()
