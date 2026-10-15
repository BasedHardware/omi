import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/services/siri_integration.dart';

/// PR #19946 review thread PRRT_kwDOLkKqys6nvzwv: the native omi/shortcuts_button
/// platform view is registered only by the Siri toolchain (Xcode 27). Stable-compiler
/// (Xcode 26.6) builds compile the registration out, so the Data & Privacy card must
/// never request the view unless the native bridge confirms availability.
void main() {
  group('SiriIntegration.appShortcutsAvailable', () {
    test('returns true when the native bridge reports the Siri toolchain', () async {
      final integration = SiriIntegration.forTest(
        _AvailabilityHost(true),
        'uid-1',
      );
      expect(await integration.appShortcutsAvailable(), isTrue);
    });

    test('returns false when the stable-compiler bridge reports unavailable', () async {
      final integration = SiriIntegration.forTest(
        _AvailabilityHost(false),
        'uid-1',
      );
      expect(await integration.appShortcutsAvailable(), isFalse);
    });

    test('fails closed to false when the native bridge throws', () async {
      final integration = SiriIntegration.forTest(
        _AvailabilityHost(null, throwOnProbe: true),
        'uid-1',
      );
      expect(await integration.appShortcutsAvailable(), isFalse);
    });

    test('fails closed to false when the native bridge never answers', () async {
      final integration = SiriIntegration.forTest(
        _AvailabilityHost(null, hangOnProbe: true),
        'uid-1',
        nativeTimeout: const Duration(milliseconds: 30),
      );
      expect(await integration.appShortcutsAvailable(), isFalse);
    });
  });

  group('Data & Privacy App Shortcuts card source invariant', () {
    final page = File('lib/pages/settings/data_privacy_page.dart');

    test('card renders only when the native probe confirms availability', () {
      final source = page.readAsStringSync();
      expect(
        RegExp(r'if\s*\(_shortcutsHintSupported\s*&&\s*_appShortcutsAvailable\)\s*\.\.\.\[').hasMatch(source),
        isTrue,
        reason: 'the siri_shortcuts_settings card must be gated on '
            '_shortcutsHintSupported && _appShortcutsAvailable so stable-compiler '
            '(Xcode 26.6) builds never request the unregistered omi/shortcuts_button view',
      );
    });

    test('UiKitView for omi/shortcuts_button stays inside the availability gate', () {
      final source = page.readAsStringSync();
      final gateIndex = source.indexOf('_appShortcutsAvailable) ...[');
      expect(gateIndex, greaterThan(0), reason: 'availability gate not found');
      final viewIndex = source.indexOf("UiKitView(viewType: 'omi/shortcuts_button')");
      expect(viewIndex, greaterThan(gateIndex), reason: 'the UiKitView must appear after the availability gate');
      // The gate must also precede the view: no earlier unguarded request exists.
      expect(source.indexOf("UiKitView(viewType: 'omi/shortcuts_button'"), greaterThanOrEqualTo(0));
    });

    test('page probes the native bridge when App Shortcuts could be supported', () {
      final source = page.readAsStringSync();
      expect(
        source.contains('if (_shortcutsHintSupported) _loadAppShortcutsAvailability();'),
        isTrue,
        reason: 'initState must probe availability before first render of the card',
      );
    });
  });
}

class _AvailabilityHost extends SiriIndexApi {
  _AvailabilityHost(this.available, {this.throwOnProbe = false, this.hangOnProbe = false});

  final bool? available;
  final bool throwOnProbe;
  final bool hangOnProbe;

  @override
  Future<bool> appShortcutsAvailable() async {
    if (throwOnProbe) throw StateError('bridge unavailable');
    if (hangOnProbe) await Completer<void>().future;
    return available ?? false;
  }
}
