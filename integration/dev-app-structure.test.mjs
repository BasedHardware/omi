// LIFECYCLE: permanent
// Structural red-proofs for the human local-demo launcher. Behavioral proofs
// live in apps/service/qa/demo-persona.test.ts (HTTP) and a headed/accept run.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const app = read("./dev-app.sh");
const stack = read("./dev-stack.sh");
const pkg = JSON.parse(read("../package.json"));

test("RED-PROOF dev-app.sh composes the existing stack and macOS launcher", () => {
  assert.match(app, /dev-stack\.sh/);
  assert.match(app, /--up/);
  assert.match(app, /dev-run-macos\.sh/);
  assert.match(app, /--route home/);
  assert.doesNotMatch(app, /Bun\.serve|createLocalDevService/);
  assert.equal((app.match(/exec "\$MACOS_LAUNCHER"/g) ?? []).length, 1);
});

test("RED-PROOF the demo launcher exports the persona only for the stack it boots", () => {
  assert.match(app, /OMI_SEED_PERSONA=demo OMI_STT_ENGINE=mlx-whisper "\$STACK" --up/);
  assert.match(app, /serving "\$SERVICE_URL"/);
  assert.match(app, /serving "\$GATEWAY_URL"/);
  assert.match(app, /reused the listeners already serving 4851 and 8788/);
});

test("RED-PROOF the headed human path asks for on-device STT, not the scripted adapter", () => {
  assert.match(app, /OMI_STT_ENGINE=mlx-whisper "\$STACK" --up/);
  assert.match(app, /status\?\.stt_engine/);
  assert.match(app, /this stack is not transcribing real speech/);
  assert.match(app, /exit 1/);
  assert.doesNotMatch(app, /--lease/);
  assert.match(stack, /LEASE_MODE=1/);
  // red-proof: dropping OMI_STT_ENGINE from the boot line, or launching against
  // a reused scripted stack, leaves Listen on createScriptedTranscriptionSource.
});

test("RED-PROOF the demo launcher never prints a token", () => {
  assert.match(app, /OMI_API_TOKEN="\$DEV_TOKEN"/);
  assert.doesNotMatch(app, /printf '.*%s.*' "\$DEV_TOKEN"/);
  assert.doesNotMatch(app, /echo "\$DEV_TOKEN"/);
  assert.doesNotMatch(app, /console\.log\(.*[Tt]oken/);
});

test("RED-PROOF stop instructions name the existing stack stopper", () => {
  assert.match(app, /integration\/dev-stack\.sh --stop/);
  assert.match(stack, /STOP_ONLY=1/);
});

test("RED-PROOF the demo launcher stays on the pinned origin 5290", () => {
  assert.match(app, /SURFACE_URL="http:\/\/127\.0\.0\.1:5290"/);
  assert.match(app, /OMI_SURFACE_PORT=5290/);
  assert.doesNotMatch(app, /OMI_SURFACE_PORT=15290|OMI_SURFACE_PORT="\$|--lease/);
});

test("RED-PROOF bun run app is wired to the one launcher", () => {
  assert.equal(pkg.scripts.app, "bash integration/dev-app.sh");
});

test("RED-PROOF scripted STT canned lines stay in lockstep on the Listen surface", () => {
  const source = read("../apps/service/listen/transcription-source.ts");
  const surface = read("../frontend/packages/surfaces/src/production/listen-presentation.ts");
  for (const line of ["Local transcription is connected.", "This segment arrived with real timing."]) {
    assert.match(source, new RegExp(line.replace(/[.*]/g, "\\$&")));
    assert.match(surface, new RegExp(line.replace(/[.*]/g, "\\$&")));
  }
});

test("RED-PROOF the launcher discloses the local test gateway, never production", () => {
  assert.match(app, /local test gateway/);
  assert.match(app, /not a real model/);
  assert.doesNotMatch(app, /api\.omi\.me|\?rig=dev/);
});

test("RED-PROOF the human demo launcher is headed; --accept stays headless", () => {
  // red-proof: drop `export OMI_HEADED=1` and `bun run app` parks offscreen
  // with no Dock icon. Drop the unset and `dev-app.sh --accept` inherits a
  // headed parent and steals focus.
  assert.match(
    app,
    /if \(\( MODE_ACCEPT \)\); then\n  unset OMI_HEADED\nelse\n  export OMI_HEADED=1\nfi/,
  );
});
