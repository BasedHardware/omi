"""Minimal dependency-free Firestore REST helper (read-only).

Auth comes from :mod:`gcpauth` (the read-only bot profile), refreshed in-process,
so a long pull never dies on a 60-minute token expiry and no token is written to disk.
"""

import json, os, ssl, sys, time, urllib.request, urllib.error, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auth_http  # noqa: E402

if os.environ.get("FINOPS_AUTH") == "cloudrun":
    import cloudrun as gcpauth  # noqa: E402
else:
    import gcpauth  # noqa: E402

PROJECT = gcpauth.PROJECT
TOKEN = gcpauth.TOKEN

BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"


def token(force=False):
    return TOKEN.get(force=force)


_CTX = ssl.create_default_context()


def post(path, body, retries=5):
    url = BASE + path
    data = json.dumps(body).encode()
    last = None
    for i in range(retries):
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": "Bearer " + token(),
                "Content-Type": "application/json",
            },
        )
        try:
            with auth_http.open_authenticated(req, timeout=180, ssl_context=_CTX) as r:
                return json.loads(r.read().decode())
        except auth_http.RedirectRefused:
            raise RuntimeError("firestore redirect refused") from None
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode()[:4000]
            last = (e.code, body_txt)
            if e.code == 401 and i == 0:
                token(force=True)
                continue
            if e.code in (429, 500, 503, 504):
                time.sleep(2 * (i + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {body_txt}")
        except Exception as e:
            last = ("net", str(e))
            time.sleep(2 * (i + 1))
            continue
    raise RuntimeError(f"exhausted retries: {last}")


def get(path, params="", retries=5):
    url = BASE + path + params
    last = None
    for i in range(retries):
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token()})
        try:
            with auth_http.open_authenticated(req, timeout=180, ssl_context=_CTX) as r:
                return json.loads(r.read().decode())
        except auth_http.RedirectRefused:
            raise RuntimeError("firestore redirect refused") from None
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode()[:4000]
            last = (e.code, body_txt)
            if e.code == 401 and i == 0:
                token(force=True)
                continue
            if e.code in (429, 500, 503, 504):
                time.sleep(2 * (i + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {body_txt}")
        except Exception as e:
            last = ("net", str(e))
            time.sleep(2 * (i + 1))
            continue
    raise RuntimeError(f"exhausted retries: {last}")


def uid_hash(uid):
    return hashlib.sha256(uid.encode()).hexdigest()[:16]


def unwrap(v):
    """Firestore Value -> python."""
    if v is None:
        return None
    k = next(iter(v))
    if k == "nullValue":
        return None
    if k == "stringValue":
        return v[k]
    if k == "integerValue":
        return int(v[k])
    if k == "doubleValue":
        return float(v[k])
    if k == "booleanValue":
        return v[k]
    if k == "timestampValue":
        return v[k]
    if k == "arrayValue":
        return [unwrap(x) for x in v[k].get("values", [])]
    if k == "mapValue":
        return {kk: unwrap(vv) for kk, vv in v[k].get("fields", {}).items()}
    if k == "referenceValue":
        return v[k]
    if k == "geoPointValue":
        return v[k]
    if k == "bytesValue":
        return "<bytes>"
    return v[k]


def typename(v):
    if v is None:
        return "missing"
    k = next(iter(v))
    if k == "arrayValue":
        vals = v[k].get("values", [])
        inner = typename(vals[0]) if vals else "empty"
        return f"array<{inner}>"
    if k == "mapValue":
        return "map{" + ",".join(sorted(v[k].get("fields", {}).keys())) + "}"
    return k
