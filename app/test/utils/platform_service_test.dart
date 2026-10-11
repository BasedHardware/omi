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

  test('fails closed on Darwin kernel strings instead of over-reporting', () {
    // Darwin strings lead with the kernel major, not the iOS major
    // (Darwin 21 is iOS 15, Darwin 24 is iOS 18), so treating that integer
    // as the marketing version would let a device pass `isIOSAtLeast(16)`
    // or `isIOSAtLeast(27)` gates it does not satisfy. Fail closed to 0.
    expect(PlatformService.iosMajorVersion('Darwin Kernel Version 24.5.0: Tue Apr  8 2026'), 0);
    expect(PlatformService.iosMajorVersion('Darwin Kernel Version 21.6.0: Wed Aug 10 13:17:20 PDT 2022'), 0);
  });

  test('returns 0 when no integer is present', () {
    expect(PlatformService.iosMajorVersion(''), 0);
    expect(PlatformService.iosMajorVersion('unknown'), 0);
  });
}
