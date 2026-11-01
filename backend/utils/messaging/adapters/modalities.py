"""Small provider-neutral transformations of untrusted chat evidence."""

import unicodedata


def emoji_only(text):
    text = text.strip()
    return (
        bool(text)
        and any(ord(c) >= 0x2300 for c in text)
        and all(
            c.isspace() or unicodedata.category(c) in ('So', 'Sk', 'Mn', 'Me', 'Cf') or c in '0123456789#*'
            for c in text
        )
    )


def location_text(location, venue=None):
    venue = venue or {}
    return (
        'Shared location (untrusted data): '
        + str(location.get('latitude', ''))[:40]
        + ','
        + str(location.get('longitude', ''))[:40]
        + ' '
        + str(venue.get('title', venue.get('name', '')))[:300]
        + ' '
        + str(venue.get('address', ''))[:500]
    ).strip()
