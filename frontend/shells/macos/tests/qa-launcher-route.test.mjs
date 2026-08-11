import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const launcher = resolve(root, "scripts/dev-run-macos.sh");
const urlPolicy = resolve(root, "scripts/qa-url-policy.mjs");
const validator = resolve(root, "../tools/validate-consumer-evidence.mjs");

function fixture() {
  const scratch = mkdtempSync(join(tmpdir(), "omi-macos-launcher-"));
  const fakeRoot = join(scratch, "core/shells/macos");
  const scripts = join(fakeRoot, "scripts");
  const bin = join(scratch, "bin");
  const dist = join(scratch, "dist");
  const actions = join(scratch, "actions.log");
  mkdirSync(scripts, { recursive: true });
  mkdirSync(bin, { recursive: true });
  mkdirSync(dist, { recursive: true });
  mkdirSync(join(scratch, "core/shells/tools"), { recursive: true });
  copyFileSync(launcher, join(scripts, "dev-run-macos.sh"));
  copyFileSync(urlPolicy, join(scripts, "qa-url-policy.mjs"));
  copyFileSync(validator, join(scratch, "core/shells/tools/validate-consumer-evidence.mjs"));
  writeFileSync(join(dist, "index.html"), "<!doctype html>");
  const writer = join(scratch, "write-result.mjs");
  writeFileSync(writer, `import { writeFileSync } from "node:fs";
const domains = ["memories","tasks","conversations","folders","listen","chat","settings"];
const [file, runId] = process.argv.slice(2);
const rows = domains.map((domain) => ({runId,shell:"macos",domain,fixture:"none",evidence:"rendered-semantic",observation:{route:domain,state:"ready",semantic:domain+":rendered",...(domain === "listen" ? {transcript:"Local transcription is connected."} : {})},shellTreeHash:"1".repeat(40),surfaceTreeHash:"2".repeat(40)}));
writeFileSync(file, JSON.stringify({schema:"omi.consumer-evidence.v1",runId,rows}));
`);
  writeFileSync(join(scripts, "run-shell.sh"), `#!/bin/bash
printf 'launch|query=%s|surface_url=%s|surface_path=%s|api=%s|run=%s|result=%s|width=%s|height=%s\n' \
  "\${OMI_SURFACE_QUERY-}" "\${OMI_SURFACE_URL-unset}" "\${OMI_SURFACE_PATH-unset}" \
  "\${OMI_API_BASE_URL-}" "\${OMI_RUN_CLIENT_ID-}" "\${OMI_CONSUMER_EVIDENCE_PATH-}" "\${OMI_NATIVE_VIEWPORT_WIDTH-}" "\${OMI_NATIVE_VIEWPORT_HEIGHT-}" >> "\$OMI_TEST_ACTION_LOG"
if [[ -n "\${OMI_SNAPSHOT_PATH:-}" ]]; then
  printf 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=' | base64 -D > "\$OMI_SNAPSHOT_PATH"
fi
if [[ -n "\${OMI_CONSUMER_EVIDENCE_PATH:-}" ]]; then
  node "\$OMI_TEST_WRITER" "\$OMI_CONSUMER_EVIDENCE_PATH" "\$OMI_RUN_CLIENT_ID"
fi
`);
  writeFileSync(join(bin, "curl"), `#!/bin/bash
printf 'curl|%s\n' "\$*" >> "\$OMI_TEST_ACTION_LOG"
if [[ "\$*" == *'-X POST'* ]]; then printf 'issued-token'; else printf '204'; fi
`);
  writeFileSync(join(bin, "security"), "#!/bin/bash\nexit 1\n");
  for (const executable of [
    join(scripts, "dev-run-macos.sh"),
    join(scripts, "run-shell.sh"),
    join(bin, "curl"),
    join(bin, "security"),
  ]) chmodSync(executable, 0o755);

  const environment = {
    ...process.env,
    PATH: `${bin}:${process.env.PATH}`,
    OMI_SURFACES_DIST: dist,
    OMI_BUILD_DIR: join(scratch, "build"),
    OMI_APP_NAME: "omi-on-launcher-test",
    OMI_API_TOKEN: "local-test-token",
    OMI_TEST_ACTION_LOG: actions,
    OMI_TEST_WRITER: writer,
  };
  for (const name of [
    "OMI_API_BASE_URL",
    "OMI_DEV_TOKEN_ISSUER_URL",
    "OMI_SURFACE_PORT",
    "OMI_SURFACE_URL",
    "OMI_SURFACE_PATH",
  ]) delete environment[name];

  return {
    scratch,
    launcher: join(scripts, "dev-run-macos.sh"),
    actions,
    environment,
    readActions: () => existsSync(actions) ? readFileSync(actions, "utf8") : "",
  };
}

