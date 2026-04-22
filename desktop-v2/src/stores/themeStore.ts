/**
 * Theme store — user's light/dark preference with a "system" option that
 * tracks `prefers-color-scheme`.
 *
 * Applies the `.dark` class to `<html>` so Tailwind's dark variant and the
 * app's CSS variables resolve to the correct palette. Persisted to
 * `localStorage` under `nooto.theme.mode`.
 */

import { create } from "zustand";

export type ThemeMode = "system" | "light" | "dark";

const STORAGE_KEY = "nooto.theme.mode";

function readStored(): ThemeMode {
  if (typeof window === "undefined") return "system";
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    // ignore
  }
  return "system";
}

function systemPrefersDark(): boolean {
  if (typeof window === "undefined") return true;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function resolve(mode: ThemeMode): "light" | "dark" {
  if (mode === "system") return systemPrefersDark() ? "dark" : "light";
  return mode;
}

/** Imperatively applies the resolved theme class to `<html>`. */
export function applyThemeClass(mode: ThemeMode): void {
  if (typeof document === "undefined") return;
  const resolved = resolve(mode);
  document.documentElement.classList.toggle("dark", resolved === "dark");
}

// Wire a single `prefers-color-scheme` listener. It only takes effect when
// the user has selected "system"; otherwise the manual choice wins.
let mqlBound = false;
function bindSystemListener(store: { getState: () => ThemeState }) {
  if (mqlBound || typeof window === "undefined") return;
  mqlBound = true;
  const mql = window.matchMedia("(prefers-color-scheme: dark)");
  const handler = () => {
    if (store.getState().mode === "system") {
      applyThemeClass("system");
    }
  };
  mql.addEventListener("change", handler);
}

interface ThemeState {
  mode: ThemeMode;
  /** The resolved concrete theme — recomputed on every change. */
  resolved: "light" | "dark";
  setMode: (mode: ThemeMode) => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  mode: readStored(),
  resolved: resolve(readStored()),
  setMode: (mode) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // ignore
    }
    applyThemeClass(mode);
    set({ mode, resolved: resolve(mode) });
  },
}));

/** Run once from `main.tsx` before React mounts to avoid a FOUC. */
export function initTheme(): void {
  const mode = useThemeStore.getState().mode;
  applyThemeClass(mode);
  bindSystemListener(useThemeStore);
}
