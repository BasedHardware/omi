// LIFECYCLE: permanent
//
// Verdict aggregation for the control-acceptance harness. The live driver
// clicks real surface controls inside the macOS WKWebView; this module is the
// only place that decides PASS / FAIL / skip from those per-control slugs.
//
// A skip is host state this harness does not own (TCC already decided). It is
// printed and it is NOT a pass. Overall PASS requires every step to be a pass
// or a legitimate skip, and the skip list to be non-empty in the output when
// any skip occurred.

export const PENDING_VALUE = "OMI_CONTROL_PENDING";
export const SCHEMA = "omi.control-acceptance.v1";

/** Stable slugs. Adding a control is a new row here, never a renamed old one. */
export const STEP_SLUGS = Object.freeze([
  "home",
  "chat",
  "mic",
  "screen",
  "nav.home",
  "nav.conversations",
  "nav.memories",
  "nav.folders",
  "nav.tasks",
  "nav.rewind",
  "nav.apps",
  "nav.brain-map",
  "nav.chat",
  "nav.settings",
  "nav.listen",
]);

/** Verdicts that count as a pass for that slug. Anything else is fail or skip. */
export const PASS_VERDICTS = Object.freeze({
  home: Object.freeze(["ready"]),
  chat: Object.freeze(["streamed-and-persisted"]),
  mic: Object.freeze(["reached-os"]),
  screen: Object.freeze(["reached-os"]),
  "nav.home": Object.freeze(["rendered"]),
  "nav.conversations": Object.freeze(["rendered"]),
  "nav.memories": Object.freeze(["rendered"]),
  "nav.folders": Object.freeze(["rendered"]),
  "nav.tasks": Object.freeze(["rendered"]),
  "nav.rewind": Object.freeze(["rendered"]),
  "nav.apps": Object.freeze(["rendered"]),
  "nav.brain-map": Object.freeze(["rendered"]),
  "nav.chat": Object.freeze(["rendered"]),
  "nav.settings": Object.freeze(["rendered"]),
  "nav.listen": Object.freeze(["rendered"]),
});

export const HOME_FAILURE_NOTICE = "Showing saved data. Couldn't refresh.";

export function isSkip(verdict) {
  return typeof verdict === "string" && verdict.startsWith("skipped-");
}

export function isPass(slug, verdict) {
  const allowed = PASS_VERDICTS[slug];
  return Array.isArray(allowed) && allowed.includes(verdict);
}

export function formatControlLine(slug, verdict) {
  return `CONTROL ${slug}=${verdict}`;
}

/**
 * Classify the page-side Screen host channel the Rewind capture control posts
 * to. A missing `omiScreenBridge` is the defect measured 2026-08-15: the
 * control is visible (or a disabled stand-in is) and the shell never registered
 * the handler.
 *
 * red-proof: pass a host with no omiScreenBridge — this returns
 * `bridge-unreachable`, never a pass token.
 */
export function inspectScreenChannel(host = globalThis) {
  const channel = host?.omiScreenBridge ?? host?.webkit?.messageHandlers?.omiScreenBridge;
  if (channel == null || typeof channel.postMessage !== "function") {
    return "bridge-unreachable";
  }
  return "present";
}

export function inspectListenChannel(host = globalThis) {
  const channel = host?.omiListenSocket ?? host?.webkit?.messageHandlers?.omiListenSocket;
  if (channel == null || typeof channel.postMessage !== "function") {
    return "channel-unreachable";
  }
  return "present";
}

export function aggregate(steps) {
  const bySlug = new Map();
  for (const step of steps ?? []) {
    if (!step || typeof step.slug !== "string" || typeof step.verdict !== "string") continue;
    bySlug.set(step.slug, step);
  }

  const ordered = STEP_SLUGS.map((slug) => bySlug.get(slug) ?? { slug, verdict: "missing-step" });
  const extras = [...bySlug.values()].filter((step) => !STEP_SLUGS.includes(step.slug));
  const all = [...ordered, ...extras];

  let passed = 0;
  let failed = 0;
  let skipped = 0;
  const skips = [];
  const failures = [];

  for (const step of all) {
    if (isSkip(step.verdict)) {
      skipped += 1;
      skips.push(formatControlLine(step.slug, step.verdict));
      continue;
    }
    if (isPass(step.slug, step.verdict)) {
      passed += 1;
      continue;
    }
    failed += 1;
    failures.push(formatControlLine(step.slug, step.verdict));
  }

  const status = failed === 0 ? "PASS" : "FAIL";
  const lines = all.map((step) => formatControlLine(step.slug, step.verdict));
  const skipList = skips.length === 0
    ? "CONTROL-ACCEPTANCE skips: (none)"
    : `CONTROL-ACCEPTANCE skips: ${skips.map((line) => line.slice("CONTROL ".length)).join(" ")}`;

  return {
    status,
    passed,
    failed,
    skipped,
    lines,
    skipList,
    failures,
    summary:
      `CONTROL-ACCEPTANCE status=${status} passed=${passed} failed=${failed} skipped=${skipped}`,
  };
}

export function parseProbeJsLine(text) {
  const lines = String(text ?? "").split(/\r?\n/);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i];
    const match = line.match(/^PROBE_JS: (.*) error: (.*)$/);
    if (!match) continue;
    const value = match[1];
    const error = match[2];
    if (error !== "none") {
      return { ok: false, reason: `probe-js-error:${error}`, raw: line };
    }
    if (value === PENDING_VALUE || value === "nil") {
      return { ok: false, reason: "probe-timeout", raw: line };
    }
    try {
      const parsed = JSON.parse(value);
      if (parsed?.schema !== SCHEMA || !Array.isArray(parsed.steps)) {
        return { ok: false, reason: "probe-shape", raw: line };
      }
      return { ok: true, result: parsed, raw: line };
    } catch {
      return { ok: false, reason: "probe-json", raw: line };
    }
  }
  return { ok: false, reason: "probe-missing", raw: null };
}

export function reportFromProbeText(text) {
  const parsed = parseProbeJsLine(text);
  if (!parsed.ok) {
    const harness = { slug: "harness", verdict: parsed.reason };
    const verdict = aggregate([harness]);
    return { ...verdict, parse: parsed };
  }
  const verdict = aggregate(parsed.result.steps);
  return { ...verdict, parse: parsed };
}
