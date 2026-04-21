import { buildPermissionHandler } from "./_permissionFactory";

export const notificationsHandler = buildPermissionHandler({
  stepId: "notifications",
  kind: "notifications",
  label: "Allow notifications",
  instruction:
    "Notifications permission. One sentence: you only nudge when something is genuinely useful, never for engagement.",
  fallback:
    "I'll nudge you only when something is actually useful — never for engagement or streaks.",
  helper: "Mute anytime with one toggle.",
});
