import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/experiments/on_device_overflow_gate.dart';
import 'package:omi/services/sockets/on_device_apple_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const batch = MethodChannel('com.omi/on_device');
  const speech = MethodChannel('com.omi.ios/speech');
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  for (final engine in ['sfspeech', 'parakeet_v2']) {
    test('overflow readiness probes the selected $engine engine and configured language', () async {
      final legacyCalls = <MethodCall>[];
      messenger.setMockMethodCallHandler(batch, (call) async {
        expect(call.arguments['language'], 'fr');
        return {'engine': engine, 'phase': 'installed'};
      });
      messenger.setMockMethodCallHandler(speech, (call) async {
        legacyCalls.add(call);
        expect(call.arguments['language'], 'fr');
        expect(call.arguments['useSpeechAnalyzer'], isFalse);
        return {'engine': 'sfspeech', 'status': 'ready'};
      });
      try {
        final state = await OnDeviceAppleProvider.readiness('fr');
        expect(state.ready, isTrue);
        expect(state.engine, engine);
        expect(legacyCalls.length, engine == 'sfspeech' ? 1 : 0);
      } finally {
        messenger.setMockMethodCallHandler(batch, null);
        messenger.setMockMethodCallHandler(speech, null);
      }
    }, skip: !OnDeviceOverflowGate.debugOverrideActive);
  }
}
