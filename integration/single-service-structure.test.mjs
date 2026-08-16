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
const evidenceCli = read("./lib/evidence-cli.mjs");
const owner = read("./lib/process-owner.mjs");
const sanitizer = read("./lib/sanitize-log.mjs");
const control = read("./control-acceptance/run.mjs");
const macos = read("../frontend/shells/macos/scripts/dev-run-macos.sh");
const ios = read("../frontend/shells/ios/scripts/dev-run-ios.sh");
const receipts = read("./lib/receipts.mjs");

test("RED-PROOF the registered stack cannot reintroduce the retired service", () => {
  // red-proof: add the old port, prototype name, or launcher path to dev-stack.
  for (const source of [stack, lanes, doctor]) {
    assert.doesNotMatch(source, /4747|qa-api-server|write-journey-door/);
  }
  assert.match(stack, /SERVICE_REL="apps\/service\/bin\/dev-server\.ts"/);
  assert.match(stack, /exec bun "\$\{service_args\[@\]\}"/);
  assert.equal(existsSync(new URL("./lib/write-journey-door.mjs", import.meta.url)), false);
});

test("RED-PROOF control-acceptance verification boots a leased stack and does not attach to 4851", () => {
  assert.match(control, /"--up", "--lease"/);
  assert.match(lanes, /command: "integration\/dev-stack\.sh --assert --lease"/);
  assert.match(lanes, /appendDeviceArgument\(step\.command, simulatorLease\?\.udid\)/);
  assert.match(lanes, /holdSimulatorLease/);
  assert.match(control, /Verification never attaches to 4851\/8788\/8791/);
  assert.doesNotMatch(control, /if \(!SCREEN_PROOF && !serviceUp && !gatewayUp\)/);
});

test("RED-PROOF L3 has no no-ios, generation split, attach, or soft shell skip", () => {
  for (const source of [stack, lanes]) {
    assert.doesNotMatch(source, /--no-ios|--generation|--attach|WANT_IOS|skipping iOS|ios:null/);
  }
  assert.match(lanes, /command: "integration\/dev-stack\.sh --assert --lease"/);
  assert.match(stack, /macOS launcher is absent or not executable/);
  assert.match(stack, /iOS launcher is absent or not executable/);
});

