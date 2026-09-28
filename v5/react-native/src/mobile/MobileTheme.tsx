// Mobile appearance: System / Light / Dark, like the shipping Omi phone app.
// The shell resolves the preference against the OS scheme and provides the
// Omi design language (mobile density) to every mobile surface below it.
import React, {createContext, useCallback, useContext, useState} from 'react';
import {NativeModules, StatusBar, useColorScheme} from 'react-native';
import {OmiThemeProvider} from '../design/OmiTheme';
import type {OmiScheme} from '../design/tokens';

export type MobileAppearance = 'system' | 'light' | 'dark';

export const mobileAppearanceOptions: ReadonlyArray<{
  value: MobileAppearance;
  label: string;
}> = [
  {value: 'system', label: 'System'},
  {value: 'light', label: 'Light'},
  {value: 'dark', label: 'Dark'},
];

const storageKey = 'omi.mobile.appearance';

export function parseMobileAppearance(value: unknown): MobileAppearance {
  return value === 'light' || value === 'dark' ? value : 'system';
}

/** System follows the OS; an unknown OS scheme keeps the historical dark. */
export function resolveMobileScheme(
  appearance: MobileAppearance,
  system: string | null | undefined,
): OmiScheme {
  if (appearance !== 'system') {
    return appearance;
  }
  return system === 'light' ? 'light' : 'dark';
}

// Persistence: the phone apps store the choice natively (OmiNative:
// NSUserDefaults on iOS, SharedPreferences on Android) and export it as a
// startup constant so the first frame already uses it; the web build keeps it
// in localStorage. Without either, the choice lasts for the app process.
type AppearanceNative = {
  appearance?: unknown;
  getConstants?: () => {appearance?: unknown};
  setAppearance?: (appearance: MobileAppearance) => Promise<unknown>;
};

function appearanceNative(): AppearanceNative | null {
  return (NativeModules.OmiNative as AppearanceNative | undefined) ?? null;
}

function nativeStoredAppearance(): MobileAppearance | null {
  const native = appearanceNative();
  if (native === null) {
    return null;
  }
  try {
    const value = native.getConstants?.().appearance ?? native.appearance;
    return value === undefined ? null : parseMobileAppearance(value);
  } catch {
    return null;
  }
}

let processAppearance: MobileAppearance | null = null;

function webStorage(): Storage | null {
  try {
    return (globalThis as {localStorage?: Storage}).localStorage ?? null;
  } catch {
    return null;
  }
}

export function loadMobileAppearance(): MobileAppearance {
  if (processAppearance !== null) {
    return processAppearance;
  }
  try {
    const stored = webStorage()?.getItem(storageKey);
    if (stored != null) {
      return parseMobileAppearance(stored);
    }
  } catch {}
  return nativeStoredAppearance() ?? 'system';
}

export function saveMobileAppearance(appearance: MobileAppearance): void {
  processAppearance = appearance;
  try {
    webStorage()?.setItem(storageKey, appearance);
  } catch {}
  // Best effort: a failed native write only loses persistence, never the
  // in-process choice.
  appearanceNative()
    ?.setAppearance?.(appearance)
    ?.catch(() => undefined);
}

/** Test seam: forget the in-process choice. */
export function resetMobileAppearanceForTests(): void {
  processAppearance = null;
}

/** Stored appearance preference plus a setter that persists it. */
export function useMobileAppearance(): [
  MobileAppearance,
  (next: MobileAppearance) => void,
] {
  const [appearance, setAppearance] = useState(loadMobileAppearance);
  const update = useCallback((next: MobileAppearance) => {
    saveMobileAppearance(next);
    setAppearance(next);
  }, []);
  return [appearance, update];
}

type AppearanceControl = {
  appearance: MobileAppearance;
  setAppearance: (next: MobileAppearance) => void;
};

const MobileAppearanceContext = createContext<AppearanceControl | null>(null);

/** The Settings appearance control; null outside the mobile shell. */
export function useMobileAppearanceControl(): AppearanceControl | null {
  return useContext(MobileAppearanceContext);
}

export function MobileThemeRoot({
  appearance,
  onAppearanceChange,
  children,
}: {
  appearance: MobileAppearance;
  onAppearanceChange: (next: MobileAppearance) => void;
  children?: React.ReactNode;
}) {
  const scheme = resolveMobileScheme(appearance, useColorScheme());
  const control = React.useMemo(
    () => ({appearance, setAppearance: onAppearanceChange}),
    [appearance, onAppearanceChange],
  );
  return (
    <MobileAppearanceContext.Provider value={control}>
      <OmiThemeProvider scheme={scheme} density="mobile">
        <StatusBar
          barStyle={scheme === 'light' ? 'dark-content' : 'light-content'}
        />
        {children}
      </OmiThemeProvider>
    </MobileAppearanceContext.Provider>
  );
}

/**
 * Ink for the Omi mark on a mobile surface: the mark's own white on dark,
 * the theme ink on light.
 */
export function markInk(theme: {
  scheme: OmiScheme;
  color: {ink: string};
}): string | undefined {
  return theme.scheme === 'light' ? theme.color.ink : undefined;
}
