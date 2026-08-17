import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi_webview_proto/main.dart';

void main() {
  test('shell appearance follows the selected surface theme before WebView paint', () {
    // red-proof: restore the former unconditional dark ThemeData/WebView/Scaffold
    // colors; light and system-light assertions fail on the first frame contract.
    expect(shellThemeModeForSurfaceQuery('?qa=tasks&theme=light'), ThemeMode.light);
    expect(shellThemeModeForSurfaceQuery('theme=dark&platform=mobile'), ThemeMode.dark);
    expect(shellThemeModeForSurfaceQuery('theme=auto'), ThemeMode.system);
    expect(shellThemeModeForSurfaceQuery('theme=unknown'), ThemeMode.system);
    expect(shellThemeModeForSurfaceQuery('%zz'), ThemeMode.system);

    expect(shellBrightnessForSurfaceQuery('theme=light', Brightness.dark), Brightness.light);
    expect(shellBrightnessForSurfaceQuery('theme=dark', Brightness.light), Brightness.dark);
    expect(shellBrightnessForSurfaceQuery('', Brightness.light), Brightness.light);
    expect(shellBackgroundForSurfaceQuery('theme=light', Brightness.dark), const Color(0xFFF5F7F9));
    expect(shellBackgroundForSurfaceQuery('theme=dark', Brightness.light), const Color(0xFF0B0B0F));
  });
}
