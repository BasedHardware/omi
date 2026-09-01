import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';

const orchestrator = readFileSync(
  resolve(__dirname, 'src/app/AppOrchestrator.tsx'),
  'utf8',
);
const app = readFileSync(resolve(__dirname, 'App.tsx'), 'utf8');

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
  expect(onboarding).toContain("import {omiAuth} from '../omiNative'");
  expect(onboarding).not.toMatch(/import \{[^}]*\bomiNative\b/);
  expect(onboarding).not.toContain('getSnapshot');
  expect(onboarding).not.toContain('useNativeDevices');
  expect(onboarding).not.toContain('CBCentral');
  expect(onboarding).not.toContain('startScan');
  const desktopMount = orchestrator.slice(
    orchestrator.indexOf('<DesktopApp'),
    orchestrator.indexOf('</PageShell>', orchestrator.indexOf('<DesktopApp')),
  );
  expect(desktopMount).toContain('onboardingRequired');
  expect(desktopMount).toContain("? 'probing'");
  expect(desktopMount).toContain("'signed-out'");
  expect(desktopMount).not.toContain('nativeSnapshot');
  expect(desktopMount).not.toContain('omiNative');
  expect(desktopMount).not.toContain('useNativeDevices');
});

test('DesktopApp owns sign-in inside the search-first shell', () => {
  const chrome = readFileSync(
    resolve(__dirname, 'src/desktop/desktopChrome.ts'),
    'utf8',
  );
  const desktopKit = [
    'src/desktop/DesktopApp.tsx',
    'src/desktop/DesktopTopChrome.tsx',
    'src/desktop/DesktopHome.tsx',
  ]
    .map(path => readFileSync(resolve(__dirname, path), 'utf8'))
    .join('\n');
  expect(chrome).toContain("Search what you've seen and heard");
  expect(desktopKit).toContain('desktopSearchPlaceholder');
  expect(desktopKit).toContain('signed-out');
  expect(desktopKit).toContain('Restoring your session');
  expect(desktopKit).not.toContain('Saved data unavailable');
  expect(desktopKit).not.toContain('Omi disconnected');
  expect(desktopKit).not.toContain('Welcome to Omi');
});
