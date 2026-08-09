const child = new URL("./conversations-restart-proof-child.ts", import.meta.url).pathname;
const databasePath = process.argv[2];

if (databasePath === undefined) {
  process.stderr.write("usage: bun run conversations-restart-proof.ts <database-path>\n");
  process.exit(2);
}

const run = (phase: "write" | "read") => Bun.spawnSync({
  cmd: [process.execPath, "run", child, phase, databasePath],
  stdout: "pipe",
  stderr: "pipe",
});

const write = run("write");
if (write.exitCode !== 0) {
  process.stderr.write(write.stderr.toString());
  process.exit(1);
}
const read = run("read");
if (read.exitCode !== 0) {
  process.stderr.write(read.stderr.toString());
  process.exit(1);
}

const written = JSON.parse(write.stdout.toString()) as { readonly title: string };
const restarted = JSON.parse(read.stdout.toString()) as {
  readonly found: boolean;
  readonly title: string | null;
  readonly revision: number;
};
if (
  written.title !== "Persistent after mutation"
  || restarted.found !== true
  || restarted.title !== "Persistent after mutation"
  || restarted.revision !== 1
) {
  process.stderr.write(
    `conversation restart persistence proof failed\n${JSON.stringify({ written, restarted }, null, 2)}\n`,
  );
  process.exit(1);
}

process.stdout.write("write conversation in first process: complete\n");
process.stdout.write("stop first process: complete\n");
process.stdout.write("start second process: complete\n");
process.stdout.write('read conversation in second process: found title="Persistent after mutation" revision=1\n');
