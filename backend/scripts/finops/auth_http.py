"""Authenticated HTTP that never follows redirects.

urllib's default redirect handler copies every header except content-length and
content-type onto the next request. A 3xx from a vendor would send the
credential to the Location host. Refuse every redirect before that copy.
Error text is a fixed label and never includes the request, the Location, or
the credential.
"""

from __future__ import annotations

import urllib.request


class RedirectRefused(Exception):
    """A 3xx was refused. The message is a static label."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RedirectRefused("authenticated redirect refused")


def build_opener(ssl_context=None):
    handlers = [NoRedirect()]
    if ssl_context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=ssl_context))
    return urllib.request.build_opener(*handlers)


def open_authenticated(request, timeout, ssl_context=None):
    return build_opener(ssl_context).open(request, timeout=timeout)
