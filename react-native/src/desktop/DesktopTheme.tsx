import React, {createContext, useContext, useMemo, useState} from 'react';
import {color as kitDark} from '../ui/tokens';
import type {DesktopThemeName, DesktopTokens} from './tokens';
export type {DesktopThemeName, DesktopTokens};
import {desktopThemeTokens} from './tokens';

// The shared kit palette (ui/tokens `color`) stays dark for the mobile
// surfaces that render without this provider. On the desktop shell the
// provider swaps in the light equivalents so kit buttons, fields, and rows
// match the window material.
const kitLight: {[K in keyof typeof kitDark]: string} = {
  canvas: '#f4f5f1',
  chrome: '#eceee9',
  chromeText: '#3a3d37',
  danger: '#c2402a',
  focus: '#0f766e',
  input: 'rgba(29, 31, 27, 0.08)',
  inputPressed: 'rgba(29, 31, 27, 0.12)',
  menu: 'rgba(250, 250, 248, 0.98)',
  menuText: '#3a3d37',
  menuTextStrong: '#23251f',
  line: 'rgba(29, 31, 27, 0.12)',
  lineStrong: 'rgba(29, 31, 27, 0.26)',
  primary: '#1d1f1b',
  primaryPressed: '#33362f',
  surface: '#f4f5f1',
  surfaceRaised: '#eceee9',
  text: '#1d1f1b',
  textInverse: '#f4f5f1',
  textMuted: '#5c5f58',
  textSubtle: '#8a8d85',
  transparent: 'transparent',
};

type DesktopThemeValue = {
  name: DesktopThemeName;
  tokens: DesktopTokens;
  kit: {[K in keyof typeof kitDark]: string};
  setName: (name: DesktopThemeName) => void;
};

// Outside the desktop shell (mobile surfaces, tests) the theme falls back to
// the historical dark palette so shared components keep rendering unchanged.
const fallback: DesktopThemeValue = {
  name: 'dark',
  tokens: desktopThemeTokens.dark,
  kit: kitDark,
  setName: () => undefined,
};

const DesktopThemeContext = createContext<DesktopThemeValue>(fallback);

export function DesktopThemeProvider({
  initialName = 'dark',
  onSetName,
  children,
}: {
  initialName?: DesktopThemeName;
  onSetName?: (name: DesktopThemeName) => void;
  children: React.ReactNode;
}) {
  const [name, setName] = useState<DesktopThemeName>(initialName);
  // The shell round-trips persistence through the parent (pref store →
  // prop), so re-sync when the incoming name changes.
  React.useEffect(() => {
    setName(initialName);
  }, [initialName]);
  const value = useMemo<DesktopThemeValue>(() => {
    const tokens = desktopThemeTokens[name];
    return {
      name,
      tokens,
      kit: name === 'light' ? kitLight : kitDark,
      setName: (next: DesktopThemeName) => {
        setName(next);
        onSetName?.(next);
      },
    };
  }, [name, onSetName]);
  return (
    <DesktopThemeContext.Provider value={value}>
      {children}
    </DesktopThemeContext.Provider>
  );
}

export function useDesktopTheme(): DesktopThemeValue {
  return useContext(DesktopThemeContext);
}

/**
 * Resolves a module-level style factory against the active theme tokens.
 * Convert `const styles = StyleSheet.create({...})` referencing tokens into
 * `const createStyles = (token: DesktopTokens) => StyleSheet.create({...})`
 * and call this hook inside the component.
 */
export function useDesktopStyleSheets<
  Factory extends (token: DesktopTokens) => Record<string, unknown>,
>(factory: Factory): ReturnType<Factory> {
  const {tokens} = useDesktopTheme();
  return useMemo(
    () => factory(tokens),
    [tokens, factory],
  ) as ReturnType<Factory>;
}

// The shared kit's static scales (radius, spacing, type…) stay as-is; only
// its `color` palette is themed. Kit primitives bind the whole tokens-shaped
// object through useDesktopTheme so mobile keeps the exact dark values.
import {
  border as kitBorder,
  icon as kitIcon,
  layout as kitLayout,
  opacity as kitOpacity,
  radius as kitRadius,
  size as kitSize,
  space as kitSpace,
  type as kitType,
} from '../ui/tokens';

export type KitTokens = {
  border: typeof kitBorder;
  color: {[K in keyof typeof kitDark]: string};
  icon: typeof kitIcon;
  layout: typeof kitLayout;
  opacity: typeof kitOpacity;
  radius: typeof kitRadius;
  size: typeof kitSize;
  space: typeof kitSpace;
  type: typeof kitType;
};

function themedKitTokens(color: KitTokens['color']): KitTokens {
  return {
    border: kitBorder,
    color,
    icon: kitIcon,
    layout: kitLayout,
    opacity: kitOpacity,
    radius: kitRadius,
    size: kitSize,
    space: kitSpace,
    type: kitType,
  };
}

export function useDesktopThemeKit(): {
  name: DesktopThemeName;
  tokens: KitTokens;
} {
  const {name, kit} = useDesktopTheme();
  return useMemo(() => ({name, tokens: themedKitTokens(kit)}), [name, kit]);
}

/**
 * Same as useDesktopStyleSheets, but for factories over the shared kit
 * tokens (ui/tokens shape) used by Button, Field, Sheet, SearchField,
 * Pressable, and PageShell.
 */
export function useKitStyleSheets<
  Factory extends (tokens: KitTokens) => Record<string, unknown>,
>(factory: Factory): ReturnType<Factory> {
  const {tokens} = useDesktopThemeKit();
  return useMemo(
    () => factory(tokens),
    [tokens, factory],
  ) as ReturnType<Factory>;
}
