import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';

const macOSRoot = resolve(__dirname, '../macos/RnRuntime-macOS');

function readNativeSource(fileName: string): string {
  return readFileSync(resolve(macOSRoot, fileName), 'utf8');
}

test('clears the React Native macOS host surface without making the window opaque', () => {
  const source = readNativeSource('AppDelegate.mm');

  expect(source).toContain('#import <React/RCTUIKit.h>');
  expect(source).toContain(
    'RCTUIView *rootView = (RCTUIView *)window.contentViewController.view;',
  );
  expect(source).toContain('rootView.backgroundColor = NSColor.clearColor;');
  expect(source).toContain('window.opaque = NO;');
  expect(source).toContain('window.backgroundColor = NSColor.clearColor;');
});

test('uses standard visible macOS traffic lights with native window dragging', () => {
  const source = readNativeSource('AppDelegate.mm');

  expect(source).toContain(
    '[window standardWindowButton:NSWindowCloseButton].hidden = NO;',
  );
  expect(source).toContain(
    '[window standardWindowButton:NSWindowMiniaturizeButton].hidden = NO;',
  );
  expect(source).toContain(
    '[window standardWindowButton:NSWindowZoomButton].hidden = NO;',
  );
  expect(source).toContain('window.movableByWindowBackground = YES;');
  expect(source).toMatch(
    /window\.toolbarStyle = NSWindowToolbarStyle(?:Automatic|Preference);/,
  );
  expect(source).toContain('window.title = @"";');
  expect(source).toContain('positionOmiTrafficLights');
  expect(source).toContain('OmiTrafficLightLeading');
  expect(source).toMatch(/OmiTrafficLightLeading\s*=\s*1[234]\.0/);
  expect(source).not.toContain('NSTitlebarAccessoryViewController');
  expect(source).not.toContain('installOmiTitlebarAccessory');
  expect(source).not.toContain('omiTitlebarAccessory');
  expect(source).not.toContain('addTitlebarAccessoryViewController');
  expect(source).not.toMatch(/OmiTrafficLightChromeHeight\s*-\s*28\.0/);
  expect(source).not.toMatch(/OmiTrafficLightChromeHeight\s*=\s*52\.0/);
  expect(source).not.toContain('accessibilityLabel="Window drag handle"');
});

test('keeps every traffic light at its native standard size and moves only its origin', () => {
  const source = readNativeSource('AppDelegate.mm');
  const methodStart = source.indexOf('- (void)positionOmiTrafficLights');
  expect(methodStart).toBeGreaterThan(-1);
  const methodEnd = source.indexOf('\n}', methodStart);
  const methodSource = source.slice(methodStart, methodEnd);

  expect(methodSource).toContain(
    'for (NSButton *button in @[ closeButton, miniaturizeButton, zoomButton ])',
  );
  expect(methodSource).toContain(
    'CGFloat buttonWidth = NSWidth(closeButton.frame);',
  );
  expect(methodSource).toContain(
    'CGFloat buttonHeight = NSHeight(closeButton.frame);',
  );
  expect(methodSource).toContain('frame.origin = NSMakePoint(x, y);');
  expect(methodSource).toContain('x += buttonWidth + OmiTrafficLightSpacing;');
  expect(methodSource).not.toContain('frame.size =');
  expect(methodSource).not.toMatch(/button\.frame\s*=\s*NSMakeRect/);
});

test('defaults the macOS backend to cloud and keeps local 8787 as fallback', () => {
  const source = readNativeSource('OmiBackendModule.mm');

  expect(source).toContain('OmiResolvedBaseURL');
  expect(source).toContain('https://api.omi.me');
  expect(source).toContain('OmiIsCloudHost');
  expect(source).toContain('environment[@"OMI_CLOUD_API_TOKEN"]');
  expect(source).toContain('environment[@"OMI_API_TOKEN"]');
  expect(source).toContain('firebase-rest-tokens');
  expect(source).toContain('kSecUseAuthenticationUIFail');
  expect(source).toContain('environment[@"OMI_LOCAL_BACKEND_URL"]');
  expect(source).toContain('environment[@"OMI_DEV_BACKEND"]');
  expect(source).toContain('http://127.0.0.1:8787');
  expect(source).toContain('NSURL URLWithString:@"http://127.0.0.1:4851"');
  expect(source).toContain('#if DEBUG');
  expect(source).toContain(
    '![developmentBackend isEqualToString:@"example-platform"]',
  );
  expect(source).toContain('environment[@"OMI_LOCAL_API_TOKEN"]');
  expect(source).toContain('environment[@"OMI_LOCAL_API_CLIENT_ID"]');
  expect(source).toContain('OmiExamplePlatformRequestSupported');
  expect(source).toContain('OmiDevelopmentBackendUnsupportedResponse');
  expect(source).toContain(
    'self.examplePlatformBackend && !OmiExamplePlatformRequestSupported(method, path)',
  );
});

