#!/usr/bin/env python3
"""Compile current CV1 source with explicit host shims; never accesses hardware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New evidence directory; existing paths are refused")
    args = parser.parse_args()
    tests = Path(__file__).resolve().parent
    app = tests.parent
    fixtures = tests / "host"
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="omi-cv1-host-"))
    if args.output:
        output.mkdir(parents=True, exist_ok=False)
    compiler = shlex.split(os.environ.get("CC", "cc"))
    report = {"state": "running", "layer": "host C with explicit Zephyr/Opus/GATT shims",
              "hardware_access": False, "commands": [], "output": str(output)}
    inputs = [app / "src/lib/core" / name for name in ("codec.c", "codec.h", "config.h", "utils.h", "transport.c")]
    inputs += [app / "src" / name for name in ("diagnostics.c", "diagnostics.h", "diagnostics_packet.c")]
    inputs += [tests / "diagnostics_packet_test.c"]

    def digests():
        return {str(path.relative_to(app)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}

    def save():
        (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(name, command, expected=0):
        result = subprocess.run(command, cwd=output, capture_output=True, text=True, timeout=30)
        report["commands"].append({"name": name, "command": command, "exit_code": result.returncode,
                                   "expected_exit_code": expected, "stdout": result.stdout, "stderr": result.stderr})
        save()
        if result.returncode != expected:
            raise RuntimeError(name + " failed; see results.json")
        print("PASS " + name)
        return result

    try:
        if not compiler or not shutil.which(compiler[0]):
            raise RuntimeError("C compiler unavailable; install a compiler with UBSan support, or set CC")
        report["source_sha256"] = digests()
        flags = compiler + ["-std=c11", "-Wall", "-Wextra", "-fsanitize=undefined", "-fno-sanitize-recover=all"]
        shim = fixtures / "diagnostics-stubs"
        includes = ["-I" + str(shim), "-I" + str(app / "src")]
        run("diagnostics-object", flags + ["-Werror"] + includes + ["-c", str(app / "src/diagnostics.c"), "-o", str(output / "diagnostics.o")])
        (output / "clock.c").write_text("#include <stdint.h>\nint64_t test_uptime;\n")
        copied = output / "source/lib/core"
        copied.mkdir(parents=True)
        for name in ("codec.c", "codec.h", "config.h", "utils.h"):
            shutil.copyfile(app / "src/lib/core" / name, copied / name)
        shutil.copyfile(fixtures / "codec_regression.c", output / "codec_regression.c")
        run("codec-compile", flags + ["-DCONFIG_OMI_CODEC_OPUS=1", "-I" + str(fixtures / "codec-stubs"), "-I" + str(app / "src"),
                                      str(output / "codec_regression.c"), str(output / "clock.c"), str(output / "diagnostics.o"), "-o", str(output / "codec")])
        run("codec", [str(output / "codec")])
        cases = [("packet", [app / "src/diagnostics_packet.c", tests / "diagnostics_packet_test.c"]),
                 ("boundary", [app / "src/diagnostics.c", app / "src/diagnostics_packet.c", fixtures / "diagnostics_boundary_test.c"])]
        for name, sources in cases:
            run(name + "-compile", flags + ["-Werror", "-pedantic"] + includes + list(map(str, sources)) + ["-o", str(output / name)])
            run(name, [str(output / name)])
        transport = (app / "src/lib/core/transport.c").read_text()
        start = "/* One snapshot per connection."
        end = "static struct bt_gatt_attr diagnostics_service_attr"
        if transport.count(start) != 1 or transport.count(end) != 1:
            raise RuntimeError("Production diagnostics block moved; review extraction rather than use a stale copy")
        block = transport[transport.index(start):transport.index(end)]
        (output / "diagnostics_gatt_block.inc").write_text(block)
        shutil.copyfile(fixtures / "diagnostics_cache_regression.c", output / "cache_regression.c")
        run("coherent-cache-compile", flags + ["-Werror", "-pedantic", "-pthread"] + includes +
            [str(app / "src/diagnostics.c"), str(app / "src/diagnostics_packet.c"), str(output / "cache_regression.c"), "-o", str(output / "cache")])
        run("coherent-cache", [str(output / "cache")])
        rejected = run("EATT-negative", compiler + ["-std=c11", "-DCONFIG_BT_EATT=1", "-I" + str(app / "src"),
                                                    "-c", str(output / "cache_regression.c"), "-o", str(output / "eatt.o")], expected=1)
        if "Diagnostics long reads require a single ATT bearer" not in rejected.stderr:
            raise RuntimeError("Compile failed for a reason other than the expected EATT guard")
        report["source_unchanged"] = digests() == report["source_sha256"]
        if not report["source_unchanged"] or transport.count("diagnostics_reset_read_cache(conn);") != 2:
            raise RuntimeError("Source changed during tests or connection lifecycle reset hooks changed")
        report["state"] = "passed"
    except Exception as error:
        report.update(state="failed", error=str(error))
    save()
    print(str(output / "results.json"))
    return 0 if report["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
