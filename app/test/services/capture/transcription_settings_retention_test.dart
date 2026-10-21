import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/services/wals/wal.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  test('changing transcription and network retains pendant session and durable audio', () async {
    final dir = await Directory.systemTemp.createTemp('stt_settings_retention_');
    final world = await CaptureReplayWorld.boot(tempDir: dir, pendantCodec: BleAudioCodec.opus);
    addTearDown(() async {
      await world.dispose();
      await dir.delete(recursive: true);
    });
    world.uploads.failAll = true;
    final connection = world.deviceConnection = ScriptedDeviceConnection();
    await world.controller.streamDeviceRecording(
      device: BtDevice(id: 'fixture-pendant', name: 'Omi', type: DeviceType.omi, rssi: -40),
    );
    await world.settle();
    final recording = world.controller.activeRecordingId;
    connection.emitAudio(value: 42);
    await world.wal.syncs.phone.finalizeCurrentSession();
    final durable = await world.wal.syncs.phone.getAllWals();
    expect(durable, isNotEmpty);
    final paths = await Future.wait(durable.map((wal) => Wal.getFilePath(wal.filePath)));
    final bytes = {for (final path in paths) path!: await File(path).readAsBytes()};

    // The same canonical event the settings page dispatches. No capture reset,
    // account sign-out or storage clear participates in changing STT.
    await SharedPreferencesUtil().saveCustomSttConfig(const CustomSttConfig(provider: SttProvider.omi));
    await world.controller.onTranscriptionSettingsChanged();
    world.setConnected(false);
    await world.settle();
    world.setConnected(true);
    await world.settle();
    expect(world.controller.activeRecordingId, recording);
    expect(connection.openAudioSubscriptions, 1);
    final socket = world.socket!;
    final sent = socket.sentBinary.length;
    connection.emitAudio(value: 43);
    expect(socket.sentBinary.length, sent + 1);
    final after = await world.wal.syncs.phone.getAllWals();
    expect(after.map((wal) => wal.id), containsAll(durable.map((wal) => wal.id)));
    for (final entry in bytes.entries) {
      expect(await File(entry.key).readAsBytes(), entry.value);
    }
  });
}
