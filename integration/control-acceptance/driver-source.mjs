// Builds the exact string handed to the shell's OMI_PROBE_JS hook.
//
// It lives apart from run.mjs so a test can assert the real thing parses.
// run.mjs performs its work at import, so a test cannot import it to ask what
// it would have sent.

export function buildDriverSource(driverSource, { screenProof = false } = {}) {
  const prelude = screenProof ? 'window.__omiCAMode = "screen";\n' : "";
  return `${prelude}${String(driverSource).trim()}`;
}
