import { buildPermissionHandler } from "./_permissionFactory";

export const automationHandler = buildPermissionHandler({
  stepId: "automation",
  kind: "automation",
  label: "Grant Automation",
  includeForPlatform: (p) => p === "macos",
  instruction:
    "Automation permission. One sentence: this lets Nooto actually act on their behalf when they ask — send, schedule, open.",
  fallback:
    "Automation lets me actually do things you ask for — send a message, schedule a follow-up, open a file.",
  helper: "Destructive actions always show a preview first.",
});
