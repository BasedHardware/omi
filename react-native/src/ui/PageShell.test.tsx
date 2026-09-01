import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';

const pageShell = readFileSync(resolve(__dirname, 'PageShell.tsx'), 'utf8');
const desktopApp = readFileSync(
  resolve(__dirname, '../desktop/DesktopApp.tsx'),
  'utf8',
);
const desktopChrome = readFileSync(
  resolve(__dirname, '../desktop/DesktopTopChrome.tsx'),
  'utf8',
);

test('macOS PageShell does not inset the nav below the titlebar', () => {
  expect(pageShell).toContain('const content = macDesktop ? (');
  expect(pageShell).toContain('<View style={[styles.safe, styles.macSafe]}>');
  expect(pageShell).not.toMatch(
    /macDesktop\s*\?\s*<SafeAreaView|SafeAreaView style=\{\[styles\.safe, macDesktop/,
  );
});

test('DesktopApp keeps an even window inset around one chrome row', () => {
  expect(desktopApp).toMatch(/root:\s*\{[^}]*padding:\s*desktopWindowInset/);
  expect(desktopChrome).toContain('height: desktopNavBarHeight');
  expect(desktopChrome).toContain('accessibilityLabel="Window controls"');
  expect(desktopChrome).toContain('width: desktopTrafficLightRowWidth');
  expect(desktopChrome).toContain('height: desktopTrafficLightButton');
  expect(desktopChrome).not.toContain('marginLeft');
  expect(desktopChrome).toMatch(/row:\s*\{[^}]*alignItems:\s*'center'/);
  expect(desktopChrome).toMatch(/navItem:\s*\{[^}]*alignItems:\s*'center'/);
  expect(desktopChrome).toMatch(/navItem:\s*\{[^}]*justifyContent:\s*'center'/);
  expect(desktopChrome).toContain('desktopSearchPlaceholder');
  expect(desktopChrome).toMatch(/omnibar:\s*\{/);
  expect(desktopChrome).toMatch(/omnibar:\s*\{[^}]*minWidth:\s*220/);
  expect(desktopChrome).not.toMatch(/navItem:\s*\{[^}]*borderRadius/);
  expect(desktopChrome).toMatch(
    /navTextActive:[^}]*textDecorationLine:\s*'underline'/,
  );
  expect(desktopChrome).toContain('accessibilityLabel="Settings"');
});
