import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';

const macOSRoot = resolve(__dirname, '../macos/RnRuntime-macOS');

function readNativeSource(fileName: string): string {
  return readFileSync(resolve(macOSRoot, fileName), 'utf8');
}

test('keeps a transparent glass window over the desktop', () => {
  const source = readNativeSource('AppDelegate.mm');

  expect(source).toContain('#import <React/RCTUIKit.h>');
  expect(source).toContain(
    'RCTUIView *rootView = (RCTUIView *)window.contentViewController.view;',
  );
  expect(source).toContain('rootView.backgroundColor = NSColor.clearColor;');
  expect(source).toContain('window.opaque = NO;');
  expect(source).toContain('window.backgroundColor = NSColor.clearColor;');
  expect(source).toContain(
    'window.appearance = [NSAppearance appearanceNamed:NSAppearanceNameAqua];',
  );
  expect(source).toContain('NSVisualEffectMaterialUnderWindowBackground');
  expect(source).not.toContain('OmiGlassPanelView');
  expect(source).not.toContain('setGlassCornerRadius:0');
  expect(source).toContain('hideOmiTitlebarMaterial');
  expect(source).not.toContain('NSWindowToolbarStyleUnified');
  expect(source).not.toContain('OmiTitlebarFillColor');
  expect(source).not.toContain('NSAppearanceNameVibrantDark');
});

test('puts traffic lights in the content chrome next to Home', () => {
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
  expect(source).toContain('window.movableByWindowBackground = NO;');
  expect(source).toContain('window.title = @"";');
  expect(source).toContain('NSWindowTitleHidden');
  expect(source).toContain('positionOmiTrafficLights');
  expect(source).toContain('OmiTrafficLightLeading');
  expect(source).toMatch(/OmiTrafficLightLeading\s*=\s*16\.0/);
  expect(source).toMatch(/OmiWindowInset\s*=\s*8\.0/);
  expect(source).toContain('NSWindowStyleMaskFullSizeContentView');
  expect(source).toContain('titlebarAppearsTransparent = YES');
  expect(source).toContain('NSTitlebarSeparatorStyleNone');
  expect(source).toContain('NSTitlebarAccessoryViewController');
  expect(source).toContain('installOmiTitlebarAccessory');
  expect(source).toContain('addTitlebarAccessoryViewController');
  expect(source).toMatch(/OmiTrafficLightChromeHeight\s*=\s*52\.0/);
  expect(source).toContain('hideOmiTitlebarMaterial');
  expect(source).not.toContain('NSWindowToolbarStyleUnified');
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
  expect(methodSource).toContain(
    'CGFloat x = OmiWindowInset + OmiTrafficLightLeading;',
  );
  expect(methodSource).toContain(
    'NSHeight(container.bounds) - OmiWindowInset - OmiTrafficLightChromeHeight',
  );
  expect(methodSource).not.toContain('frame.size =');
  expect(methodSource).not.toMatch(/button\.frame\s*=\s*NSMakeRect/);
});

