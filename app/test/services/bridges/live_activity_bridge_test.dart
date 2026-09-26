import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/bridges/live_activity_bridge.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel(LiveActivityBridge.channelName);
  final calls = <MethodCall>[];

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    calls.clear();
    binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call);
      return null;
    });
  });

  tearDown(() => binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, null));

  test('old owner cleanup preserves the new native action handler and preference', () async {
    final old = LiveActivityBridge();
    final current = LiveActivityBridge();
    var oldActions = 0;
    var newActions = 0;
    await old.start((_) async {
      oldActions++;
      return {};
    });
    final oldOwner = calls.last.arguments;
    await current.start((_) async {
      newActions++;
      return {'handled': true};
    });
    final newOwner = calls.last.arguments;
    expect(newOwner, isNot(oldOwner));
    await old.close();
    expect(calls.where((call) => call.method == 'detach'), isEmpty);

    final result = Completer<ByteData?>();
    binding.defaultBinaryMessenger.handlePlatformMessage(
      channel.name,
      const StandardMethodCodec().encodeMethodCall(const MethodCall('action', {'action': 'pause'})),
      result.complete,
    );
    expect(const StandardMethodCodec().decodeEnvelope((await result.future)!), {'handled': true});
    expect(oldActions, 0);
    expect(newActions, 1);

    await SharedPreferencesUtil().setShowCaptureLiveActivity(false);
    await current.publish({'recordingId': 'recording'});
    expect(calls.last.arguments['enabled'], false);
    expect(calls.last.arguments['ownerId'], newOwner);
    await current.close();
    expect(calls.last.method, 'detach');
    expect(calls.last.arguments, newOwner);
  });
}
