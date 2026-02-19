import os

import firebase_admin
from firebase_admin import auth

_prod_auth_app = None


def init_prod_firebase_auth():
    """Initialize a secondary Firebase app for verifying prod Firebase tokens on the dev backend.

    When PROD_FIREBASE_PROJECT_ID is set (e.g. 'based-hardware'), this creates a second
    Firebase app that can verify tokens from the prod Firebase project. This allows the
    dev backend to accept requests from TestFlight users who authenticate against the
    prod Firebase project.

    Token verification only uses the project ID (to check aud/iss claims) and Google's
    public signing keys — no prod service account credentials are needed.
    """
    global _prod_auth_app
    prod_project_id = os.environ.get('PROD_FIREBASE_PROJECT_ID')
    if not prod_project_id:
        return

    try:
        default_app = firebase_admin.get_app()
        _prod_auth_app = firebase_admin.initialize_app(
            default_app.credential,
            options={'projectId': prod_project_id},
            name='prod-auth',
        )
        print(f"Initialized prod Firebase auth app for project: {prod_project_id}")
    except Exception as e:
        print(f"Warning: Failed to initialize prod Firebase auth app: {e}")


def verify_firebase_token(token: str) -> dict:
    """Verify a Firebase ID token, trying the default project first, then the prod project.

    Returns the decoded token dict.
    Raises the original exception if all verification attempts fail.
    """
    try:
        return auth.verify_id_token(token)
    except Exception as default_error:
        if _prod_auth_app is not None:
            try:
                return auth.verify_id_token(token, app=_prod_auth_app)
            except Exception:
                pass
        raise default_error
