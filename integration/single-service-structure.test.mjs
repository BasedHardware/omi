// LIFECYCLE: permanent
// Structural red-proofs for the retired multi-door and soft-shell shapes. These
// complement the behavioral arbiter tests: they stop a launcher regression
// before it can produce a plausible-looking receipt.

import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const stack = read("./dev-stack.sh");
const lanes = read("./lanes.mjs");
const doctor = read("./doctor.sh");
const macos = read("../core/shells/macos/scripts/dev-run-macos.sh");
const ios = read("../core/shells/ios/scripts/dev-run-ios.sh");

test("RED-PROOF the registered stack cannot reintroduce the retired service", () => {
  // red-proof: add the old port, prototype name, or launcher path to dev-stack.
  for (const source of [stack, lanes, doctor]) {
    assert.doesNotMatch(source, /4747|qa-api-server|write-journey-door/);
  }
  assert.match(stack, /SERVICE_REL="apps\/service\/bin\/dev-server\.ts"/);
  assert.match(stack, /exec bun "\$SERVICE_REL"/);
  assert.equal(existsSync(new URL("./lib/write-journey-door.mjs", import.meta.url)), false);
});

test("RED-PROOF L3 has no no-ios, generation split, attach, or soft shell skip", () => {
  for (const source of [stack, lanes]) {
    assert.doesNotMatch(source, /--no-ios|--generation|--attach|WANT_IOS|skipping iOS|ios:null/);
  }
  assert.match(lanes, /command: "integration\/dev-stack\.sh --assert"/);
  assert.match(stack, /macOS launcher is absent or not executable/);
  assert.match(stack, /iOS launcher is absent or not executable/);
});

test("RED-PROOF macOS registered evidence is exactly 127.0.0.1:5290", () => {
  assert.match(stack, /MACOS_ORIGIN="http:\/\/127\.0\.0\.1:5290"/);
  assert.match(stack, /required port \$port is occupied/);
  assert.match(macos, /structured macOS evidence requires 127\.0\.0\.1:5290 exactly/);
  assert.doesNotMatch(`${stack}\n${lanes}\n${doctor}`, /529[1-9]/);
  assert.doesNotMatch(stack, /for candidate|free_port|kill.*5290/);
});

test("RED-PROOF there is one app-facing service listener and one run-scoped SQLite path", () => {
  assert.equal((stack.match(/SERVICE_URL="http:\/\/127\.0\.0\.1:4851"/g) ?? []).length, 1);
  assert.match(stack, /DATABASE_PATH="\$RUN_DIR\/service\.sqlite"/);
  assert.match(stack, /OMI_QA_DB="\$DATABASE_PATH"/);
  assert.doesNotMatch(stack, /SURFACES_PORT|dev-stack-static|OMI_BACKEND_URL|using external/);
});

test("RED-PROOF iOS evidence is bounded build-install-launch-collect, never optional", () => {
  assert.match(ios, /deterministic selection; boot ready/);
  assert.match(ios, /did not boot within 60s/);
  assert.match(ios, /flutter_bin" build ios --simulator --debug/);
  assert.match(ios, /simctl install/);
  assert.match(ios, /simctl launch --terminate-running-process/);
  assert.match(ios, /did not write structured evidence within 180s/);
  assert.match(ios, /omi-ui:\/\/local/);
  assert.doesNotMatch(ios, /skipping|WARNING:.*simulator/);
});

test("RED-PROOF fixture and headed click-through cannot enter the registered result", () => {
  assert.match(macos, /structured evidence refuses --fixture/);
  assert.match(ios, /structured evidence refuses --fixture/);
  assert.match(macos, /OMI_HEADED=0/);
  assert.doesNotMatch(stack, /--headed|screencapture|screenshot/);
});
