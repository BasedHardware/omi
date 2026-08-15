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

export const CANNED_CHAT_LABEL = "Local test gateway";
export const CANNED_CHAT_ANSWER = "Local test gateway answered.";
export const REAL_CHAT_LABEL_PREFIX = "External model response";
export const CANNED_GATEWAY_KIND = "omi.local-test-gateway.v1";
export const REAL_GATEWAY_KIND = "omi.local-model-gateway.v1";

/** Skips this harness may emit. Prefix-matching `skipped-*` is how a real
 *  failure was laundered into a pass (`skipped-already-granted`). Add slugs;
 *  never treat an unknown skip as legitimate. */
export const SKIP_VERDICTS = Object.freeze([
  "skipped-tcc-denied",
  "skipped-not-requested",
]);

/** Verdicts that count as a pass for that slug. Anything else is fail or skip. */
export const PASS_VERDICTS = Object.freeze({
  home: Object.freeze(["ready"]),
  chat: Object.freeze(["streamed-and-persisted"]),
  mic: Object.freeze(["transcript-rendered"]),
  screen: Object.freeze(["frame-rendered"]),
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
  return SKIP_VERDICTS.includes(verdict);
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

function attr(node, name) {
  if (node == null) return "";
  if (typeof node.getAttribute === "function") return node.getAttribute(name) ?? "";
  return "";
}

function nodesOf(root, selector) {
  if (root == null || typeof root.querySelectorAll !== "function") return [];
  return [...root.querySelectorAll(selector)];
}

/**
 * Outcome of the Listen control: a rendered transcript, not an OS permission
 * request. Pass requires the published segment count, the transcript attribute,
 * and visible `.listen-transcript` rows — the data attributes without the rows
 * is the helper-vs-JSX miss this harness exists to catch.
 *
 * red-proof: stub `data-consumer-semantic` at segments:0 with no transcript
 * rows. That is `empty-transcript`, never a pass.
 */
export function inspectListenTranscript(root) {
  const semantic = attr(root, "data-consumer-semantic");
  const match = /^listen:capture:[^:]+:segments:(\d+)$/.exec(semantic);
  const segments = match ? Number(match[1]) : 0;
  const transcript = attr(root, "data-consumer-transcript").trim();
  const rows = nodesOf(root, ".listen-transcript-row");
  const rowText = rows
    .map((row) => {
      const textNode = typeof row.querySelector === "function"
        ? row.querySelector(".listen-transcript-text")
        : null;
      return String(textNode?.textContent ?? row.textContent ?? "").trim();
    })
    .filter((text) => text.length > 0)
    .join(" ");
  if (segments > 0 && transcript.length > 0 && rows.length > 0 && rowText.length > 0) {
    return "transcript-rendered";
  }
  return "empty-transcript";
}

/**
 * Outcome of the Rewind control: a decoded picture, not an OS permission
 * request. The `.screen-frame-unavailable` paragraph is the defect this token
 * exists to catch — a timeline row can exist while the stage shows no image.
 *
 * red-proof: point the stage at that paragraph, or at an `img` whose src is
 * `data:image/png;base64,` with no payload / `naturalWidth` 0. Never a pass.
 */
export function inspectScreenFrame(root) {
  if (root?.querySelector?.(".screen-frame-unavailable")) return "frame-unavailable";
  const img = root?.querySelector?.("img.screen-frame-image");
  if (img == null) {
    if (root?.querySelector?.(".screen-frame-loading")) return "frame-loading";
    return "frame-missing";
  }
  const src = String(img.getAttribute?.("src") ?? img.src ?? "");
  if (!src.startsWith("data:image/png;base64,")) return "frame-not-png";
  const payload = src.slice("data:image/png;base64,".length).trim();
  if (payload.length === 0) return "frame-empty-bytes";
  const width = Number(img.naturalWidth);
  if (!Number.isFinite(width) || width <= 0) return "frame-undecoded";
  return "frame-rendered";
}

/**
 * Chat provenance is a conjunction of three witnesses. Any two agreeing
 * without the third is how a stub ships for a week.
 *
 * red-proof: boot the canned gateway (`omi.local-test-gateway.v1`) while
 * declaring `OMI_CHAT_MODEL=real`. Label and boot agree canned; intent does
 * not. That is `provenance-mismatch`, never `streamed-and-persisted`.
 */
export function inspectChatProvenance({ intent, boot, label, assistantText } = {}) {
  const rendered = String(label ?? "").trim();
  const text = String(assistantText ?? "");
  const kind = typeof boot?.gateway_kind === "string" ? boot.gateway_kind : null;
  const model = typeof boot?.gateway_model === "string" && boot.gateway_model.length > 0
    ? boot.gateway_model
    : null;
  const wantReal = intent === "real";

  if (kind == null) return "boot-missing";

  const bootIsCanned = kind === CANNED_GATEWAY_KIND;
  const bootIsReal = kind === REAL_GATEWAY_KIND;
  const labelIsCanned = rendered === CANNED_CHAT_LABEL;
  const labelIsReal = rendered.startsWith(REAL_CHAT_LABEL_PREFIX) && !labelIsCanned;

  if (wantReal) {
    if (!bootIsReal || !labelIsReal || labelIsCanned) return "provenance-mismatch";
    if (model != null && !rendered.includes(`(${model})`)) return "provenance-mismatch";
    if (text === CANNED_CHAT_ANSWER) return "canned-answer";
    return "agree";
  }

  if (!bootIsCanned || !labelIsCanned || labelIsReal) return "provenance-mismatch";
  if (text !== CANNED_CHAT_ANSWER) return "answer-mismatch";
  return "agree";
}

export function applyChatProvenance(steps, { intent, boot, rendered } = {}) {
  const next = [];
  for (const step of steps ?? []) {
    if (!step || step.slug !== "chat" || isSkip(step.verdict) || step.verdict !== "streamed-and-persisted") {
      next.push(step);
      continue;
    }
    const clause = inspectChatProvenance({
      intent,
      boot,
      label: rendered?.capabilityLabel,
      assistantText: rendered?.assistantText,
    });
    next.push(clause === "agree" ? step : { ...step, verdict: clause });
  }
  return next;
}

export function readServiceBoot(text) {
  let boot = null;
  for (const line of String(text ?? "").split(/\r?\n/)) {
    if (line.trim().length === 0) continue;
    try {
      const record = JSON.parse(line);
      if (record && record.event === "service.boot") boot = record;
    } catch {
      // JSONL skip
    }
  }
  return boot;
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