test('owns an in-app PKCE sign-in session and stores its cloud token locally', () => {
  const auth = readNativeSource('OmiAuthModule.mm');
  const backend = readNativeSource('OmiBackendModule.mm');

  expect(auth).toContain('RCT_EXPORT_MODULE(OmiAuth)');
  expect(auth).toContain('RCT_REMAP_METHOD(signIn');
  expect(auth).toContain('RCT_REMAP_METHOD(hasCloudSession');
  expect(auth).toContain('ASWebAuthenticationSession');
  expect(auth).toContain('listen');
  expect(auth).toContain('accept');
  expect(auth).toContain('/v1/auth/authorize');
  expect(auth).toContain('/v1/auth/token');
  expect(auth).toContain('code_challenge_method');
  expect(auth).toContain('S256');
  expect(auth).toContain('firebase-rest-tokens');
  expect(auth).toContain('SecItemAdd');
  expect(auth).not.toMatch(/NSLog\([^\n]*(token|Authorization)/i);
  expect(backend.indexOf('OmiOwnKeychainCloudToken')).toBeGreaterThan(-1);
  expect(backend.indexOf('OmiOwnKeychainCloudToken')).toBeLessThan(
    backend.indexOf('environment[@"OMI_CLOUD_API_TOKEN"]'),
  );
});

test('persists completed macOS onboarding in this app NSUserDefaults', () => {
  const auth = readNativeSource('OmiAuthModule.mm');

  expect(auth).toContain('RCT_REMAP_METHOD(hasCompletedOnboarding');
  expect(auth).toContain('RCT_REMAP_METHOD(markOnboardingComplete');
  expect(auth).toContain('NSUserDefaults.standardUserDefaults');
  expect(auth).toContain('@"omi.onboarding.completed"');
  expect(auth).toContain('boolForKey');
  expect(auth).toContain('setBool:YES');
});

test('renders macOS chrome icons as named SF Symbols', () => {
  const source = readNativeSource('OmiSFSymbolView.mm');
  expect(source).toContain('RCT_EXPORT_MODULE(OmiSFSymbol)');
  expect(source).toContain('RCT_EXPORT_VIEW_PROPERTY(symbolName, NSString)');
  expect(source).toContain('imageWithSystemSymbolName');
  expect(source).toContain('configurationWithPointSize');
});

test('glass material never swallows hits', () => {
  const source = readNativeSource('OmiGlassPanelView.mm');
  expect(source).toContain('- (NSView *)hitTest:(NSPoint)point');
  expect(source).toContain('return nil;');
  expect(source).toContain('return NO;');
});

test('keeps the glass reduce-transparency fallback intact', () => {
  const source = readNativeSource('OmiGlassPanelView.mm');

  expect(source).toContain('@property (nonatomic, strong) NSView *fallback;');
  expect(source).toContain('self.fallback.hidden = !reduceTransparency;');
  expect(source).toContain('self.material.hidden = reduceTransparency;');
  expect(source).toContain(
    'CGFloat alpha = reduceTransparency ? 1.0 : OmiGlassScrimAlpha;',
  );
});

test('keeps the shared HUD material translucent with a semantic opaque fallback', () => {
  const source = readNativeSource('OmiGlassPanelView.mm');

  expect(source).toContain('static const CGFloat OmiGlassScrimAlpha = 0.14;');
  expect(source).toContain(
    'self.fallback.layer.backgroundColor = NSColor.controlBackgroundColor.CGColor;',
  );
  expect(source).toContain(
    'self.material.material = NSVisualEffectMaterialHUDWindow;',
  );
  expect(source).toContain('self.appearance = nil;');
  expect(source).toContain('self.layer.borderWidth = 0;');
  expect(source).not.toContain('NSAppearanceNameAqua');
  expect(source).not.toContain('self.sheen');
  expect(source).not.toContain('NSMaxY(self.bounds) - 1.0');
  expect(source).not.toContain(
    '[NSColor.whiteColor colorWithAlphaComponent:0.5]',
  );
  expect(source).toContain(
    'self.scrim.backgroundColor = [NSColor.controlBackgroundColor colorWithAlphaComponent:alpha].CGColor;',
  );
});

test('lets the host choose the glass radius so one panel can run full-bleed', () => {
  const source = readNativeSource('OmiGlassPanelView.mm');

  expect(source).toContain(
    'RCT_EXPORT_VIEW_PROPERTY(glassCornerRadius, CGFloat)',
  );
  expect(source).toMatch(/defaultCornerRadius\s*=\s*22\.0/);
  expect(source).not.toMatch(
    /shadowPath\s*=\s*\[NSBezierPath[^]*?xRadius:OmiGlassCornerRadius/,
  );
});

test('treats a generation transport failure with no HTTP response as an error', () => {
  const source = readNativeSource('OmiBackendModule.mm');
  const didCompleteIndex = source.indexOf('didCompleteWithError:');
  expect(didCompleteIndex).toBeGreaterThan(-1);
  const methodEnd = source.indexOf('@end', didCompleteIndex);
  const methodSource = source.slice(didCompleteIndex, methodEnd);
  expect(methodSource).toMatch(
    /if\s*\(\s*self\.responseStatus\s*!=\s*0\s*&&\s*self\.responseStatus\s*!=\s*200\s*\)/,
  );
  expect(methodSource).toContain(
    'Native generation transport failed before an HTTP response',
  );
});
