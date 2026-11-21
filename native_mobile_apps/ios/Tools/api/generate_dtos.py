"""`make api` / `make api-check`: upstream's Swift DTO generator over the spec the patched backend
serves (Tools/api/backend_patches.py), written to OmiNetwork's generated file.

Usage: generate_dtos.py <omi-repository> [--check]
"""

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backend_patches  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[2] / "Packages/OmiNetwork/Sources/OmiNetwork/Generated/OmiApi.generated.swift"


def main() -> int:
    upstream, check = Path(sys.argv[1]), "--check" in sys.argv[2:]
    generator = upstream / "backend/scripts/generate_swift_openapi_types.py"
    spec_ = importlib.util.spec_from_file_location("omi_swift_openapi_generator", generator)
    sw = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(sw)
    spec, patches = backend_patches.apply(json.loads(Path(sw.DEFAULT_SPEC_PATH).read_text(encoding="utf-8")))
    label = sw.source_label_for_path(Path(sw.DEFAULT_SPEC_PATH)) + "".join(f" + docs/backend-patches/{p}" for p in patches)
    generated = sw.generate(spec, label)
    if check:
        if OUTPUT.read_text(encoding="utf-8") != generated:
            print(f"{OUTPUT.name} is out of date. Run: make api", file=sys.stderr)
            return 1
        return 0
    OUTPUT.write_text(generated, encoding="utf-8")
    print(f"wrote {OUTPUT.name} ({len(patches)} backend patch{'es' if len(patches) != 1 else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
