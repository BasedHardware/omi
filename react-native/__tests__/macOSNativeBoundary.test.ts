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

test('uses only the native local service configuration for macOS credentials', () => {
  const source = readNativeSource('OmiBackendModule.mm');

  expect(source).toContain('environment[@"OMI_LOCAL_BACKEND_URL"]');
  expect(source).toContain('NSURL URLWithString:@"http://127.0.0.1:8787"');
  expect(source).toContain('environment[@"OMI_LOCAL_API_TOKEN"]');
  expect(source).toContain('environment[@"OMI_LOCAL_API_CLIENT_ID"]');
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
