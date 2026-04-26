import { buildPermissionHandler } from "./_permissionFactory";

export const screenRecordingHandler = buildPermissionHandler({
  stepId: "screen_recording",
  kind: "screen_recording",
  label: "Grant screen & system audio",
  includeForPlatform: (p) => p !== "linux",
  instruction:
    "Screen & system audio recording permission. One sentence: it lets Nooto see what's on screen AND capture the other side of your meetings and calls (YouTube, Zoom, Meet), revocable any time in System Settings.",
  fallback:
    "Screen recording lets me see what's on your screen when you ask for help, and capture the other side of your meetings and calls (Zoom, Meet, YouTube, etc.). You can revoke it any time in System Settings.",
  helper:
    "Also gates meeting capture — without it, live transcripts only hear your mic, not the other side.",
});
