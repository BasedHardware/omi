from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    forbidden_paths = [
        ROOT / "omiGlass/firmware/src/ota.cpp",
        ROOT / "omiGlass/firmware/src/ota.h",
    ]
    forbidden_tokens = [
        '#include "ota.h"',
        "OTA_SERVICE_UUID",
        "ota_handle_command",
        "ota_loop()",
        "WiFiClientSecure",
        "setInsecure",
        "HTTPClient",
        "Update.begin",
        "Update.end",
    ]
    sources = (ROOT / "omiGlass/firmware/src").glob("*")
    failures = [
        str(path.relative_to(ROOT)) for path in forbidden_paths if path.exists()
    ]
    for path in sources:
        if path.suffix not in {".cpp", ".h"}:
            continue
        text = path.read_text(encoding="utf-8")
        failures.extend(
            f"{path.relative_to(ROOT)}: {token}"
            for token in forbidden_tokens
            if token in text
        )
    if failures:
        print(
            "OmiGlass OTA must remain removed until authenticated artifact verification exists:"
        )
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
