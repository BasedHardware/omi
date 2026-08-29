import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';

const macOSRoot = resolve(__dirname, '../macos/RnRuntime-macOS');

function readNativeSource(fileName: string): string {
  return readFileSync(resolve(macOSRoot, fileName), 'utf8');
}

test('keeps the RN host surface clear while the stock titlebar carries a dark glass fill', () => {
  const source = readNativeSource('AppDelegate.mm');

  expect(source).toContain('#import <React/RCTUIKit.h>');
  expect(source).toContain(
    'RCTUIView *rootView = (RCTUIView *)window.contentViewController.view;',
  );
  expect(source).toContain('rootView.backgroundColor = NSColor.clearColor;');
  expect(source).toContain('window.opaque = NO;');
  expect(source).toContain('window.backgroundColor = OmiTitlebarFillColor();');
  expect(source).toMatch(/alpha:0\.8[0-9]\]/);
  expect(source).toContain(
    'window.appearance = [NSAppearance appearanceNamed:NSAppearanceNameVibrantDark];',
  );
  expect(source).not.toContain('window.backgroundColor = NSColor.clearColor;');
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
  expect(source).toContain('window.title = @"omi";');
  expect(source).toContain('window.titleVisibility = NSWindowTitleVisible');
  expect(source).not.toContain('window.title = @"";');
  expect(source).not.toContain('NSWindowTitleHidden');
  expect(source).toContain('positionOmiTrafficLights');
  expect(source).toContain('OmiTrafficLightLeading');
  expect(source).toMatch(/OmiTrafficLightLeading\s*=\s*1[234]\.0/);
  expect(source).not.toContain('FullSizeContentView');
  expect(source).toContain('titlebarAppearsTransparent = NO');
  expect(source).not.toContain('titlebarAppearsTransparent = YES');
  expect(source).toContain('NSTitlebarSeparatorStyleAutomatic');
  expect(source).not.toContain('NSTitlebarSeparatorStyleNone');
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
  expect(backend).not.toContain('com.omi.desktop.firebase-rest-session');
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
  expect(method).toContain('errSecSuccess');
  expect(method).toContain('errSecItemNotFound');
  expect(method).toContain('@{@"signedOut" : @YES}');
  expect(method).toContain('OMI_AUTH_KEYCHAIN');
  expect(method).toContain('Could not clear the Omi cloud session');
  expect(method).toContain('NSOSStatusErrorDomain');
  expect(auth).toContain('com.omi.rnruntime.firebase-rest-session');
  expect(auth).not.toContain('com.omi.desktop.firebase-rest-session');
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

test('serves a branded auto-closing success page and returns the user to the app', () => {
  const auth = readNativeSource('OmiAuthModule.mm');

  expect(auth).not.toContain('Signed in to Omi. You can close this window.');
  expect(auth).toContain('OmiAuthSuccessPageHTML');
  expect(auth).toContain('<title>Signed in to Omi</title>');
  expect(auth).toContain('window.close()');
  expect(auth).toContain('setTimeout(close');
  expect(auth).toContain('Content-Length');
  // The product mark only: eight white dots on dark glass, no rainbow.
  expect(auth.match(/<circle /g)).toHaveLength(8);
  expect(auth.match(/fill='#ffffff'/g)).toHaveLength(8);
  expect(auth).not.toContain('hsl(');
  // The session hands the foreground back to Omi once the code lands.
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
