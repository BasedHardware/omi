import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/platform/platform_service.dart';

void main() {
  test('parses the iOS marketing format the platform actually reports', () {
    // dart:io on iOS reports e.g. `Version 18.2 (Build 22C150)`; the buggy
    // split('.').first form captured `Version 18` and parsed null -> 0.
    expect(PlatformService.iosMajorVersion('Version 18.2 (Build 22C150)'), 18);
    expect(PlatformService.iosMajorVersion('Version 27.0 (Build 24E237)'), 27);
    expect(PlatformService.iosMajorVersion('Version 16.4.1'), 16);
  });

  test('parses Darwin uname strings conservatively', () {
    // Some builds report a Darwin kernel string; the leading kernel major is
    // the only integer available, so gates stay on the conservative side.
    expect(PlatformService.iosMajorVersion('Darwin Kernel Version 24.5.0: Tue Apr  8 2026'), 24);
  });

  test('returns 0 when no integer is present', () {
    expect(PlatformService.iosMajorVersion(''), 0);
    expect(PlatformService.iosMajorVersion('unknown'), 0);
  });
}
