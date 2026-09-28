// domain-pending(DIV-DOMTASK-001)
// domain-pending(DIV-DOMTASK-002)
// domain-pending(FC-DOMTASK-001)

import { existsSync } from "node:fs";

const childPath = new URL("./unit-of-work-crash-proof-child.ts", import.meta.url).pathname;
const databasePath = process.argv[2];
const markerPath = process.argv[3];

if (databasePath === undefined || markerPath === undefined) {
  process.stderr.write("usage: unit-of-work-crash-proof.ts <database-path> <marker-path>\n");
  process.exit(2);
}

const crashed = Bun.spawn({
  cmd: [process.execPath, "run", childPath, "crash", databasePath, markerPath],
  stdout: "pipe",
  stderr: "pipe",
});

const deadline = Date.now() + 10_000;
while (!existsSync(markerPath) && Date.now() < deadline) {
  if (crashed.exitCode !== null || crashed.signalCode !== null) break;
  await Bun.sleep(10);
}

if (!existsSync(markerPath)) {
  if (crashed.exitCode === null && crashed.signalCode === null) crashed.kill("SIGKILL");
  await crashed.exited;
  const stderr = await new Response(crashed.stderr).text();
  process.stderr.write(`crash child never reached the apply/record boundary\n${stderr}`);
  process.exit(1);
}

crashed.kill("SIGKILL");
await crashed.exited;
if (crashed.signalCode !== "SIGKILL") {
  process.stderr.write(`crash child was not killed by SIGKILL: ${String(crashed.signalCode)}\n`);
  process.exit(1);
}

const restarted = Bun.spawnSync({
  cmd: [process.execPath, "run", childPath, "restart", databasePath, markerPath],
  stdout: "pipe",
  stderr: "pipe",
});
if (restarted.exitCode !== 0) {
  process.stderr.write(restarted.stderr.toString());
  process.exit(1);
}

const result = JSON.parse(restarted.stdout.toString()) as {
  beforeReplay: { taskRecords: number; taskApplies: number; registryRows: number };
  replay: { status: number; body: string };
  read: { status: number; body: string };
  secondReplay: { status: number; body: string };
  afterReplay: { taskRecords: number; taskApplies: number; registryRows: number };
  description: string;
};
const replayBody = JSON.parse(result.replay.body) as { idempotent?: boolean };
const secondReplayBody = JSON.parse(result.secondReplay.body) as { idempotent?: boolean };
const passed = result.beforeReplay.taskRecords === 0
  && result.beforeReplay.taskApplies === 0
  && result.beforeReplay.registryRows === 0
  && result.replay.status === 200
  && replayBody.idempotent === false
  && result.read.status === 200
  && result.read.body.includes(result.description)
  && result.secondReplay.status === 200
  && secondReplayBody.idempotent === true
  && result.afterReplay.taskRecords === 1
  && result.afterReplay.taskApplies === 1
  && result.afterReplay.registryRows === 1;

if (!passed) {
  process.stderr.write(`unit-of-work crash proof failed\n${JSON.stringify(result, null, 2)}\n`);
  process.exit(1);
}

process.stdout.write("child reached boundary: task applied, write_id not recorded\n");
process.stdout.write("kill child: SIGKILL\n");
process.stdout.write("restart child: complete\n");
process.stdout.write("after crash: task_records=0 task_applies=0 registry_rows=0\n");
process.stdout.write("replay same write_id: 200 idempotent=false\n");
process.stdout.write("after replay: task_records=1 task_applies=1 registry_rows=1\n");
process.stdout.write("second replay: 200 idempotent=true\n");
process.stdout.write("unit-of-work crash proof: PASS\n");
