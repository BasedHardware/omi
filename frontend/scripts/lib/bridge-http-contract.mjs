// Shared extraction of the security-bearing declarations in
// `contracts/src/bridge/http.ts`, used by every per-language generator
// (gen-bridge-swift.mjs, gen-bridge-dart.mjs).
//
// Extraction lives here, ONCE, on purpose: it is the fragile half of the
// generators (regex-grade matching over TS source), and the wave-9 addition of a
// second target would otherwise have duplicated it. The emitters stay in their
// own scripts because they are language-specific and each shell regenerates
// independently.
//
// Deliberately regex-grade over COMMENT-STRIPPED source rather than a TS parser:
// comments are stripped first so quoted words in prose cannot be mistaken for
// values, every failure exits non-zero naming the declaration, and the reason
// union is cross-checked against the status map in both directions. A silent
// partial extraction is therefore not possible.
import { readFileSync } from "node:fs";

export const SOURCE_REL = "contracts/src/bridge/http.ts";

/** Strip block and line comments so prose can never be read as a value. */
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^[ \t]*\/\/.*$/gm, "");
}

/**
 * Parse the contract. Throws with a named declaration on any failure — callers
 * report and exit non-zero rather than emitting a partial file.
 */
export function readBridgeHttpContract(sourceAbs) {
  const src = stripComments(readFileSync(sourceAbs, "utf8"));
  const bad = (msg) => {
    throw new Error(msg);
  };

  const channelMatch = src.match(/export const BRIDGE_HTTP_CHANNEL\s*=\s*"([^"]+)"/);
  if (!channelMatch) bad("could not extract BRIDGE_HTTP_CHANNEL");
  const channel = channelMatch[1];

  const replyMatch = src.match(/export const BRIDGE_HTTP_REPLY_FUNCTION\s*=\s*"([^"]+)"/);
  if (!replyMatch) bad("could not extract BRIDGE_HTTP_REPLY_FUNCTION");
  const replyFunction = replyMatch[1];

  const headersMatch = src.match(/export const BRIDGE_HTTP_FORBIDDEN_HEADERS[^=]*=\s*\[([^\]]*)\]/);
  if (!headersMatch) bad("could not extract BRIDGE_HTTP_FORBIDDEN_HEADERS");
  const forbiddenHeaders = [...headersMatch[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  if (forbiddenHeaders.length === 0) {
    bad("BRIDGE_HTTP_FORBIDDEN_HEADERS extracted as empty — refusing to weaken a shell");
  }

  const reasonMatch = src.match(/export type BridgeHttpFailureReason\s*=([^;]*);/);
  if (!reasonMatch) bad("could not extract BridgeHttpFailureReason");
  const reasons = [...reasonMatch[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  if (reasons.length === 0) bad("BridgeHttpFailureReason extracted as empty");

  const statusMatch = src.match(/export const BRIDGE_HTTP_FAILURE_STATUS[^=]*=\s*\{([^}]*)\}/);
  if (!statusMatch) bad("could not extract BRIDGE_HTTP_FAILURE_STATUS");
  const failureStatus = new Map(
    [...statusMatch[1].matchAll(/(?:"([^"]+)"|([A-Za-z_$][\w$]*))\s*:\s*(\d+)/g)].map((m) => [
      m[1] ?? m[2],
      Number(m[3]),
    ]),
  );
  if (failureStatus.size === 0) bad("BRIDGE_HTTP_FAILURE_STATUS extracted as empty");

  // A reason with no status (or a status with no reason) means the contract and
  // the generated code would disagree about the taxonomy.
  const missingStatus = reasons.filter((r) => !failureStatus.has(r));
  const orphanStatus = [...failureStatus.keys()].filter((k) => !reasons.includes(k));
  if (missingStatus.length) bad(`reasons with no status mapping: ${missingStatus.join(", ")}`);
  if (orphanStatus.length) bad(`status entries with no matching reason: ${orphanStatus.join(", ")}`);

  return { channel, replyFunction, forbiddenHeaders, reasons, failureStatus };
}

/** kebab-case reason -> lowerCamelCase enum case (Swift and Dart agree here). */
export function camelCase(reason) {
  return reason.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
}

/**
 * Shared write/check plumbing so both generators behave identically:
 * `--check` fails on drift; a missing shell checkout SKIPS (absence is not
 * drift — core must stay verifiable standalone).
 */
export function emit({ label, shellDir, outRel, content, check, summary, fs, path }) {
  if (!fs.existsSync(shellDir)) {
    console.log(`${label}: SKIPPED — shell prototype not found (set ${outRel.envVar} to override).`);
    return 0;
  }
  const outAbs = path.join(shellDir, outRel.path);
  let current = null;
  try {
    current = fs.readFileSync(outAbs, "utf8");
  } catch {
    current = null;
  }
  if (check) {
    if (current !== content) {
      console.error(`${label} drift: ${outRel.path} — run the generator in core/`);
      return 1;
    }
    console.log(`${label} in sync (${summary}).`);
    return 0;
  }
  if (current !== content) {
    fs.writeFileSync(outAbs, content);
    console.log(`wrote ${outRel.path}`);
  }
  console.log(`${label} generated (${summary}).`);
  return 0;
}
