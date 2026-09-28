import React, {createContext, useContext, useMemo} from 'react';
import {StyleSheet} from 'react-native';
import {
  omiTheme,
  type OmiDensity,
  type OmiScheme,
  type OmiTheme,
} from './tokens';

const OmiThemeContext = createContext<OmiTheme>(omiTheme('dark', 'mobile'));

/**
 * Provides the Omi design language to a subtree. The desktop shell mounts it
 * from DesktopThemeProvider (appearance preference, desktop density); the
 * mobile shell mounts it with mobile density. Outside any provider the
 * default is dark/mobile, matching the historical v5 fallback.
 */
export function OmiThemeProvider({
  scheme,
  density,
  children,
}: {
  scheme: OmiScheme;
  density: OmiDensity;
  children: React.ReactNode;
}) {
  const value = useMemo(() => omiTheme(scheme, density), [scheme, density]);
  return (
    <OmiThemeContext.Provider value={value}>
      {children}
    </OmiThemeContext.Provider>
  );
}

export function useOmiTheme(): OmiTheme {
  return useContext(OmiThemeContext);
}

/** Memoised StyleSheet built from the active theme. */
export function useOmiStyles<T extends StyleSheet.NamedStyles<T>>(
  factory: (theme: OmiTheme) => T,
): T {
  const theme = useOmiTheme();
  // The factory is expected to be a module-level function.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => StyleSheet.create(factory(theme)), [theme]);
}
