// Builds the exact string handed to the shell's OMI_PROBE_JS hook.
//
// It lives apart from run.mjs so a test can assert the real thing parses.
// run.mjs performs its work at import, so a test cannot import it to ask what
// it would have sent.

export function buildDriverSource(driverSource, {
  screenProof = false,
  journey = false,
  real = false,
  baseline = null,
} = {}) {
  if (screenProof && journey) {
    throw new Error("control-acceptance modes are mutually exclusive");
  }
  const lines = [];
  if (screenProof) lines.push('window.__omiCAMode = "screen";');
  if (journey) {
    lines.push('window.__omiCAMode = "journey";');
    const ids = baseline && typeof baseline === "object"
      ? {
          conversationIds: Array.isArray(baseline.conversationIds) ? baseline.conversationIds : [],
          memoryIds: Array.isArray(baseline.memoryIds) ? baseline.memoryIds : [],
        }
      : { conversationIds: [], memoryIds: [] };
    lines.push(`window.__omiCABaseline = ${JSON.stringify(ids)};`);
  }
  if (real) lines.push("window.__omiCAReal = true;");
  const prelude = lines.length > 0 ? `${lines.join("\n")}\n` : "";
  return `${prelude}${String(driverSource).trim()}`;
}
