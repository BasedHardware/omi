"""Read-projection defaults for a stored ``structured`` payload.

A v3 row written before its summary carries no ``category``, and a legacy row may carry no
``title``/``overview`` or a category value no longer in ``CategoryEnum``. The app's ``Structured``
model defaults all three, so a response model that requires them must project the same defaults
before validation. The stored document is never rewritten.
"""

from typing import Any

from models.conversation_enums import CategoryEnum

_UNSET_CATEGORY = object()


def project_structured_defaults(row: dict[str, Any], *, fold_invalid_category: bool = True) -> dict[str, Any]:
    """Return a copy of ``row`` whose ``structured`` carries the response-model defaults.

    ``fold_invalid_category`` decides what a stored value outside ``CategoryEnum`` becomes. The
    developer routes fold it to ``other``, matching the app model's ``set_category_default_on_error``.
    A surface that already skips malformed records (MCP) passes ``False`` so its own guard keeps
    deciding, and only a *missing* category is filled; such a row is returned unchanged.
    """
    structured = row.get('structured')
    if not isinstance(structured, dict):
        return row
    category = structured.get('category', _UNSET_CATEGORY)
    if category is _UNSET_CATEGORY or category is None:
        category = CategoryEnum.other
    else:
        try:
            category = CategoryEnum(category)
        except (ValueError, TypeError):
            # Enum lookups raise TypeError for unhashable stored values (list/dict), not ValueError.
            if not fold_invalid_category:
                return row
            category = CategoryEnum.other
    return {
        **row,
        'structured': {
            **structured,
            'title': structured.get('title') or '',
            'overview': structured.get('overview') or '',
            'category': category,
        },
    }
