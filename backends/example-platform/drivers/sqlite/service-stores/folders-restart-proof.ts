const child = new URL("./folders-restart-proof-child.ts", import.meta.url).pathname;
const databasePath = process.argv[2];

if (databasePath === undefined) {
  process.stderr.write("usage: folders-restart-proof.ts <database-path>\n");
  process.exit(2);
}

const run = (phase: "write" | "read") => Bun.spawnSync({
  cmd: [process.execPath, "run", child, phase, databasePath],
  stdout: "pipe",
  stderr: "pipe",
});

const write = run("write");
const read = run("read");
if (write.exitCode !== 0 || read.exitCode !== 0) {
  process.stderr.write(write.stderr.toString());
  process.stderr.write(read.stderr.toString());
  process.exit(1);
}

const written = JSON.parse(write.stdout.toString()) as { readonly id: string; readonly name: string };
const restarted = JSON.parse(read.stdout.toString()) as {
  readonly found: boolean;
  readonly record: FolderRecord | null;
};
if (
  written.id !== "folder-persistent"
  || written.name !== "Persistent folder"
  || restarted.found !== true
  || restarted.record?.name !== "Persistent folder"
) {
  process.stderr.write(`folder restart persistence proof failed\n${JSON.stringify({ written, restarted }, null, 2)}\n`);
  process.exit(1);
}

process.stdout.write("write folder in first process: complete\n");
process.stdout.write("kill first process: complete\n");
process.stdout.write("start second process: complete\n");
process.stdout.write('read folder in second process: found id="folder-persistent" name="Persistent folder"\n');

interface FolderRecord { readonly name: unknown }
