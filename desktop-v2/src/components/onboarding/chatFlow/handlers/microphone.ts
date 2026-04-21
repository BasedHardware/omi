import { buildPermissionHandler } from "./_permissionFactory";

export const microphoneHandler = buildPermissionHandler({
  stepId: "microphone",
  kind: "microphone",
  label: "Grant microphone access",
  instruction:
    "Microphone permission. One sentence: you'll transcribe meetings and voice notes only when they explicitly start one.",
  fallback:
    "I'll need the mic to transcribe meetings and voice notes — only when you explicitly start one.",
  helper: "Audio is discarded; only the transcript stays.",
  linuxInformational: true,
});