test("RED-PROOF the pinned app origin and the leased verification origin stay distinct", () => {
  // red-proof: fold verification back onto 5290, or drop the lease-path
  // refusal and let a lane report green against the app's IndexedDB.
  const lease = read("../apps/service/net/port-lease.ts");
  const app = read("./dev-app.sh");
  assert.match(stack, /MACOS_ORIGIN="http:\/\/127\.0\.0\.1:5290"/);
  assert.match(stack, /held="\$\(listener 5290\)"/);
  assert.match(stack, /required port 5290 is occupied/);
  assert.match(stack, /LEASE_ROLES="service,gateway,surface"/);
  assert.match(stack, /refusing to use or fall back to the pinned app origin 5290/);
  assert.match(lease, /SURFACE_TEST_PORT_MIN = 15_290/);
  assert.match(lease, /SURFACE_TEST_PORT_MAX = 15_309/);
  assert.match(macos, /PINNED_APP_ORIGIN_PORT=5290/);
  assert.match(macos, /VERIFICATION_SURFACE_PORT_MIN=15290/);
  assert.match(macos, /do not fold this path back into/);
  assert.match(app, /OMI_SURFACE_PORT=5290/);
  assert.match(app, /SURFACE_URL="http:\/\/127\.0\.0\.1:5290"/);
  assert.doesNotMatch(app, /OMI_SURFACE_PORT=15290|OMI_SURFACE_PORT="\$|--lease/);
  assert.match(control, /refusing to use the pinned app origin 5290/);
  assert.doesNotMatch(`${lanes}\n${doctor}`, /529[1-9]/);
  assert.doesNotMatch(stack, /for candidate|free_port|kill.*5290/);
  assert.match(stack, /--lease/);
  assert.match(stack, /stack-port-lease\.ts/);
  assert.match(stack, /stack-simulator-lease\.ts/);
  assert.match(stack, /if \[\[ -z "\$DEVICE" \]\]/);
  assert.match(stack, /ios_args\+=\(--device "\$DEVICE"\)/);
  assert.doesNotMatch(stack, /simctl erase|simctl delete/);
});

test("RED-PROOF there is one app-facing service listener and one run-scoped SQLite path", () => {
  assert.equal((stack.match(/SERVICE_URL="http:\/\/127\.0\.0\.1:4851"/g) ?? []).length, 1);
  assert.match(stack, /DATABASE_PATH="\$RUN_DIR\/service\.sqlite"/);
  assert.match(stack, /OMI_QA_DB="\$DATABASE_PATH"/);
  assert.equal((stack.match(/exec bun "\$\{service_args\[@\]\}"/g) ?? []).length, 1);
  assert.match(stack, /OMI_PORT="\$SERVICE_PORT"/);
  assert.match(stack, /--app-facing-test-lease/);
  assert.doesNotMatch(stack, /SURFACES_PORT|dev-stack-static|OMI_BACKEND_URL|using external/);
});

test("RED-PROOF --assert expected shell hash is the macos-app stamp the shells bake", () => {
  // red-proof: drop `--artifact macos-app`. expectedShell becomes the
  // frontend+integration worktree, iOS evidence completes, and every matrix
  // row fails as a stale shell hash because the apps stamp macos-app/ios-bundle.
  assert.match(stack, /provenance\.mjs" --repo core-foundation --artifact macos-app/);
  assert.match(receipts, /artifact: "macos-app"/);
});

test("RED-PROOF iOS evidence is bounded build-install-launch-collect, never optional", () => {
  assert.match(ios, /simctl list devices booted/);
  assert.match(ios, /no booted simulator found/);
  assert.doesNotMatch(ios, /simctl boot /);
  assert.match(ios, /flutter_bin" build ios --simulator --debug/);
  assert.match(ios, /simctl install/);
  assert.match(ios, /simctl launch "\$device" "\$bundle_id"/);
  assert.doesNotMatch(ios, /--terminate-running-process/);
  assert.match(ios, /OMI_CONSUMER_EVIDENCE_WAIT_SECONDS:-180/);
  assert.match(ios, /native iOS result was not written within/);
  assert.match(ios, /omi-ui:\/\/local/);
  assert.doesNotMatch(ios, /skipping.*simulator/);
});

test("RED-PROOF fixture and headed click-through cannot enter the registered result", () => {
  assert.match(ios, /consumer evidence requires LIVE mode; --fixture is forbidden/);
  assert.doesNotMatch(macos, /--fixture\)/);
  assert.match(macos, /surface_query="route=\$\{route\}&platform=desktop&generation=platform"/);
  assert.match(ios, /surface_query="route=\$\{route\}&platform=mobile&generation=platform"/);
  assert.doesNotMatch(stack, /--fixture|--headed|OMI_HEADED|screencapture|screenshot/);
});

test("RED-PROOF headed Chat uses a disclosed local test gateway, never production or scripted source", () => {
  assert.match(stack, /local-test-gateway\.mjs/);
  assert.match(stack, /OMI_LLM_GATEWAY_URL="\$GATEWAY_URL"/);
  assert.match(stack, /OMI_LLM_GATEWAY_SERVICE_TOKEN="\$GATEWAY_TOKEN"/);
  assert.match(stack, /local test gateway/);
  assert.match(stack, /never a production model, never the production API host/);
  assert.doesNotMatch(stack, /https:\/\/api\.omi\.me/);
  assert.doesNotMatch(stack, /createScriptedChatGenerationSource/);
  assert.equal(existsSync(new URL("./local-test-gateway.mjs", import.meta.url)), true);
});

test("RED-PROOF native result bytes stay exact and launcher outcomes stay separate", () => {
  assert.doesNotMatch(stack, /stamp-shell/);
  assert.doesNotMatch(evidenceCli, /command === "stamp-shell"/);
  assert.match(evidenceCli, /validate-consumer-evidence\.mjs/);
  assert.match(evidenceCli, /if \(!before\.equals\(after\)\)/);
  assert.match(stack, /launchers:\{macos:\{status:"pass",exitCode:0\},ios:\{status:"pass",exitCode:0\}\}/);
});

test("RED-PROOF --up returns after owned service readiness and before every build or shell", () => {
  const up = stack.indexOf("if (( MODE_UP )); then");
  const buildFence = stack.indexOf("Everything below this line belongs only to the full two-shell assertion run");
  const macosLaunch = stack.indexOf('"$MACOS_LAUNCHER" --api');
  const iosLaunch = stack.indexOf('"$IOS_LAUNCHER" "${ios_args[@]}"');
  assert.ok(up >= 0 && buildFence > up && macosLaunch > buildFence && iosLaunch > buildFence);
  assert.match(stack.slice(up, buildFence), /LEAVE_RUNNING=1[\s\S]*exit 0/);
  assert.doesNotMatch(stack.slice(0, buildFence), /corepack pnpm|"\$MACOS_LAUNCHER" --api|"\$IOS_LAUNCHER"/);
});

test("RED-PROOF stop signals only a durable exact process owner", () => {
  assert.match(owner, /runId.*expectedExecutable.*expectedCommand.*ownerToken.*processStartIdentity/s);
  assert.match(owner, /owner PID was reused or has a stale start identity/);
  assert.match(owner, /owner PID has an unknown executable or command/);
  assert.match(owner, /process identity changed before escalation; SIGKILL skipped/);
  assert.match(owner, /ownerTokenSha256/);
  assert.match(owner, /independent binding changed before signal; stop refused/);
  assert.match(owner, /independent binding changed before escalation; SIGKILL skipped/);
  assert.match(owner, /stopPreOwnerProcess/);
  assert.match(owner, /immediatelyBeforeCommit/);
  assert.match(owner, /validateCommittedOwner\(path, record\)/);
  assert.match(stack, /stop-pre-owner --pid "\$SERVICE_PID"/);
  assert.doesNotMatch(stack, /PIDFILE|kill -KILL "\$pid"|kill "\$SERVICE_PID"/);
});

test("RED-PROOF service output reaches disk only through the streaming sanitizer", () => {
  assert.match(stack, /if ! mkdir "\$RUN_DIR"/);
  assert.match(stack, /refusing to reuse or overwrite prior evidence/);
  assert.match(stack, /mkfifo "\$SERVICE_LOG_PIPE"/);
  assert.match(stack, /"\$LOG_SANITIZER" --stream --out "\$LOG_DIR\/service\.log"/);
  assert.match(stack, /exec bun "\$\{service_args\[@\]\}" \) > "\$SERVICE_LOG_PIPE" 2>&1 &/);
  assert.doesNotMatch(stack, /exec bun "\$\{service_args\[@\]\}" \) > "\$LOG_DIR\/service\.log"/);
  assert.match(stack, /"\$ARTIFACT_GUARD" --readiness "\$READINESS_PATH" --path "\$LOG_DIR"/);
  assert.match(stack, /retained_paths=\("\$LOG_DIR" "\$MACOS_RESULT" "\$IOS_RESULT" "\$CONSUMER_RESULT" "\$PRODUCER_RESULT" "\$FACTS_PATH"\)/);
  assert.match(stack, /retained_paths\+\=\("\$REPORTFILE"\)/);
  for (const coordinate of ["--run-id", "--executable", "--base-url", "--database", "--pid", "--process-start-identity"]) {
    assert.match(stack, new RegExp(coordinate));
  }
  assert.match(sanitizer, /validateServiceReadiness/);
  assert.match(sanitizer, /snapshot\.startIdentity !== expectedStartIdentity/);
  assert.match(sanitizer, /activated && !commandMatchesService/);
});
