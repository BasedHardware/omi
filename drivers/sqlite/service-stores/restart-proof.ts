const child = new URL("./restart-proof-child.ts", import.meta.url).pathname;
const databasePath = process.argv[2];

if (databasePath === undefined) {
  process.stderr.write("usage: bun run restart-proof.ts <database-path>\n");
  process.exit(2);
}

const run = (phase: "write" | "read-and-replay") => Bun.spawnSync({
  cmd: [process.execPath, "run", child, phase, databasePath],
  stdout: "pipe",
  stderr: "pipe",
});

const write = run("write");
if (write.exitCode !== 0) {
  process.stderr.write(write.stderr.toString());
  process.exit(1);
}

const restart = run("read-and-replay");
if (restart.exitCode !== 0) {
  process.stderr.write(restart.stderr.toString());
  process.exit(1);
}

const first = JSON.parse(write.stdout.toString()) as {
  activation: { status: number; body: string };
  written: { status: number; body: string };
};
const second = JSON.parse(restart.stdout.toString()) as {
  read: { status: number; body: string };
  replay: { status: number; body: string };
  description: string;
};

const firstBody = JSON.parse(first.written.body) as { idempotent?: boolean };
const replayBody = JSON.parse(second.replay.body) as { idempotent?: boolean };
const passed = first.activation.status === 200
  && first.written.status === 200
  && firstBody.idempotent === false
  && second.read.status === 200
  && second.read.body.includes(second.description)
  && second.replay.status === 200
  && replayBody.idempotent === true;

if (!passed) {
  process.stderr.write(`restart persistence proof failed\n${JSON.stringify({ first, second }, null, 2)}\n`);
  process.exit(1);
}

process.stdout.write("write through door: 200 idempotent=false\n");
process.stdout.write("stop first process: complete\n");
process.stdout.write("start second process: complete\n");
process.stdout.write(`read through door: 200 found=${JSON.stringify(second.description)}\n`);
process.stdout.write("replay after restart: 200 idempotent=true\n");

