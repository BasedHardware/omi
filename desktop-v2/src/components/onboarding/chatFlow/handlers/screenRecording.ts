import { buildPermissionHandler } from "./_permissionFactory";

export const screenRecordingHandler = buildPermissionHandler({
  stepId: "screen_recording",
  kind: "screen_recording",
  label: "Grant screen recording",
  includeForPlatform: (p) => p !== "linux",
  instruction:
    "Screen recording permission. One sentence: it lets Nooto see what's on screen so it can help with the thing you're actually doing, revocable any time in System Settings.",
  fallback:
    "Screen recording lets me see what's on your screen when you ask for help. You can revoke it any time in System Settings.",
  helper: "Captures stay local until you ask Nooto to act on them.",
});