test('pairs the macOS backend origin and credentials in one validated policy', () => {
  const source = readNativeSource('OmiBackendModule.mm');

  expect(source).toContain('OmiResolvedBackendPolicy');
  expect(source).not.toContain('OmiResolvedBaseURL');
  expect(source).not.toContain('OmiResolvedToken');
  expect(source).toContain('OmiBackendCredentialKindCloud');
  expect(source).toContain('OmiBackendCredentialKindLocal');
  expect(source).toContain('https://api.omi.me');
  expect(source).toContain('OmiIsCloudHost');
  expect(source).toContain('environment[@"OMI_CLOUD_API_TOKEN"]');
  expect(source).toContain('environment[@"OMI_API_TOKEN"]');
  expect(source).toContain('firebase-rest-tokens');
  expect(source).toContain('kSecUseAuthenticationUIFail');
  expect(source).toContain('environment[@"OMI_LOCAL_BACKEND_URL"]');
  expect(source).toContain('environment[@"OMI_V5_BACKEND_URL"]');
  expect(source).toContain('OmiValidatedV5URL');
  expect(source).toContain('OmiIsCaptureBackendPath');
  expect(source).toContain('OmiRequestBaseURL');
  expect(source).toContain('.workers.dev');
  expect(source).toContain('environment[@"OMI_DEV_BACKEND"]');
  expect(source).toContain('http://127.0.0.1:8787');
  expect(source).toContain('NSURL URLWithString:@"http://127.0.0.1:4851"');
  expect(source).toContain('#if DEBUG');
  expect(source).toContain(
    '![developmentBackend isEqualToString:@"example-platform"]',
  );
  expect(source).toContain('environment[@"OMI_LOCAL_API_TOKEN"]');
  expect(source).toContain('environment[@"OMI_LOCAL_API_CLIENT_ID"]');
  expect(source).toMatch(
    /if \(localToken\.length > 0 && localClient\.length > 0\) \{[^]*OmiLocalBaseURL/,
  );
  expect(source).not.toMatch(
    /if \([^\n]*localURL\.length > 0[^\n]*\) \{\s*return OmiLocalBaseURL/,
  );
  expect(source).toContain('OmiBackendPolicyIsValid');
  expect(source).toContain('OmiApplyAuthorization');
  expect(
    source.match(/OmiResolvedBackendPolicy\(/g)?.length,
  ).toBeGreaterThanOrEqual(4);
  expect(source.match(/resolveBackendPolicyWithCompletion/g)).toHaveLength(4);
  expect(source.match(/OmiApplyAuthorization\(/g)?.length).toBe(4);
  expect(source.match(/Bearer %@/g)).toHaveLength(1);
  expect(source).toContain('OmiExamplePlatformRequestSupported');
  expect(source).toContain('OmiDevelopmentBackendUnsupportedResponse');
  expect(source).toContain(
    'self.examplePlatformBackend && !OmiExamplePlatformRequestSupported(method, path)',
  );
  expect(source).toContain('omi.backend.softwarePlane');
  expect(source).toContain('OmiSoftwarePlaneIsNew');
  expect(source).toContain('RCT_REMAP_METHOD(setSoftwarePlane');
  expect(source).toContain('RCT_REMAP_METHOD(stampedV5BackendOrigin');
  expect(source).not.toContain(
    'omi-v5-backend-staging.undivisible.workers.dev',
  );
  const cloudBranch = source.slice(
    source.indexOf('OmiBackendCredentialKindCloud'),
    source.indexOf('static BOOL OmiBackendPolicyIsValid'),
  );
  expect(cloudBranch).toContain('OmiOwnKeychainCloudToken');
  expect(cloudBranch).toContain('environment[@"OMI_CLOUD_API_TOKEN"]');
  expect(cloudBranch).toContain('environment[@"OMI_API_TOKEN"]');
  expect(source.match(/environment\[@"OMI_CLOUD_API_TOKEN"\]/g)).toHaveLength(
    1,
  );
  expect(source.match(/environment\[@"OMI_API_TOKEN"\]/g)).toHaveLength(1);
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
  expect(backend).not.toContain('OmiKeychainCloudToken');
  expect(auth).toContain('OmiAuthImportShippingSessionIfNeeded');
  expect(auth).toContain('com.omi.desktop.firebase-rest-session');
  expect(auth).toContain('com.omi.computer-macos');
  expect(backend).toContain('OmiAuthImportShippingSessionIfNeeded');
});

test('signs out by deleting only this app firebase-rest-session keychain item', () => {
  const auth = readNativeSource('OmiAuthModule.mm');
  const header = readNativeSource('OmiAuthModule.h');
  const methodStart = auth.indexOf('RCT_REMAP_METHOD(signOut');
  expect(methodStart).toBeGreaterThan(-1);
  const methodEnd = auth.indexOf('@end', methodStart);
  const method = auth.slice(methodStart, methodEnd);

  expect(header).toContain(
    '@interface OmiAuthModule : NSObject <RCTBridgeModule>',
  );
  expect(auth).toContain('#import "OmiAuthModule.h"');
  expect(auth).toContain('RCT_EXPORT_MODULE(OmiAuth)');
  expect(method).toContain('OmiAuthClearSession');
  expect(method).toContain('OmiAuthSetEnvironmentCloudTokensIgnored(YES)');
  expect(method).toContain('OmiAuthSetShippingSessionIgnored(YES)');
  expect(method).toContain('errSecSuccess');
  expect(method).toContain('errSecItemNotFound');
  expect(method).toContain('@{@"signedOut" : @YES}');
  expect(method).toContain('OMI_AUTH_KEYCHAIN');
  expect(method).toContain('Could not clear the Omi cloud session');
  expect(method).toContain('NSOSStatusErrorDomain');
  expect(auth).toContain('com.omi.rnruntime.firebase-rest-session');
  expect(method).not.toContain('com.omi.desktop.firebase-rest-session');
  expect(method).not.toContain('authorization');
  expect(method).not.toContain('Bearer');
  expect(method).not.toContain('127.0.0.1');
  expect(method).not.toContain('/Applications/Omi.app');
  expect(method).not.toContain('omi.onboarding.completed');
  expect(method).not.toMatch(/NSLog\([^\n]*(token|Authorization)/i);
});

test('ignores environment cloud tokens after explicit sign-out until the next sign-in', () => {
  const auth = readNativeSource('OmiAuthModule.mm');
  const header = readNativeSource('OmiAuthModule.h');
  const backend = readNativeSource('OmiBackendModule.mm');

  expect(header).toContain('OmiAuthEnvironmentCloudTokensIgnored');
  expect(header).toContain('OmiAuthSetEnvironmentCloudTokensIgnored');
  expect(auth).toContain(
    'static BOOL OmiAuthIgnoreEnvironmentCloudTokens = NO',
  );
  expect(auth).toContain('OmiAuthSetEnvironmentCloudTokensIgnored(YES)');
  expect(auth).toContain('OmiAuthSetEnvironmentCloudTokensIgnored(NO)');
  expect(auth).toMatch(
    /hasCloudSessionWithResolver:[^]*if \(!OmiAuthEnvironmentCloudTokensIgnored\(\)\) \{[^]*OMI_CLOUD_API_TOKEN[^]*OMI_API_TOKEN[^]*\[self resolveStoredToken:/,
  );
  expect(
    auth.indexOf('OmiAuthSetEnvironmentCloudTokensIgnored(YES)'),
  ).toBeGreaterThan(auth.indexOf('RCT_REMAP_METHOD(signOut'));
  expect(
    auth.indexOf('OmiAuthSetEnvironmentCloudTokensIgnored(NO)'),
  ).toBeGreaterThan(auth.indexOf('finishSignInAttempt:'));
  expect(
    auth.indexOf('OmiAuthSetEnvironmentCloudTokensIgnored(NO)'),
  ).toBeLessThan(auth.indexOf('RCT_REMAP_METHOD(hasCloudSession'));
  expect(backend).toContain('OmiAuthEnvironmentCloudTokensIgnored()');
  expect(backend).toMatch(
    /if \(cloud\.length == 0 && !OmiAuthEnvironmentCloudTokensIgnored\(\)\) \{[^]*OMI_CLOUD_API_TOKEN[^]*OMI_API_TOKEN/,
  );
  expect(auth).not.toContain('unsetenv');
  expect(auth).not.toContain('.zshrc');
  expect(auth).not.toContain('.zprofile');
  expect(auth).not.toContain('.bashrc');
  expect(auth).not.toContain('launchctl');
  expect(auth).not.toMatch(
    /NSLog\([^\n]*(token|Authorization|OMI_CLOUD_API_TOKEN|OMI_API_TOKEN)/i,
  );
  expect(backend).not.toMatch(
    /NSLog\([^\n]*(token|Authorization|OMI_CLOUD_API_TOKEN|OMI_API_TOKEN)/i,
  );
});

test('refreshes expiring macOS cloud sessions without using stale tokens', () => {
  const auth = readNativeSource('OmiAuthModule.mm');
  const backend = readNativeSource('OmiBackendModule.mm');

  for (const source of [auth, backend]) {
    expect(source).toContain('expiryTime');
    expect(source).toContain('refreshToken');
    expect(source).toContain('firebaseApiKey');
    expect(source).toContain('https://securetoken.googleapis.com/v1/token');
  }
  expect(backend).toContain('grant_type" value:@"refresh_token');
  expect(backend).toContain('OmiClearOwnKeychainCloudSession');
  expect(backend).toContain('OmiCloudRefreshFailureIsDefinitive');
  expect(backend).not.toMatch(
    /NSLog\([^\n]*(idToken|refreshToken|Authorization)/i,
  );
  expect(auth).toContain('grant_type=refresh_token');
  expect(auth).toContain('OmiAuthClearSession');
  expect(auth).toContain('OmiAuthRefreshFailureIsDefinitive');
  expect(auth).toMatch(
    /hasCloudSessionWithResolver:[^]*\[self resolveStoredToken:[^]*resolve\(@\(token\.length > 0\)\)/,
  );
  expect(auth).toMatch(
    /if \(refreshToken\.length == 0\) \{[^]*OmiAuthClearSession\(\);[^]*completion\(nil, nil\)/,
  );
  expect(auth).not.toMatch(
    /NSLog\([^\n]*(idToken|refreshToken|Authorization)/i,
  );
});

test('validates loopback callbacks before success and keeps listening past probes', () => {
  const auth = readNativeSource('OmiAuthModule.mm');
  const validated = auth.slice(
    auth.indexOf('static NSURL *OmiAuthValidatedCallbackURL'),
    auth.indexOf('static NSURL *OmiAuthAcceptCallback'),
  );

  expect(auth).toContain('struct sockaddr_storage');
  expect(auth).toContain('getpeername');
  expect(auth).toContain('OmiAuthPeerIsLoopback');
  expect(auth).toContain('OmiAuthValidatedCallbackURL');
  expect(auth).toMatch(
    /while \(NSDate\.date\.timeIntervalSince1970 < deadline\)/,
  );
  expect(auth).toMatch(/if \(callbackURL == nil\) \{[^]*continue;/);
  expect(auth.indexOf('OmiAuthValidatedCallbackURL')).toBeLessThan(
    auth.indexOf('HTTP/1.1 200 OK'),
  );
  expect(auth).toContain('isEqualToString:@"GET"');
  expect(auth).toMatch(/HTTP\/1\.0[^]*HTTP\/1\.1/);
  expect(auth).toContain('HTTP/1.1 400 Bad Request');
  expect(auth).toMatch(
    /callback\.scheme[^]*callback\.host[^]*callback\.port[^]*callback\.path/,
  );
  expect(auth).toMatch(/values\[@"state"\][^]*values\[@"code"\]/);
  expect(validated).toMatch(/uint16_t port/);
  expect(validated).not.toContain(
    '@"http://127.0.0.1" stringByAppendingString:target',
  );
  expect(validated).toMatch(/http:\/\/127\.0\.0\.1:%u%@/);
  expect(auth).toMatch(
    /static NSURL \*OmiAuthAcceptCallback\(int listener,\s*uint16_t port,/,
  );
  expect(auth).toContain(
    'OmiAuthValidatedCallbackURL(request ?: @"", expectedState, port)',
  );
  expect(auth).toContain('OmiAuthAcceptCallback(listener, port, 180, state)');
});

test('does not reject sign-in when ASWebAuth cancels while loopback waits', () => {
  const auth = readNativeSource('OmiAuthModule.mm');
  const sessionStart = auth.indexOf(
    'initWithURL:authorize.URL callbackURLScheme:@"http"',
  );
  expect(sessionStart).toBeGreaterThan(-1);
  const handler = auth.slice(
    sessionStart,
    auth.indexOf(
      'self.authenticationSession.presentationContextProvider',
      sessionStart,
    ),
  );

  expect(handler).toContain('completeSignInWithCallback:callbackURL');
  expect(handler).not.toContain('completeSignInWithCallback:nil');
  expect(handler).toMatch(/if \(callbackURL == nil\) \{\s*return;/);
  expect(auth).toContain(
    '[self completeSignInWithCallback:callbackURL\n                                   state:state',
  );
});

test('clears the leftover loopback tab and returns the user to the app', () => {
  const auth = readNativeSource('OmiAuthModule.mm');

  expect(auth).not.toContain('OmiAuthSuccessPageHTML');
  expect(auth).not.toContain('<title>Signed in to Omi</title>');
  expect(auth).not.toContain('Signed in to Omi');
  expect(auth).not.toContain('This window closes itself');
  expect(auth).not.toContain('<circle ');
  expect(auth).not.toContain('radial-gradient');
  expect(auth).toContain("location.replace('about:blank')");
  expect(auth).toContain('window.close()');
  expect(auth).toContain('Content-Length');
  expect(auth).toContain('prefersEphemeralWebBrowserSession = YES');
  expect(auth).not.toContain('prefersEphemeralWebBrowserSession = NO');
  expect(auth).not.toContain('openURL:authorize.URL');
  expect(auth).not.toContain('hsl(');
  expect(auth).toContain('bringOmiToFront');
  expect(auth).toContain('[NSApp activate];');
  expect(auth).toContain('makeKeyAndOrderFront');
  expect(auth).toMatch(
    /finishSignInAttempt:[^]*\[self\.authenticationSession cancel\];[^]*OmiAuthSetEnvironmentCloudTokensIgnored\(NO\);[^]*resolve\(value\);[^]*\[self bringOmiToFront\];/,
  );
});

test('fences overlapping native macOS sign-in attempts', () => {
  const auth = readNativeSource('OmiAuthModule.mm');

  expect(auth).toContain('@property(nonatomic) NSUInteger signInAttempt;');
  expect(auth).toContain(
    '@property(nonatomic, copy) RCTPromiseRejectBlock pendingSignInReject;',
  );
  expect(auth).toMatch(
    /self\.signInAttempt \+= 1;[^]*\[self\.authenticationSession cancel\];[^]*\[self closeLoopback\];[^]*previousReject\(@"OMI_AUTH_UNAUTHORIZED"/,
  );
  expect(auth).toMatch(/if \(attempt != self\.signInAttempt\) return;/);
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

test('desktop settings persist preferences and request real macOS permissions', () => {
  const source = readNativeSource('OmiDesktopCommandsModule.mm');
  expect(source).toContain('RCT_REMAP_METHOD(loadDesktopPreferences');
  expect(source).toContain('RCT_REMAP_METHOD(setDesktopPreference');
  expect(source).toContain('screenAnalysisEnabled');
  expect(source).toContain('audioRecordingMode');
  expect(source).toContain('CGPreflightScreenCaptureAccess');
  expect(source).toContain('CGRequestScreenCaptureAccess');
  expect(source).toContain('AVCaptureDevice');
  expect(source).toContain('requestAuthorizationWithOptions');
  expect(source).not.toContain('CBCentralManager');
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
  expect(source).toContain('self.sheen.hidden = reduceTransparency;');
  expect(source).toContain(
    'CGFloat alpha = reduceTransparency ? 1.0 : OmiGlassScrimAlpha;',
  );
});

test('uses NSGlassEffectView per panel and HUD only as InkGlass fallback', () => {
  const source = readNativeSource('OmiGlassPanelView.mm');

  expect(source).toContain('static const CGFloat OmiGlassScrimAlpha = 0.46;');
  expect(source).toContain('NSAppearanceNameAqua');
  expect(source).toContain('NSClassFromString(@"NSGlassEffectView")');
  expect(source).toContain('self.liquidGlass');
  expect(source).toContain('self.sheen');
  expect(source).toContain('NSMaxY(self.bounds) - OmiGlassSheenHeight');
  expect(source).toContain(
    '[NSColor.whiteColor colorWithAlphaComponent:OmiGlassSheenAlpha]',
  );
  expect(source).toContain(
    'self.fallback.layer.backgroundColor = NSColor.controlBackgroundColor.CGColor;',
  );
  expect(source).toContain(
    'self.material.material = NSVisualEffectMaterialHUDWindow;',
  );
  expect(source).toMatch(
    /if \(self\.liquidGlass != nil\) \{\s*\[self addSubview:self\.liquidGlass\];/,
  );
  expect(source).toMatch(
    /if \(self\.liquidGlass == nil\) \{\s*self\.material = \[\[NSVisualEffectView alloc\]/,
  );
  expect(source).not.toContain(
    'self.material.hidden = reduceTransparency || hasLiquid;',
  );
  expect(source).not.toContain('self.appearance = nil;');
  expect(source).not.toContain('NSVisualEffectMaterialUnderWindowBackground');
  expect(source).not.toContain('NSAppearanceNameVibrantDark');
  expect(source).not.toContain('shadowColor');
  expect(source).not.toContain('shadowRadius');
  expect(source).not.toContain('shadowOpacity');
  expect(source).not.toContain('shadowOffset');
  expect(source).not.toContain('shadowPath');
  expect(source).toContain(
    'self.scrim.backgroundColor = [NSColor.controlBackgroundColor colorWithAlphaComponent:alpha].CGColor;',
  );
});

test('hosts React children in NSGlassEffectView contentView and clips to the panel', () => {
  const source = readNativeSource('OmiGlassPanelView.mm');

  expect(source).toContain(
    '@property (nonatomic, strong) NSView *contentHost;',
  );
  expect(source).toContain('setContentView:');
  expect(source).toContain('insertReactSubview');
  expect(source).toContain('removeReactSubview');
  expect(source).toContain('didUpdateReactSubviews');
  expect(source).toContain('self.clipsToBounds = YES');
  expect(source).toContain('self.layer.masksToBounds = YES');
  expect(source).toContain('[self.contentHost addSubview:subview');
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

test('does not construct CBCentralManager until an explicit scan or connect', () => {
  const source = readNativeSource('OmiNativeModule.mm');
  const initStart = source.indexOf('- (instancetype)init');
  expect(initStart).toBeGreaterThan(-1);
  const initSource = source.slice(
    initStart,
    source.indexOf('\n}\n', initStart),
  );
  expect(initSource).toContain('_lastEvent = @"Bluetooth adapter not checked"');
  expect(initSource).not.toContain('CBCentralManager');
  expect(initSource).not.toContain('initWithDelegate');

  const snapshotStart = source.indexOf('RCT_REMAP_METHOD(getSnapshot');
  const snapshotSource = source.slice(
    snapshotStart,
    source.indexOf('RCT_REMAP_METHOD(getBluetoothState', snapshotStart),
  );
  expect(snapshotSource).not.toContain('ensureCentral');
  expect(snapshotSource).not.toContain('initWithDelegate');

  const bluetoothStart = source.indexOf('RCT_REMAP_METHOD(getBluetoothState');
  const bluetoothSource = source.slice(
    bluetoothStart,
    source.indexOf('RCT_REMAP_METHOD(requestPermissions', bluetoothStart),
  );
  expect(bluetoothSource).not.toContain('ensureCentral');
  expect(bluetoothSource).not.toContain('initWithDelegate');

  expect(source).toContain('- (void)ensureCentral');
  expect(source).toContain(
    'self.central = [[CBCentralManager alloc] initWithDelegate:self queue:dispatch_get_main_queue()]',
  );
  const scanStart = source.indexOf('RCT_REMAP_METHOD(startScan');
  const scanSource = source.slice(
    scanStart,
    source.indexOf('RCT_REMAP_METHOD(stopScan', scanStart),
  );
  expect(scanSource).toContain('[self ensureCentral]');
  const connectStart = source.indexOf('RCT_REMAP_METHOD(connectDevice');
  const connectSource = source.slice(
    connectStart,
    source.indexOf('RCT_REMAP_METHOD(disconnectDevice', connectStart),
  );
  expect(connectSource).toContain('[self ensureCentral]');
  expect(source).toMatch(
    /bluetoothState \{[^]*if \(self\.central == nil\) \{[^]*return @"unknown"/,
  );
});

test('exposes a real OmiNative CoreBluetooth module instead of a hardware stub', () => {
  const source = readNativeSource('OmiNativeModule.mm');
  const header = readNativeSource('OmiNativeModule.h');
  const entitlements = readNativeSource('RnRuntime.entitlements');
  const info = readNativeSource('Info.plist');
  const pbxproj = readFileSync(
    resolve(__dirname, '../macos/RnRuntime.xcodeproj/project.pbxproj'),
    'utf8',
  );

  expect(header).toContain('RCTEventEmitter');
  expect(source).toContain('RCT_EXPORT_MODULE(OmiNative)');
  expect(source).toContain('#import <CoreBluetooth/CoreBluetooth.h>');
  expect(source).toContain('19b10000-e8f2-537e-4f6c-d104768a1214');
  expect(source).toContain('19b10001-e8f2-537e-4f6c-d104768a1214');
  expect(source).toContain('19b10002-e8f2-537e-4f6c-d104768a1214');
  expect(source).toContain('2A19');
  expect(source).toContain('timeoutSeconds');
  expect(source).toContain('self.scanResolve = resolve');
  expect(source).toContain('self.connectResolve = resolve');
  const connectStart = source.indexOf('RCT_REMAP_METHOD(connectDevice');
  const connectSource = source.slice(
    connectStart,
    source.indexOf('RCT_REMAP_METHOD(disconnectDevice', connectStart),
  );
  expect(connectSource).toContain('cancelPeripheralConnection:existing');
  expect(source).toContain(
    'self.connectedPeripheral != nil && self.connectedPeripheral != peripheral',
  );
  expect(source).toContain('characteristic.isNotifying');
  expect(source).toContain('self.audioNotifying ? @"recording" : @"idle"');
  const scanStart = source.indexOf('RCT_REMAP_METHOD(startScan');
  const scanSource = source.slice(
    scanStart,
    source.indexOf('RCT_REMAP_METHOD(stopScan', scanStart),
  );
  expect(scanSource).toContain('[self.devices removeAllObjects]');
  expect(scanSource).toContain('self.connectedPeripheral');
  expect(scanSource).toContain('self.devices[keepId] = kept');
  expect(source).not.toContain('.swift');
  expect(entitlements).toContain('com.apple.security.device.bluetooth');
  expect(entitlements).toContain('com.apple.security.app-sandbox');
  expect(entitlements).toContain('<false/>');
  expect(entitlements).toContain('com.apple.security.device.audio-input');
  expect(entitlements).toContain('com.apple.security.device.screen-capture');
  expect(info).toContain('NSBluetoothAlwaysUsageDescription');
  expect(pbxproj).toContain('OmiNativeModule.mm in Sources');
  expect(pbxproj).toContain('CoreBluetooth.framework');
  expect(pbxproj).toContain('CODE_SIGN_ENTITLEMENTS');
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
