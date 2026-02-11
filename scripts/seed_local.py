#!/usr/bin/env python3
"""Create a test user in the Firebase Auth emulator and print credentials.

Usage:
    python scripts/seed_local.py
"""

import json
import sys
import urllib.request
import urllib.error

FIREBASE_AUTH_EMULATOR = "http://localhost:9099"
PROJECT_ID = "demo-omi-local"

TEST_EMAIL = "test@omi.local"
TEST_PASSWORD = "testpassword123"


def create_user():
    """Create a test user via the Auth emulator REST API."""
    url = f"{FIREBASE_AUTH_EMULATOR}/identitytoolkit.googleapis.com/v1/accounts:signUp?key=fake-api-key"
    data = json.dumps({
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "returnSecureToken": True,
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read().decode())
        return result
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode())
        if body.get("error", {}).get("message") == "EMAIL_EXISTS":
            print("User already exists, signing in instead...")
            return sign_in()
        print(f"Error creating user: {json.dumps(body, indent=2)}", file=sys.stderr)
        sys.exit(1)


def sign_in():
    """Sign in to get a fresh ID token."""
    url = f"{FIREBASE_AUTH_EMULATOR}/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=fake-api-key"
    data = json.dumps({
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "returnSecureToken": True,
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Error signing in: {body}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    result = create_user()
    uid = result.get("localId")
    id_token = result.get("idToken")

    print()
    print("=" * 60)
    print("  Test User Created")
    print("=" * 60)
    print(f"  Email:    {TEST_EMAIL}")
    print(f"  Password: {TEST_PASSWORD}")
    print(f"  UID:      {uid}")
    print()
    print("  ID Token (for Authorization header):")
    print(f"  {id_token}")
    print()
    print("  Example API call:")
    print(f'  curl -H "Authorization: Bearer {id_token}" http://localhost:8080/v1/users/me')
    print("=" * 60)
