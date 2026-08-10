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
    const flutterCount = path.join(scratch, "flutter-count.txt");
    const curlCount = path.join(scratch, "curl-count.txt");
    writeFileSync(
      flutter,
      `#!/bin/bash\necho x >> "${flutterCount}"\nif [[ "$1" == "--version" ]]; then echo "Flutter 3.44.5"; exit 0; fi\nprintf '%s\\n' "$@" > "${argsFile}"\n`,
    );
    writeFileSync(curl, `#!/bin/bash\necho x >> "${curlCount}"\nprintf '200'\n`);
    chmodSync(flutter, 0o755);
    chmodSync(curl, 0o755);
    const env = {
      ...process.env,
      PATH: `${scratch}:${process.env.PATH}`,
      FLUTTER_BIN: flutter,
      NODE_BIN: "/usr/bin/true",
      OMI_API_TOKEN: "test-token-never-printed",
      OMI_RUN_CLIENT_ID: "run-launcher-proof",
      OMI_CONSUMER_EVIDENCE_PATH: path.join(scratch, "consumer-evidence.json"),
    };
    for (const route of ["memories", "conversations", "tasks", "folders", "chat", "settings", "listen"]) {
      const selected = spawnSync(
        "/bin/bash",
        [launcher, "--route", route, "--device", "simulator-proof"],
        { encoding: "utf8", env },
      );
      assert.equal(selected.status, 0, selected.stderr || selected.stdout);
      const args = readFileSync(argsFile, "utf8");
      assert.match(args, /--dart-define=SURFACE_MODE=scheme/);
      assert.match(args, new RegExp(`--dart-define=SURFACE_QUERY=route=${route}&platform=mobile`));
      assert.match(args, /--dart-define=OMI_RUN_CLIENT_ID=run-launcher-proof/);
      assert.match(args, /--dart-define=OMI_CONSUMER_EVIDENCE_PATH=.*consumer-evidence\.json/);
      assert.match(args, /--dart-define=OMI_CONSUMER_EVIDENCE_EXIT=true/);
      assert.doesNotMatch(args, /rig=dev|qa=|api\.omi\.me/);
      assert.doesNotMatch(`${selected.stdout}${selected.stderr}`, /test-token-never-printed/);
    }

    const defaultHome = spawnSync("/bin/bash", [launcher, "--device", "simulator-proof"], {
      encoding: "utf8",
      env,
    });
    assert.equal(defaultHome.status, 0, defaultHome.stderr || defaultHome.stdout);
    assert.match(readFileSync(argsFile, "utf8"), /SURFACE_QUERY=route=home&platform=mobile/);

    const unknown = spawnSync("/bin/bash", [launcher, "--route", "not-a-route"], { encoding: "utf8", env });
    assert.equal(unknown.status, 2);
    assert.match(unknown.stderr, /--route must be one of/);

    for (const productionUrl of [
      "https://api.omi.me/path",
      "https://api.omi.me:443",
      "https://api.omi.me?q=1",
      "HTTPS://API.OMI.ME/path",
      "https://api.omi.me./",
      "http://api.omi.me:8443/other",
    ]) {
      writeFileSync(flutterCount, "");
      writeFileSync(curlCount, "");
      const production = spawnSync(
        "/bin/bash",
        [launcher, "--api", productionUrl, "--device", "simulator-proof"],
        { encoding: "utf8", env },
      );
      assert.equal(production.status, 2, productionUrl);
      assert.match(production.stderr, /production api\.omi\.me is forbidden/);
      assert.equal(readFileSync(flutterCount, "utf8"), "", `Flutter invoked for ${productionUrl}`);
      assert.equal(readFileSync(curlCount, "utf8"), "", `curl invoked for ${productionUrl}`);
    }
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});
