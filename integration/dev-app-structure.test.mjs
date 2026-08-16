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
  assert.match(app, /--route conversations/);
  assert.doesNotMatch(app, /Bun\.serve|createLocalDevService/);
  assert.equal((app.match(/exec "\$MACOS_LAUNCHER"/g) ?? []).length, 1);
});

test("RED-PROOF the demo launcher exports the persona only for the stack it boots", () => {
  assert.match(
    app,
    /OMI_SEED_PERSONA=demo OMI_STT_ENGINE=mlx-whisper OMI_CHAT_MODEL="\$OMI_CHAT_MODEL" "\$STACK" --up/,
  );
  assert.match(app, /serving "\$SERVICE_URL"/);
  assert.match(app, /serving "\$GATEWAY_URL"/);
  assert.match(app, /reused the listeners already serving 4851 and 8788/);
});

test("RED-PROOF the headed human path asks for on-device STT, not the scripted adapter", () => {
  // Anchored to the boot invocation, not the bare pair: the refusal message
  // below prints the same two variables as remediation prose, so a looser match
  // stays green after OMI_STT_ENGINE is dropped from the line that boots.
  assert.match(app, /OMI_STT_ENGINE=mlx-whisper OMI_CHAT_MODEL="\$OMI_CHAT_MODEL" "\$STACK" --up/);
  assert.match(app, /status\?\.stt_engine/);
  assert.match(app, /this stack is not transcribing real speech/);
  assert.match(app, /exit 1/);
  assert.doesNotMatch(app, /--lease/);
  assert.match(stack, /LEASE_MODE=1/);
  // red-proof: dropping OMI_STT_ENGINE from the boot line, or launching against
  // a reused scripted stack, leaves Listen on createScriptedTranscriptionSource.
});

test("RED-PROOF the headed human path answers chat with a real model by default", () => {
  // red-proof: restore `""|test) ;;` to the case arm and an unset env silently
  // selects the canned gateway again — which is exactly the reported defect,
  // "Local test gateway answered." to every question.
  assert.match(app, /OMI_CHAT_MODEL="\$\{OMI_CHAT_MODEL:-real\}"/);
  assert.doesNotMatch(app, /^\s*""\|test\) ;;$/m);
  assert.match(app, /OMI_CHAT_MODEL="\$OMI_CHAT_MODEL" "\$STACK" --up/);
});

test("RED-PROOF a canned stack is refused rather than served as if it were thinking", () => {
  // red-proof: delete the chat_gateway branch and `bun run app` happily attaches
  // to a reused 8788 stack, so Chat answers "Local test gateway answered."
  // The gate reads the same capability tier the transcript chip renders.
  assert.match(app, /status\?\.chat_gateway/);
  assert.match(app, /chat_gateway" == "real-provider"/);
  assert.match(app, /this stack is not answering chat with a real model/);
  assert.match(app, /Local test gateway answered\./);
});

test("RED-PROOF a missing provider key fails closed and names what is missing", () => {
  // red-proof: drop this guard and a keyless machine falls through to a gateway
  // that cannot start, or worse, to canned answers presented as a real model.
  assert.match(app, /GLM_API_KEY/);
  assert.match(app, /ZAI_API_KEY/);
  assert.match(app, /OMI_BENCH_OPENAI_API_KEY/);
  assert.match(app, /no provider key is set/);
  assert.match(app, /OMI_CHAT_MODEL=test bun run app/);
});

test("RED-PROOF the real-model default is the headed path only, never the ladder", () => {
  // red-proof: moving the `:-real` default into dev-stack.sh would make provider
  // uptime trunk colour. L3/L4 drive dev-stack.sh directly and must stay canned.
  assert.doesNotMatch(stack, /OMI_CHAT_MODEL="\$\{OMI_CHAT_MODEL:-real\}"/);
  assert.match(stack, /""\|test\) ;;/);
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
