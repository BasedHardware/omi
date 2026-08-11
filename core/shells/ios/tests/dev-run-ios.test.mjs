import assert from "node:assert/strict";
import { chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const originalLauncher = path.join(here, "../scripts/dev-run-ios.sh");
const originalValidator = path.join(here, "../../tools/validate-consumer-evidence.mjs");

test("the iOS QA launcher selects only a closed local-origin production route", () => {
  // red-proof: pass the host result path as a Dart define or skip either stale
  // deletion; the fake container/build/timeout cases fail independently.
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-ios-launcher-"));
  try {
    const fakeRoot = path.join(scratch, "core/shells/ios");
    const launcher = path.join(fakeRoot, "scripts/dev-run-ios.sh");
    const fakeApp = path.join(fakeRoot, "app");
    const container = path.join(scratch, "container");
    mkdirSync(path.dirname(launcher), { recursive: true });
    mkdirSync(fakeApp, { recursive: true });
    mkdirSync(path.join(scratch, "core/shells/tools"), { recursive: true });
    mkdirSync(path.join(fakeRoot, "tools"), { recursive: true });
    mkdirSync(path.join(container, "Documents"), { recursive: true });
    copyFileSync(originalLauncher, launcher);
    copyFileSync(originalValidator, path.join(scratch, "core/shells/tools/validate-consumer-evidence.mjs"));
    writeFileSync(path.join(fakeRoot, "tools/build-surfaces-bundle.mjs"), "");
    chmodSync(launcher, 0o755);
    const argsFile = path.join(scratch, "flutter-args.txt");
    const flutter = path.join(scratch, "flutter");
    const curl = path.join(scratch, "curl");
    const flutterCount = path.join(scratch, "flutter-count.txt");
    const curlCount = path.join(scratch, "curl-count.txt");
    const simctlLog = path.join(scratch, "simctl.log");
    const xcrun = path.join(scratch, "xcrun");
    const node = path.join(scratch, "node");
    const nativeResult = path.join(scratch, "native-result.json");
    const invalidNativeResult = path.join(scratch, "invalid-native-result.json");
    const domains = ["memories", "tasks", "conversations", "folders", "listen", "chat", "settings"];
    writeFileSync(nativeResult, JSON.stringify({
      schema: "omi.consumer-evidence.v1",
      runId: "run-launcher-proof",
      rows: domains.map((domain) => ({
        runId: "run-launcher-proof", shell: "ios", domain, fixture: "none",
        evidence: "rendered-semantic",
        observation: { route: domain, state: "ready", semantic: `${domain}:rendered`, ...(domain === "listen" ? { transcript: "Local transcription is connected." } : {}) },
        shellTreeHash: "1".repeat(40), surfaceTreeHash: "2".repeat(40),
      })),
    }));
    writeFileSync(invalidNativeResult, JSON.stringify({ schema: "wrong", runId: "run-launcher-proof", rows: [] }));
    writeFileSync(
      flutter,
      `#!/bin/bash\necho x >> "${flutterCount}"\nif [[ "$1" == "--version" ]]; then echo "Flutter 3.44.5"; exit 0; fi\nprintf '%s\\n' "$@" > "${argsFile}"\nif [[ "$1" == "build" && "\${OMI_TEST_FAIL_BUILD:-}" == "1" ]]; then exit 9; fi\nif [[ "$1" == "build" ]]; then mkdir -p "${fakeApp}/build/ios/iphonesimulator/Runner.app"; fi\n`,
    );
    writeFileSync(curl, `#!/bin/bash\necho x >> "${curlCount}"\nprintf '200'\n`);
    writeFileSync(node, `#!/bin/bash\nif [[ "$1" == *validate-consumer-evidence.mjs ]]; then exec "${process.execPath}" "$@"; fi\nexit 0\n`);
    writeFileSync(xcrun, `#!/bin/bash
printf '%s\n' "$*" >> "${simctlLog}"
if [[ "$1 $2" == "simctl get_app_container" ]]; then printf '%s\n' "${container}"; exit 0; fi
if [[ "$1 $2" == "simctl launch" ]]; then
  [[ -e "${container}/Documents/omi-c3b3-consumer-run-launcher-proof.json" ]] && exit 71
  if [[ "\${OMI_TEST_INVALID_NATIVE_RESULT:-}" == "1" ]]; then
    cp "${invalidNativeResult}" "${container}/Documents/omi-c3b3-consumer-run-launcher-proof.json"
  elif [[ "\${OMI_TEST_NO_NATIVE_RESULT:-}" != "1" ]]; then
    cp "${nativeResult}" "${container}/Documents/omi-c3b3-consumer-run-launcher-proof.json"
  fi
fi
exit 0
`);
    chmodSync(flutter, 0o755);
    chmodSync(curl, 0o755);
    chmodSync(node, 0o755);
    chmodSync(xcrun, 0o755);
    const env = {
      ...process.env,
      PATH: `${scratch}:${process.env.PATH}`,
      FLUTTER_BIN: flutter,
      NODE_BIN: node,
      OMI_API_TOKEN: "test-token-never-printed",
      OMI_RUN_CLIENT_ID: "run-launcher-proof",
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
      assert.doesNotMatch(args, /generation=platform/);
      assert.match(args, /--dart-define=OMI_RUN_CLIENT_ID=run-launcher-proof/);
      assert.doesNotMatch(args, /OMI_CONSUMER_EVIDENCE/);
      assert.doesNotMatch(args, /rig=dev|qa=|api\.omi\.me/);
      assert.doesNotMatch(`${selected.stdout}${selected.stderr}`, /test-token-never-printed/);
    }

    const defaultHome = spawnSync("/bin/bash", [launcher, "--device", "simulator-proof"], {
      encoding: "utf8",
      env,
    });
    assert.equal(defaultHome.status, 0, defaultHome.stderr || defaultHome.stdout);
    assert.match(readFileSync(argsFile, "utf8"), /SURFACE_QUERY=route=home&platform=mobile/);
    assert.doesNotMatch(readFileSync(argsFile, "utf8"), /generation=platform/);

    const fixtureMode = spawnSync(
      "/bin/bash",
      [launcher, "--fixture", "conversations", "--device", "simulator-proof"],
      { encoding: "utf8", env },
    );
    assert.equal(fixtureMode.status, 0, fixtureMode.stderr || fixtureMode.stdout);
    assert.match(readFileSync(argsFile, "utf8"), /SURFACE_QUERY=qa=conversations&state=normal&platform=mobile/);
    assert.doesNotMatch(readFileSync(argsFile, "utf8"), /generation=platform/);

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

    const evidence = path.join(scratch, "ios-consumer.json");
    writeFileSync(flutterCount, "");
    writeFileSync(curlCount, "");
    writeFileSync(evidence, "prior one-sided success");
    const outputOnly = spawnSync("/bin/bash", [
      launcher, "--evidence-out", evidence,
    ], { encoding: "utf8", env });
    assert.equal(outputOnly.status, 2);
    assert.match(outputOnly.stderr, /--evidence-out and --run-id must be supplied together/);
    assert.equal(existsSync(evidence), false, "an output-only invocation must remove prior host success");
    assert.equal(readFileSync(flutterCount, "utf8"), "", "Flutter invoked for an output-only gate");
    assert.equal(readFileSync(curlCount, "utf8"), "", "curl invoked for an output-only gate");

    const runOnly = spawnSync("/bin/bash", [
      launcher, "--run-id", "run-launcher-proof",
    ], { encoding: "utf8", env });
    assert.equal(runOnly.status, 2);
    assert.match(runOnly.stderr, /--evidence-out and --run-id must be supplied together/);
    assert.equal(existsSync(evidence), false, "a run-only invocation cannot restore prior host success");
    assert.equal(readFileSync(flutterCount, "utf8"), "", "Flutter invoked for a run-only gate");
    assert.equal(readFileSync(curlCount, "utf8"), "", "curl invoked for a run-only gate");

    writeFileSync(evidence, "prior success");
    const rejected = spawnSync("/bin/bash", [
      launcher, "--route", "not-a-route", "--device", "simulator-proof",
      "--evidence-out", evidence, "--run-id", "run-launcher-proof",
    ], { encoding: "utf8", env });
    assert.equal(rejected.status, 2);
    assert.equal(existsSync(evidence), false, "a pre-build gate must remove prior host success");

    const selected = spawnSync("/bin/bash", [
      launcher, "--route", "chat", "--device", "simulator-proof",
      "--evidence-out", evidence, "--run-id", "run-launcher-proof",
    ], {
      encoding: "utf8",
      env: (() => {
        writeFileSync(
          path.join(container, "Documents/omi-c3b3-consumer-run-launcher-proof.json"),
          "prior container success",
        );
        return env;
      })(),
    });
    assert.equal(selected.status, 0, selected.stderr || selected.stdout);
    const args = readFileSync(argsFile, "utf8");
    assert.match(args, /^build\nios\n--simulator\n--debug/m);
    assert.match(args, /--dart-define=SURFACE_QUERY=route=chat&platform=mobile&generation=platform/);
    assert.equal(args.match(/generation=platform/g)?.length, 1);
    assert.doesNotMatch(args, /qa=|rig=dev/);
    assert.match(args, /--dart-define=OMI_RUN_CLIENT_ID=run-launcher-proof/);
    assert.match(args, /--dart-define=OMI_CONSUMER_EVIDENCE_FILENAME=omi-c3b3-consumer-run-launcher-proof\.json/);
    assert.doesNotMatch(args, new RegExp(evidence.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    assert.equal(JSON.parse(readFileSync(evidence, "utf8")).runId, "run-launcher-proof");
    const simctl = readFileSync(simctlLog, "utf8");
    assert.match(simctl, /simctl install simulator-proof/);
    assert.match(simctl, /simctl launch simulator-proof me\.omi\.proto\.omiWebviewProto/);
    assert.match(simctl, /simctl terminate simulator-proof me\.omi\.proto\.omiWebviewProto/);

    writeFileSync(evidence, "stale after success");
    const buildFailure = spawnSync("/bin/bash", [
      launcher, "--route", "chat", "--device", "simulator-proof",
      "--evidence-out", evidence, "--run-id", "run-launcher-proof",
    ], { encoding: "utf8", env: { ...env, OMI_TEST_FAIL_BUILD: "1" } });
    assert.equal(buildFailure.status, 9);
    assert.equal(existsSync(evidence), false, "build failure cannot retain host success");

    writeFileSync(evidence, "stale before timeout");
    const timeout = spawnSync("/bin/bash", [
      launcher, "--route", "chat", "--device", "simulator-proof",
      "--evidence-out", evidence, "--run-id", "run-launcher-proof",
    ], {
      encoding: "utf8",
      env: {
        ...env,
        OMI_TEST_NO_NATIVE_RESULT: "1",
        OMI_CONSUMER_EVIDENCE_WAIT_SECONDS: "1",
      },
    });
    assert.equal(timeout.status, 124, timeout.stderr || timeout.stdout);
    assert.equal(existsSync(evidence), false, "timeout cannot retain host success");

    writeFileSync(evidence, "stale before invalid native result");
    const invalidNative = spawnSync("/bin/bash", [
      launcher, "--route", "chat", "--device", "simulator-proof",
      "--evidence-out", evidence, "--run-id", "run-launcher-proof",
    ], { encoding: "utf8", env: { ...env, OMI_TEST_INVALID_NATIVE_RESULT: "1" } });
    assert.equal(invalidNative.status, 1, invalidNative.stderr || invalidNative.stdout);
    assert.match(invalidNative.stderr, /invalid native consumer evidence: wrong schema/);
    assert.equal(existsSync(evidence), false, "invalid native result cannot retain host success");
    assert.equal(
      existsSync(path.join(container, "Documents/omi-c3b3-consumer-run-launcher-proof.json")),
      false,
      "invalid native result is removed from the simulator container",
    );
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});
