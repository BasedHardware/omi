import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';

const orchestrator = readFileSync(
  resolve(__dirname, 'src/app/AppOrchestrator.tsx'),
  'utf8',
);
const app = readFileSync(resolve(__dirname, 'App.tsx'), 'utf8');
const desktopApp = readFileSync(
  resolve(__dirname, 'src/desktop/DesktopApp.tsx'),
  'utf8',
);

test('the product entry keeps the canonical orchestrator', () => {
  expect(app).toContain('AppOrchestrator');
  expect(app).toContain('export default function App');
  expect(app).not.toContain('Saved data unavailable');
});

test('macOS chrome is DesktopApp after first paint for every session state', () => {
  expect(orchestrator).toMatch(/if \(macDesktop\) \{/);
  expect(orchestrator).not.toMatch(
    /if \(macDesktop && onboardingRequired === false\)/,
  );
  expect(orchestrator).toContain('<DesktopApp');
  expect(orchestrator).toContain('session=');
  expect(orchestrator).toContain('onSignIn=');
  expect(orchestrator).not.toContain('HomeRecovery');
  expect(orchestrator).not.toContain('HomeTimeline');
  expect(orchestrator).not.toContain('HomeSurface');
  expect(orchestrator).not.toContain("'Saved data unavailable'");
  expect(orchestrator).not.toContain('"Saved data unavailable"');
});

test('DesktopApp owns sign-in inside the search-first shell', () => {
  expect(desktopApp).toContain("Search what you've seen and heard");
  expect(desktopApp).toContain('signed-out');
  expect(desktopApp).toContain('Restoring your session');
  expect(desktopApp).not.toContain('Saved data unavailable');
  expect(desktopApp).not.toContain('Omi disconnected');
  expect(desktopApp).not.toContain('Welcome to Omi');
});