test("macOS QA launcher freezes origin, URLs, and the seven evidence routes before actions", () => {
  // red-proof: append ::macos in the launcher or retain a prior host result;
  // the raw-run action log or pre-gate stale-file assertion fails.
  const source = readFileSync(launcher, "utf8");
  assert.match(source, /OMI_SURFACE_PORT:-5290/);
  assert.match(source, /home\|memories\|conversations\|tasks\|folders\|chat\|settings\|listen/);
  assert.doesNotMatch(source, /qa=(memories|tasks|chat)|rig=dev|4841/);
  assert.match(source, /--fixture/);

  const run = fixture();
  try {
    const invalidRoute = spawnSync(run.launcher, ["--route", "not-a-route"], {
      encoding: "utf8", env: run.environment,
    });
    assert.equal(invalidRoute.status, 2);
    assert.equal(run.readActions(), "");

    const wrongOrigin = spawnSync(run.launcher, ["--route", "chat"], {
      encoding: "utf8", env: { ...run.environment, OMI_SURFACE_PORT: "5291" },
    });
    assert.equal(wrongOrigin.status, 1);
    assert.equal(run.readActions(), "");

    const forbiddenApiVariants = [
      "https://api.omi.me",
      "http://API.OMI.ME",
      "https://api.omi.me:8443",
      "https://api.omi.me/path",
      "https://api.omi.me?query=1",
      "https://api.omi.me#fragment",
      "https://user:password@api.omi.me/private",
      "https://api.omi.me./",
      "not a URL",
      "ftp://127.0.0.1/token",
      "http://user:password@127.0.0.1:4851",
      "http://127.0.0.1:4851/path",
    ];
    for (const value of forbiddenApiVariants) {
      const result = spawnSync(run.launcher, ["--api", value, "--route", "chat"], {
        encoding: "utf8", env: run.environment,
      });
      assert.equal(result.status, 1, value);
      assert.doesNotMatch(`${result.stdout}${result.stderr}`, new RegExp(value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
      assert.equal(run.readActions(), "", value);
    }

    const forbiddenIssuerVariants = [
      "https://api.omi.me/token",
      "http://API.OMI.ME:8080/token?scope=dev#fragment",
      "https://user:password@api.omi.me./token",
      "not a URL",
      "file:///tmp/token",
    ];
    for (const value of forbiddenIssuerVariants) {
      const environment = { ...run.environment, OMI_DEV_TOKEN_ISSUER_URL: value };
      delete environment.OMI_API_TOKEN;
      const result = spawnSync(run.launcher, ["--api", "http://127.0.0.1:4851"], {
        encoding: "utf8", env: environment,
      });
      assert.equal(result.status, 1, value);
      assert.equal(run.readActions(), "", value);
    }

    const evidenceRoutes = ["memories", "conversations", "tasks", "folders", "chat", "settings", "listen"];
    for (const route of evidenceRoutes) {
      const result = spawnSync(run.launcher, ["--api", "HTTP://LOCALHOST:4851/", "--route", route], {
        encoding: "utf8", env: run.environment,
      });
      assert.equal(result.status, 0, `${route}: ${result.stderr}`);
    }
    let actions = run.readActions();
    for (const route of evidenceRoutes) {
      assert.match(actions, new RegExp(`launch\\|query=route=${route}&platform=desktop`));
    }
    assert.equal(actions.match(/^launch\|/gm)?.length, 7);
    assert.doesNotMatch(actions, /generation=platform/);

    const defaultHome = spawnSync(run.launcher, [], {
      encoding: "utf8", env: run.environment,
    });
    assert.equal(defaultHome.status, 0);
    actions = run.readActions();
    assert.match(actions, /launch\|query=route=home&platform=desktop.*\|api=http:\/\/127\.0\.0\.1:4851\|/);

    for (const [name, value] of [
      ["OMI_SURFACE_URL", "https://stale.example.invalid/"],
      ["OMI_SURFACE_PATH", "/?rig=dev"],
    ]) {
      const result = spawnSync(run.launcher, ["--api", "http://127.0.0.1:4851", "--route", "chat"], {
        encoding: "utf8", env: { ...run.environment, [name]: value },
      });
      assert.equal(result.status, 0, name);
    }
    const launches = run.readActions().trim().split("\n").filter((line) => line.startsWith("launch|"));
    for (const line of launches.slice(-2)) {
      assert.match(line, /surface_url=unset\|surface_path=unset/);
    }

    const evidence = join(run.scratch, "macos-consumer.json");
    writeFileSync(evidence, "stale success");
    const rejected = spawnSync(run.launcher, [
      "--route", "not-a-route", "--evidence-out", evidence, "--run-id", "raw-macos-run",
    ], { encoding: "utf8", env: run.environment });
    assert.equal(rejected.status, 2);
    assert.equal(existsSync(evidence), false, "a gate failure must remove prior host success");

    const nativeEvidence = spawnSync(run.launcher, [
      "--api", "http://127.0.0.1:4851", "--route", "chat",
      "--evidence-out", evidence, "--run-id", "raw-macos-run",
    ], { encoding: "utf8", env: run.environment });
    assert.equal(nativeEvidence.status, 0, nativeEvidence.stderr || nativeEvidence.stdout);
    assert.equal(JSON.parse(readFileSync(evidence, "utf8")).runId, "raw-macos-run");
    actions = run.readActions();
    const evidenceLaunch = actions.trim().split("\n").filter((line) => line.startsWith("launch|")).at(-1);
    assert.match(evidenceLaunch, /^launch\|query=route=chat&platform=desktop&generation=platform\|/);
    assert.equal(evidenceLaunch.match(/generation=platform/g)?.length, 1);
    assert.doesNotMatch(evidenceLaunch, /qa=|rig=dev/);
    assert.match(evidenceLaunch, /run=raw-macos-run\|result=.*macos-consumer\.json/);
    assert.doesNotMatch(evidenceLaunch, /raw-macos-run::macos/);
  } finally {
    rmSync(run.scratch, { recursive: true, force: true });
  }
});

test("macOS native fixture capture is offline, query-bound, and probe-waited", () => {
  const run = fixture();
  try {
    const output = join(run.scratch, "fixture.png");
    const result = spawnSync(run.launcher, [
      "--fixture", "memories-platform", "--state", "ready", "--theme", "dark",
      "--accessibility", "rtl", "--run-id", "fixture-mac-001", "--capture-out", output,
      "--viewport-width", "960", "--viewport-height", "671",
    ], { encoding: "utf8", env: { ...run.environment, OMI_API_TOKEN: "must-not-leak" } });
    assert.equal(result.status, 0, result.stderr || result.stdout);
    assert.equal(existsSync(output), true);
    const action = run.readActions();
    assert.match(action, /query=qa=memories-platform&polish=1&state=ready&theme=dark&platform=desktop&accessibility=rtl/);
    assert.match(action, /api=\|run=fixture-mac-001\|result=\|width=960\|height=671/);
    assert.doesNotMatch(`${result.stdout}${result.stderr}${action}`, /must-not-leak|OMI_API_TOKEN/);
    assert.match(readFileSync(resolve(root, "scripts/run-shell.sh"), "utf8"), /OMI_PROBE_EXIT/);
  } finally {
    rmSync(run.scratch, { recursive: true, force: true });
  }
});
