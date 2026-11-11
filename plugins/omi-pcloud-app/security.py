"""Verify backend-issued, account-bound grants; UID hints never authorize."""

import hashlib
import json
import os

import jwt
from fastapi import HTTPException, Request

ISSUER = 'omi-plugin-transport/v1'


def signing_key() -> str:
    key = os.getenv('OMI_PLUGIN_SIGNING_KEY', '')
    if len(key.encode()) < 32 or not os.getenv('OMI_PLUGIN_APP_ID'):
        raise ValueError('Configure OMI_PLUGIN_APP_ID and a 32-byte OMI_PLUGIN_SIGNING_KEY')
    return key


def verify(token: str, scope: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            signing_key(),
            algorithms=['HS256'],
            audience=os.environ['OMI_PLUGIN_APP_ID'],
            issuer=ISSUER,
            options={'require': ['exp', 'iat', 'sub', 'jti', 'scope']},
        )
        if claims['scope'] != scope or not isinstance(claims['sub'], str) or not claims['sub']:
            raise ValueError('Wrong scope')
        return claims
    except ValueError:
        raise HTTPException(status_code=401, detail='Open pCloud settings again from your signed-in Omi app.')
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401, detail='This connection link is invalid or expired. Open it again from Omi.'
        )


def verify_delivery(request: Request, payload: dict, uid: str) -> dict:
    claims = verify(request.headers.get('X-Omi-Plugin-Authorization', ''), 'delivery')
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
    if (
        claims['sub'] != uid
        or claims.get('path') != request.url.path
        or claims.get('method') != 'POST'
        or claims.get('sha256') != hashlib.sha256(canonical).hexdigest()
    ):
        raise HTTPException(status_code=401, detail='The backup delivery identity or content did not match.')
    return claims
