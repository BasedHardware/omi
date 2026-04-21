import { buildPermissionHandler } from "./_permissionFactory";

export const accessibilityHandler = buildPermissionHandler({
  stepId: "accessibility",
  kind: "accessibility",
  label: "Grant Accessibility",
  includeForPlatform: (p) => p === "macos",
  instruction:
    "Accessibility permission. One sentence: it lets you see which app they're focused on, never keystrokes.",
  fallback:
    "Accessibility lets me see which app you're focused on so my suggestions match what you're doing. Never keystrokes.",
  helper: "App + window only, not keystrokes or clipboard.",
});
