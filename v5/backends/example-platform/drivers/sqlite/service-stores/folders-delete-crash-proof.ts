import { existsSync } from "node:fs";

const child = new URL("./folders-delete-crash-proof-child.ts", import.meta.url).pathname;
const databasePath = process.argv[2];
const markerPath = process.argv[3];
if (databasePath === undefined || markerPath === undefined) {
  process.stderr.write("usage: folders-delete-crash-proof.ts <database-path> <marker-path>\n");
  process.exit(2);
}

const crashed = Bun.spawn({
  cmd: [process.execPath, "run", child, "crash", databasePath, markerPath],
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
  process.stderr.write(`crash child never reached the folder delete boundary\n${await new Response(crashed.stderr).text()}`);
  process.exit(1);
}

crashed.kill("SIGKILL");
await crashed.exited;
if (crashed.signalCode !== "SIGKILL") {
  process.stderr.write(`crash child was not killed by SIGKILL: ${String(crashed.signalCode)}\n`);
  process.exit(1);
}

const restarted = Bun.spawnSync({
  cmd: [process.execPath, "run", child, "restart", databasePath, markerPath],
  stdout: "pipe",
  stderr: "pipe",
});
if (restarted.exitCode !== 0) {
  process.stderr.write(restarted.stderr.toString());
  process.exit(1);
}
const afterCrash = JSON.parse(restarted.stdout.toString()) as {
  readonly sourceExists: boolean;
  readonly targetExists: boolean;
  readonly conversationFolderId: string | null;
  readonly folderRows: number;
  readonly conversationRows: number;
};
if (
  afterCrash.sourceExists !== true
  || afterCrash.targetExists !== true
  || afterCrash.conversationFolderId !== "folder-source"
  || afterCrash.folderRows !== 2
  || afterCrash.conversationRows !== 1
) {
  process.stderr.write(`folder delete atomicity proof failed\n${JSON.stringify(afterCrash, null, 2)}\n`);
  process.exit(1);
}

process.stdout.write("child reached boundary: conversations reassigned, folder not deleted\n");
process.stdout.write("kill child: SIGKILL\n");
process.stdout.write("restart child: complete\n");
process.stdout.write("after crash: source_folder=present target_folder=present conversation.folder_id=folder-source\n");
process.stdout.write("folder delete atomicity proof: PASS\n");
