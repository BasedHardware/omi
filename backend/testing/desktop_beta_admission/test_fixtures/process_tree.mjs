import { writeFileSync } from "node:fs";
import { spawn } from "node:child_process";

const [pidFile, mode = "wait"] = process.argv.slice(2);
if (!pidFile) throw new Error("Usage: process_tree.mjs <pid-file> [wait|exit]");

const grandchild = spawn(process.execPath, ["-e", "setInterval(() => {}, 1_000)"], { stdio: "ignore" });
writeFileSync(pidFile, `${grandchild.pid}\n`);

if (mode === "exit") process.exit(0);
setInterval(() => {}, 1_000);
