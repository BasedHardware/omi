import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

/// The server keeps a mobile conversation open when /v4/listen closes, so a
/// reconnect continues it. Only the user's Stop may say "finalize now", via a
/// `finalization_reason: user_stop` frame sent after the last audio, right
/// before the close. Drops and disconnects must stay silent.
void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  final userStop = jsonEncode(const {'type': 'finalization_reason', 'reason': 'user_stop'});
  bool isUserStop(String frame) => frame == userStop;

  int userStops() => world.sockets.expand((s) => s.transport.wire).where(isUserStop).length;

  /// Exactly one user-stop frame: after every audio frame, immediately before the close.
  void expectUserStopThenClose(ScriptedPureSocket socket) {
    final at = socket.wire.indexWhere(isUserStop);
    expect(at, isNonNegative, reason: 'the user stop must reach the server');
    expect(socket.wire.sublist(at + 1), ['<close>']);
    expect(socket.wire.lastIndexOf('<binary>'), lessThan(at));
    expect(userStops(), 1);
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_user_stop_');
    world = await CaptureReplayWorld.boot(tempDir: directory, pendantCodec: BleAudioCodec.opus);
  });

  tearDown(() async {
    await world.controller.pendingSourceSwitch;
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  group('phone recording', () {
    Future<void> recordPhone() async {
      await world.startLiveCapture();
      final sessionId = world.hostApi.lastStartSessionId!;
      world.emitNativeState(PhoneMicCaptureState.running);
      world.injectAudioFrames(50, sessionId: sessionId);
      await world.settle();
      expect(world.socket!.sentBinary, isNotEmpty);
    }

    test('Stop sends one user_stop after the last audio and right before close', () async {
      await recordPhone();
      final socket = world.socket!;

      await world.stopLiveCapture();

      expect(socket.closeCalls, 1);
      expectUserStopThenClose(socket);
    });

    test('a socket drop and its reconnect send no user_stop; the later Stop sends one', () async {
      await recordPhone();
      final dropped = world.socket!;

      dropped.emitClose(1006);
      await world.settle();
      await world.elapse(const Duration(seconds: 5));
      expect(world.sockets.length, greaterThan(1), reason: 'the drop must reconnect');
      expect(userStops(), 0);

      await world.stopLiveCapture();
      expect(dropped.wire.where(isUserStop), isEmpty);
      expectUserStopThenClose(world.socket!);
    });
  });

  group('pendant', () {
    Future<void> connectPendant() async {
      world.deviceConnection = ScriptedDeviceConnection(orphanDeviceId: pendant.id);
      await world.controller.streamDeviceRecording(device: pendant);
      await world.settle();
      world.deviceConnection!.emitAudio();
      await world.settle();
      expect(world.socket!.status, PureSocketStatus.connected);
    }

    test('an explicit stop sends one user_stop right before close', () async {
      await connectPendant();
      final socket = world.socket!;

      await world.controller.stopStreamDeviceRecording();
      await world.settle();

      expect(socket.closeCalls, 1);
      expectUserStopThenClose(socket);
    });

    test('a BLE disconnect closes the socket without a user_stop', () async {
      await connectPendant();
      final socket = world.socket!;

      world.controller.updateRecordingDevice(null);
      await world.settle();
      await world.controller.pendingSourceSwitch;

      expect(socket.closeCalls, 1);
      expect(userStops(), 0);
    });
  });

  group('best effort', () {
    test('a dead socket gets no frame and still closes', () async {
      final socket = ScriptedPureSocket();
      final service = TranscriptSegmentSocketService.withSocket(16000, BleAudioCodec.opus, 'en', socket);

      await service.stop(userStop: true);

      expect(socket.sentText, isEmpty);
      expect(socket.closeCalls, 1);
    });

    test('a failed send never blocks the close', () async {
      final socket = _TextRefusingSocket();
      final service = TranscriptSegmentSocketService.withSocket(16000, BleAudioCodec.opus, 'en', socket);
      await service.start();

      await service.stop(userStop: true);

      expect(socket.closeCalls, 1);
    });
  });
}

/// A transport whose sink closed underneath the app just as Stop was tapped.
class _TextRefusingSocket extends ScriptedPureSocket {
  @override
  void send(dynamic message) {
    if (message is String && message.contains('finalization_reason')) throw StateError('sink closed');
    super.send(message);
  }
}
