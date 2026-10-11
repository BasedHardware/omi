"""Pure, stable provider identity keys shared by storage and admission."""

import json
from hashlib import sha256


def key(*parts):
    return sha256(json.dumps(parts, separators=(',', ':')).encode()).hexdigest()
