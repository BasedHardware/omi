#!/usr/bin/env python3
"""Reject iOS Swift null placeholders that can reach property-list defaults.

The allowed lines build JSON response dictionaries, never persisted defaults.
Any new JSON-only use needs an explicit review and allowlist entry.
"""

from pathlib import Path
import re
import sys


IOS_ROOT = Path(__file__).resolve().parents[1]
JSON_ONLY_NULL_LINES = {
    "Runner/AppDelegate.swift": {
        '"firebase_messaging_auto_init": info["FirebaseMessagingAutoInitEnabled"] ?? NSNull(),',
        '"firebase_crashlytics_collection": info["FirebaseCrashlyticsCollectionEnabled"] ?? NSNull(),',
        '"firebase_data_collection": info["FirebaseDataCollectionDefaultEnabled"] ?? NSNull()',
    },
    "Runner/Ble/OmiBleManager.swift": {
        '"counters_since": defaults.object(forKey: "ble_diagnostics_counters_since_\\(uuid)") ?? NSNull(),',
    },
}
OPTIONAL_ANY_COALESCE = re.compile(r"\bas\s+Any\?\s*\?\?")


def main() -> int:
    violations = []
    for path in sorted(IOS_ROOT.rglob("*.swift")):
        relative = str(path.relative_to(IOS_ROOT))
        if "Pods" in Path(relative).parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "NSNull()" in line and line.strip() not in JSON_ONLY_NULL_LINES.get(relative, set()):
                violations.append(f"{relative}:{number}: NSNull() needs a reviewed JSON-only exception; omit unknown defaults fields")
            if OPTIONAL_ANY_COALESCE.search(line):
                violations.append(f"{relative}:{number}: do not coalesce Optional<Any> into a defaults value")
    if violations:
        print("\n".join(violations), file=sys.stderr)
        return 1
    print("iOS UserDefaults plist-value guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
