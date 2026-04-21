import { invoke } from "@tauri-apps/api/core";

export type DesktopPlatform = "macos" | "windows" | "linux";

let cached: DesktopPlatform | null = null;

export async function getPlatform(): Promise<DesktopPlatform> {
  if (cached) return cached;
  try {
    const result = await invoke<string>("get_platform");
    const normalized = (result || "").toLowerCase();
    if (normalized.includes("mac") || normalized === "darwin") cached = "macos";
    else if (normalized.includes("win")) cached = "windows";
    else cached = "linux";
  } catch {
    const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
    if (/mac/i.test(ua)) cached = "macos";
    else if (/win/i.test(ua)) cached = "windows";
    else cached = "linux";
  }
  return cached;
}
