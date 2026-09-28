// Mobile appearance: System / Light / Dark, like the shipping Omi phone app.
// The shell resolves the preference against the OS scheme and provides the
// Omi design language (mobile density) to every mobile surface below it.
import React, {createContext, useCallback, useContext, useState} from 'react';
import {StatusBar, useColorScheme} from 'react-native';
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

// Persistence: the web build keeps the choice in localStorage. The phone
// shells have no JS-reachable preference store yet (adding one is native
// work), so there the choice lasts for the app process.
let processAppearance: MobileAppearance = 'system';

function webStorage(): Storage | null {
  try {
    return (globalThis as {localStorage?: Storage}).localStorage ?? null;
  } catch {
    return null;
  }
}

export function loadMobileAppearance(): MobileAppearance {
  try {
    const stored = webStorage()?.getItem(storageKey);
    if (stored != null) {
      return parseMobileAppearance(stored);
    }
  } catch {}
  return processAppearance;
}

export function saveMobileAppearance(appearance: MobileAppearance): void {
  processAppearance = appearance;
  try {
    webStorage()?.setItem(storageKey, appearance);
  } catch {}
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
