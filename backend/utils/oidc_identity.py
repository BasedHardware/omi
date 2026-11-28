"""Mint a Google OIDC identity token for a service-to-service call.

Owns one thing: asking the metadata server (Workload Identity or the Cloud Run
service account) for an ID token scoped to an audience. It never reads exported
JSON keys or an interactive gcloud credential. Moved here from the deleted
legacy backfill worker client (SCA-2965) so Episodes intake keeps its caller.
"""


def identity_token(audience: str) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import fetch_id_token

    token = fetch_id_token(Request(), audience)
    if not isinstance(token, str) or not token:
        raise RuntimeError('Workload Identity did not return an ID token')
    return token
