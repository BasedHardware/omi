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

test('macOS first paint and session probe do not require native devices or BLE', () => {
  const onboarding = readFileSync(
    resolve(__dirname, 'src/app/useOnboarding.ts'),
    'utf8',
  );

  expect(orchestrator).toMatch(
    /useNativeDevices\(\{\s*enabled:\s*!macDesktop\s*\}\)/,
  );
  expect(orchestrator).not.toMatch(/useNativeDevices\(\)/);
  expect(onboarding).toContain('hasCloudSession');
  expect(onboarding).toContain('setOnboardingRequired(!hasSession)');
  expect(onboarding).not.toContain(
    'setOnboardingRequired(!completed && !hasSession)',
  );
  expect(onboarding).not.toContain('omiNative');
  expect(onboarding).not.toContain('getSnapshot');
  expect(onboarding).not.toContain('useNativeDevices');
  expect(onboarding).not.toContain('CBCentral');
  expect(onboarding).not.toContain('startScan');
  const sessionBlock = orchestrator.slice(
    orchestrator.indexOf('session='),
    orchestrator.indexOf('signingIn={signingIn}'),
  );
  expect(sessionBlock).toContain('onboardingRequired');
  expect(sessionBlock).not.toContain('nativeSnapshot');
  expect(sessionBlock).not.toContain('omiNative');
  expect(sessionBlock).not.toContain('useNativeDevices');
});

test('DesktopApp owns sign-in inside the search-first shell', () => {
  expect(desktopApp).toContain("Search what you've seen and heard");
  expect(desktopApp).toContain('signed-out');
  expect(desktopApp).toContain('Restoring your session');
  expect(desktopApp).not.toContain('Saved data unavailable');
  expect(desktopApp).not.toContain('Omi disconnected');
  expect(desktopApp).not.toContain('Welcome to Omi');
});
