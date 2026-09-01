import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';

const pageShell = readFileSync(resolve(__dirname, 'PageShell.tsx'), 'utf8');
const desktopApp = readFileSync(
  resolve(__dirname, '../desktop/DesktopApp.tsx'),
  'utf8',
);

test('macOS PageShell does not inset the nav below the titlebar', () => {
  expect(pageShell).toContain('const content = macDesktop ? (');
  expect(pageShell).toContain('<View style={[styles.safe, styles.macSafe]}>');
  expect(pageShell).not.toMatch(
    /macDesktop\s*\?\s*<SafeAreaView|SafeAreaView style=\{\[styles\.safe, macDesktop/,
  );
});

test('DesktopApp keeps Home on the same row as the traffic-light spacer', () => {
  expect(desktopApp).toContain('paddingTop: desktopNavTopInset');
  expect(desktopApp).toContain('height: desktopNavBarHeight');
  expect(desktopApp).toContain('accessibilityLabel="Window controls"');
  expect(desktopApp).toContain('width: desktopTrafficLightRowWidth');
  expect(desktopApp).toContain('marginLeft: desktopTrafficLightLeading');
  expect(desktopApp).toContain('height: desktopTrafficLightButton');
  expect(desktopApp).toMatch(/root:\s*\{[^}]*paddingTop:\s*desktopNavTopInset/);
  expect(desktopApp).not.toMatch(/root:\s*\{[^}]*padding:\s*8/);
  expect(desktopApp).not.toMatch(/navbar:\s*\{[^}]*height:\s*52/);
  expect(desktopApp).toMatch(/navbar:\s*\{[^}]*alignItems:\s*'center'/);
  expect(desktopApp).toMatch(/navItem:\s*\{[^}]*alignItems:\s*'center'/);
  expect(desktopApp).toMatch(/navItem:\s*\{[^}]*justifyContent:\s*'center'/);
  expect(desktopApp).toContain('desktopSearchPlaceholder');
  expect(desktopApp).toMatch(/omnibar:\s*\{/);
});
