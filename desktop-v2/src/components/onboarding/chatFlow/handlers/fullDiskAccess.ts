import { buildPermissionHandler } from "./_permissionFactory";

export const fullDiskAccessHandler = buildPermissionHandler({
  stepId: "full_disk_access",
  kind: "full_disk_access",
  label: "Grant Full Disk Access",
  includeForPlatform: (p) => p === "macos",
  instruction:
    "Full Disk Access on macOS. One sentence: I read filenames only, never contents, to map your projects. Revocable anytime.",
  fallback:
    "Full Disk Access lets me read filenames and folders — never contents — so I can map what you're working on.",
  helper: "Filenames + paths only, never file contents.",
});
