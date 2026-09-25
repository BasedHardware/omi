#!/usr/bin/env python3
"""Static tripwire for the v0.12.356 stale subprocess credential incident.

Scoped to managed desktop agent credentials, not OAuth credentials belonging to
external harnesses. Request-scoped model_headers_result is the explicit interim
IPC exception until Swift owns the HTTP relay; it must never become cached state.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PATTERNS = {
    "credential environment assignment": re.compile(r'(?:env|environment)\s*(?:\.\s*OMI_(?:AUTH_TOKEN|API_KEY|BYOK_\w+)|\[\s*["\']OMI_(?:AUTH_TOKEN|API_KEY|BYOK_\w+)["\']\s*\])\s*='),
    "startup credential configuration": re.compile(r'\bauthToken\s*[?:=]'),
    "refresh-token IPC": re.compile(r'["\'](?:type|case)?["\']?\s*:?\s*["\']refresh_token["\']'),
    "refresh-driven restart": re.compile(r'\b(?:pendingTokenRefresh|updateAuthToken|ensureTokenRefreshTask)\b'),
}


def violations(text):
    return [name for name, pattern in PATTERNS.items() if pattern.search(text)]


def main():
    # Exercise every prohibited form alongside allowed per-request headers.
    bad = ['env.OMI_API_KEY = token', 'env["OMI_AUTH_TOKEN"] = token',
           'env["OMI_BYOK_OPENAI"] = key', 'authToken?: string',
           '"type": "refresh_token"', 'pendingTokenRefresh = true']
    assert all(violations(sample) for sample in bad)
    assert not violations('headers["Authorization"] = value; env.removeValue(forKey: "OMI_AUTH_TOKEN")')
    desktop = ROOT / 'desktop/macos'
    paths = [desktop / 'Desktop/Sources/Chat/AgentBridge.swift',
             desktop / 'Desktop/Sources/Chat/AgentRuntimeProcess.swift',
             desktop / 'agent/src/index.ts', desktop / 'agent/src/protocol.ts',
             desktop / 'agent/src/adapters/interface.ts', desktop / 'agent/src/adapters/pi-mono.ts']
    paths += list((desktop / 'pi-mono-extension').glob('*.ts'))
    errors = [(str(path.relative_to(ROOT)), violation) for path in paths if not path.name.endswith('.test.ts')
              for violation in violations(path.read_text())]
    for path, violation in errors:
        print(f'{path}: forbidden {violation}')
    if errors:
        return 1
    print('PASS: managed agent credentials remain request-scoped (static tripwire + self-tests)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
