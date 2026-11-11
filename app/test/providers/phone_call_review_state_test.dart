import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/providers/phone_call_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const eventChannelName = 'com.omi/phone_calls/events';
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  setUp(() {
    messenger.setMockMessageHandler(eventChannelName, (message) async {
      return const StandardMethodCodec().encodeSuccessEnvelope(null);
    });
  });

  tearDown(() {
    messenger.setMockMessageHandler(eventChannelName, null);
  });

  test('app snapshot is readable without constructing the provider', () {
    expect(PhoneCallProvider.callStateListenable.value, PhoneCallState.idle);
  });

  test('snapshot follows call transitions and resets on clear and dispose', () {
    final provider = PhoneCallProvider.forTesting();
    var disposed = false;
    addTearDown(() {
      if (!disposed) provider.dispose();
    });

    final observed = <PhoneCallState>[];
    void listener() => observed.add(PhoneCallProvider.callStateListenable.value);
    PhoneCallProvider.callStateListenable.addListener(listener);
    addTearDown(() => PhoneCallProvider.callStateListenable.removeListener(listener));

    provider.debugSetCallStateForTesting(PhoneCallState.connecting);
    expect(PhoneCallProvider.callStateListenable.value, PhoneCallState.connecting);

    provider.clearUserData();
    expect(PhoneCallProvider.callStateListenable.value, PhoneCallState.idle);

    provider.debugSetCallStateForTesting(PhoneCallState.ringing);
    provider.dispose();
    disposed = true;
    expect(PhoneCallProvider.callStateListenable.value, PhoneCallState.idle);
    expect(observed, [PhoneCallState.connecting, PhoneCallState.idle, PhoneCallState.ringing, PhoneCallState.idle]);
  });
}
