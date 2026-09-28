const tracked = Bun.spawnSync(["git", "ls-files"], {
  cwd: import.meta.dir + "/..",
  stdout: "pipe",
  stderr: "inherit",
});

if (tracked.exitCode !== 0) {
  process.exit(tracked.exitCode);
}

const files = tracked.stdout.toString().trim().split("\n").filter(Boolean);

// Swift is allowed only where the package manifest declares a target path
// (Package.swift itself excepted).
const packageSwift = await Bun.file(
  import.meta.dir + "/../Package.swift",
).text();
const targetPaths = [...packageSwift.matchAll(/path:\s*"([^"]+)"/g)].map(
  (match) => match[1],
);

const forbidden = files.filter((file) => {
  if (file === "tools/OmiSimulator" || file.startsWith("tools/OmiSimulator/"))
    return false;
  if (/\.swift$/.test(file)) {
    if (file === "Package.swift") return false;
    return !targetPaths.some(
      (targetPath) => file === targetPath || file.startsWith(targetPath + "/"),
    );
  }
  return /(^|\/)(node_modules|Pods|DerivedData|\.build|dist)(\/|$)|(^|\/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$/.test(
    file,
  );
});

if (forbidden.length > 0) {
  console.error(`Forbidden rewrite boundary files:\n${forbidden.join("\n")}`);
  process.exit(1);
}

const sourceFiles = files.filter((file) =>
  /\.(c|cc|cpp|h|m|mm|ts|tsx)$/.test(file),
);
for (const file of sourceFiles) {
  const text = await Bun.file(import.meta.dir + "/../" + file).text();
  if (/import\s+.*(?:backend|spikes|web)\//.test(text)) {
    console.error(`Legacy import in ${file}`);
    process.exit(1);
  }
}

console.log(`boundaries: ${files.length} tracked files accepted`);
