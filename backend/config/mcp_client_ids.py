"""URL-form (CIMD) OAuth client_id detection.

Pure module (no imports) so both ``database`` and ``utils`` layers can consume
the same predicate without a database -> utils dependency. A URL-form client
id carries a path separator and is never a valid Firestore document id, so the
client lookup must branch on this shape before ``.document(client_id)`` — and
before any outbound metadata fetch — is attempted.
"""


def is_url_form_client_id(client_id: object) -> bool:
    return isinstance(client_id, str) and "/" in client_id
