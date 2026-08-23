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
  expect(source).toContain('window.toolbarStyle = NSWindowToolbarStyleUnified;');
  expect(source).toContain('window.title = @"";');
  expect(source).not.toContain('accessibilityLabel="Window drag handle"');
});

test('uses only the native local service configuration for macOS credentials', () => {
  const source = readNativeSource('OmiBackendModule.mm');

  expect(source).toContain('environment[@"OMI_LOCAL_BACKEND_URL"]');
  expect(source).toContain('environment[@"OMI_DEV_BACKEND"]');
  expect(source).toContain('NSURL URLWithString:@"http://127.0.0.1:8787"');
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
  expect(source).not.toContain('OMI_API_TOKEN');
  expect(source).not.toContain('OMI_API_CLIENT_ID');
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
  expect(source).toContain('self.sheen = [CALayer layer];');
  expect(source).toContain(
    'self.sheen.backgroundColor = [NSColor.whiteColor colorWithAlphaComponent:0.5].CGColor;',
  );
  expect(source).toContain(
    'self.scrim.backgroundColor = [NSColor.controlBackgroundColor colorWithAlphaComponent:alpha].CGColor;',
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
