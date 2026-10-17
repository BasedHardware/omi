import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/settings/device_settings.dart';

void main() {
  group('showDeviceDiagnosticsRow', () {
    test('a connected device always offers diagnostics', () {
      expect(showDeviceDiagnosticsRow(deviceId: 'pendant', isConnected: true, offlineEnabled: false), isTrue);
    });

    test('a disconnected device needs the offline flag', () {
      expect(showDeviceDiagnosticsRow(deviceId: 'pendant', isConnected: false, offlineEnabled: false), isFalse);
      expect(showDeviceDiagnosticsRow(deviceId: 'pendant', isConnected: false, offlineEnabled: true), isTrue);
    });

    test('no remembered device never offers diagnostics', () {
      expect(showDeviceDiagnosticsRow(deviceId: null, isConnected: false, offlineEnabled: true), isFalse);
    });
  });
}
