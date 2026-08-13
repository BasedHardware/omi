import { readFileSync } from "node:fs";

import { parseProductionQualificationManifest } from "./production-qualification-manifest";

const fail = (code: string): never => { throw new TypeError(code); };

const inputArgument = (args: readonly string[]): string => {
  if (args.length !== 2 || args[0] !== "--input" || args[1]?.length === 0) {
    return fail("production_qualification_usage_invalid");
  }
  return args[1]!;
};

try {
  const inputPath = inputArgument(process.argv.slice(2));
  const bytes = readFileSync(inputPath, "utf8");
  const receipt = parseProductionQualificationManifest(JSON.parse(bytes));
  process.stdout.write(`${JSON.stringify({
    status: "valid",
    version: receipt.manifest.version,
    manifest_digest: receipt.manifest_digest,
  })}\n`);
} catch (error) {
  const code = error instanceof TypeError
    && /^production_qualification_[a-z_]+$/.test(error.message)
    ? error.message
    : "production_qualification_manifest_invalid";
  process.stderr.write(`${JSON.stringify({ status: "error", code })}\n`);
  process.exitCode = 1;
}
