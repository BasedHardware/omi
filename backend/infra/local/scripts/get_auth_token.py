#!/usr/bin/env python3
"""
Get Firebase Auth Token for API testing.

Usage:
    python get_auth_token.py --email your@email.com --password yourpassword

Requires FIREBASE_API_KEY environment variable or pass via --api-key
"""

import argparse
import os
import requests
import json


def get_auth_token(email: str, password: str, api_key: str) -> dict:
    """Sign in with email/password and return auth tokens."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"

    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }

    response = requests.post(url, json=payload)

    if response.status_code != 200:
        error = response.json().get("error", {})
        raise Exception(f"Auth failed: {error.get('message', 'Unknown error')}")

    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Get Firebase Auth Token")
    parser.add_argument("--email", "-e", required=True, help="User email")
    parser.add_argument("--password", "-p", required=True, help="User password")
    parser.add_argument("--api-key", "-k", help="Firebase API Key (or set FIREBASE_API_KEY env var)")

    args = parser.parse_args()

    api_key = args.api_key or os.getenv("FIREBASE_API_KEY")
    if not api_key:
        print("Error: FIREBASE_API_KEY not set. Use --api-key or set environment variable.")
        return

    try:
        result = get_auth_token(args.email, args.password, api_key)

        print("\n" + "=" * 60)
        print("AUTH TOKEN (idToken):")
        print("=" * 60)
        print(result.get("idToken", ""))
        print("\n" + "=" * 60)
        print("USER INFO:")
        print("=" * 60)
        print(f"UID: {result.get('localId', '')}")
        print(f"Email: {result.get('email', '')}")
        print(f"Expires in: {result.get('expiresIn', '')} seconds")
        print("\n" + "=" * 60)
        print("REFRESH TOKEN:")
        print("=" * 60)
        print(result.get("refreshToken", ""))

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
