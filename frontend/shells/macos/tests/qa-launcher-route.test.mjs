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

function fixture() {
  const scratch = mkdtempSync(join(tmpdir(), "omi-macos-launcher-"));
  const scripts = join(scratch, "scripts");
  const bin = join(scratch, "bin");
  const dist = join(scratch, "dist");
  const actions = join(scratch, "actions.log");
  mkdirSync(scripts, { recursive: true });
  mkdirSync(bin, { recursive: true });
  mkdirSync(dist, { recursive: true });
  copyFileSync(launcher, join(scripts, "dev-run-macos.sh"));
  copyFileSync(urlPolicy, join(scripts, "qa-url-policy.mjs"));
  writeFileSync(join(dist, "index.html"), "<!doctype html>");
  writeFileSync(join(scripts, "run-shell.sh"), `#!/bin/bash
printf 'launch|query=%s|surface_url=%s|surface_path=%s|api=%s\n' \
  "\${OMI_SURFACE_QUERY-}" "\${OMI_SURFACE_URL-unset}" "\${OMI_SURFACE_PATH-unset}" \
  "\${OMI_API_BASE_URL-}" >> "\$OMI_TEST_ACTION_LOG"
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
  const source = readFileSync(launcher, "utf8");
  assert.match(source, /OMI_SURFACE_PORT:-5290/);
  assert.match(source, /home\|memories\|conversations\|tasks\|folders\|chat\|settings\|listen/);
  assert.doesNotMatch(source, /qa=|rig=dev|--fixture|4841/);

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
      "http://user:password@127.0.0.1:4801",
      "http://127.0.0.1:4801/path",
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
      const result = spawnSync(run.launcher, ["--api", "http://127.0.0.1:4801"], {
        encoding: "utf8", env: environment,
      });
      assert.equal(result.status, 1, value);
      assert.equal(run.readActions(), "", value);
    }

    const evidenceRoutes = ["memories", "conversations", "tasks", "folders", "chat", "settings", "listen"];
    for (const route of evidenceRoutes) {
      const result = spawnSync(run.launcher, ["--api", "HTTP://LOCALHOST:4801/", "--route", route], {
        encoding: "utf8", env: run.environment,
      });
      assert.equal(result.status, 0, `${route}: ${result.stderr}`);
    }
    let actions = run.readActions();
    for (const route of evidenceRoutes) {
      assert.match(actions, new RegExp(`launch\\|query=route=${route}&platform=desktop`));
    }
    assert.equal(actions.match(/^launch\|/gm)?.length, 7);

    const defaultHome = spawnSync(run.launcher, ["--api", "http://127.0.0.1:4801"], {
      encoding: "utf8", env: run.environment,
    });
    assert.equal(defaultHome.status, 0);
    actions = run.readActions();
    assert.match(actions, /launch\|query=route=home&platform=desktop/);

    for (const [name, value] of [
      ["OMI_SURFACE_URL", "https://stale.example.invalid/"],
      ["OMI_SURFACE_PATH", "/?rig=dev"],
    ]) {
      const result = spawnSync(run.launcher, ["--api", "http://127.0.0.1:4801", "--route", "chat"], {
        encoding: "utf8", env: { ...run.environment, [name]: value },
      });
      assert.equal(result.status, 0, name);
    }
    const launches = run.readActions().trim().split("\n").filter((line) => line.startsWith("launch|"));
    for (const line of launches.slice(-2)) {
      assert.match(line, /surface_url=unset\|surface_path=unset/);
    }
  } finally {
    rmSync(run.scratch, { recursive: true, force: true });
  }
});
