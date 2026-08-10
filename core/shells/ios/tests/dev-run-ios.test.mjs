import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const launcher = path.join(here, "../scripts/dev-run-ios.sh");

test("the iOS QA launcher selects only a closed local-origin production route", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-ios-launcher-"));
  try {
    const argsFile = path.join(scratch, "flutter-args.txt");
    const flutter = path.join(scratch, "flutter");
    const curl = path.join(scratch, "curl");
    writeFileSync(
      flutter,
      `#!/bin/bash\nif [[ "$1" == "--version" ]]; then echo "Flutter 3.44.5"; exit 0; fi\nprintf '%s\\n' "$@" > "${argsFile}"\n`,
    );
    writeFileSync(curl, "#!/bin/bash\nprintf '200'\n");
    chmodSync(flutter, 0o755);
    chmodSync(curl, 0o755);
    const env = {
      ...process.env,
      PATH: `${scratch}:${process.env.PATH}`,
      FLUTTER_BIN: flutter,
      NODE_BIN: "/usr/bin/true",
      OMI_API_TOKEN: "test-token-never-printed",
      OMI_RUN_CLIENT_ID: "run-launcher-proof",
    };
    const selected = spawnSync(
      "/bin/bash",
      [launcher, "--route", "chat", "--device", "simulator-proof"],
      { encoding: "utf8", env },
    );
    assert.equal(selected.status, 0, selected.stderr || selected.stdout);
    const args = readFileSync(argsFile, "utf8");
    assert.match(args, /--dart-define=SURFACE_MODE=scheme/);
    assert.match(args, /--dart-define=SURFACE_QUERY=route=chat&platform=mobile/);
    assert.match(args, /--dart-define=OMI_RUN_CLIENT_ID=run-launcher-proof/);
    assert.doesNotMatch(args, /rig=dev|qa=|api\.omi\.me/);
    assert.doesNotMatch(`${selected.stdout}${selected.stderr}`, /test-token-never-printed/);

    const unknown = spawnSync("/bin/bash", [launcher, "--route", "not-a-route"], { encoding: "utf8", env });
    assert.equal(unknown.status, 2);
    assert.match(unknown.stderr, /--route must be one of/);

    const production = spawnSync("/bin/bash", [launcher, "--api", "https://api.omi.me"], {
      encoding: "utf8",
      env,
    });
    assert.equal(production.status, 2);
    assert.match(production.stderr, /production api\.omi\.me is forbidden/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});
