// ignore_for_file: experimental_member_use

import 'package:audio_session/audio_session.dart';
import 'package:flutter/foundation.dart';

enum VoiceOutputRouteKind { headphones, speaker, unknown }

@immutable
class VoiceOutputRoute {
  const VoiceOutputRoute._(this.kind, this.name);

  const VoiceOutputRoute.headphones(String name) : this._(VoiceOutputRouteKind.headphones, name);
  const VoiceOutputRoute.speaker() : this._(VoiceOutputRouteKind.speaker, null);
  const VoiceOutputRoute.unknown() : this._(VoiceOutputRouteKind.unknown, null);

  final VoiceOutputRouteKind kind;
  final String? name;
}

abstract interface class VoiceOutputRouteSource {
  Stream<VoiceOutputRoute> watch();
}

class AudioSessionVoiceOutputRouteSource implements VoiceOutputRouteSource {
  static const _privateOutputTypes = <AudioDeviceType>{
    AudioDeviceType.bluetoothA2dp,
    AudioDeviceType.bluetoothLe,
    AudioDeviceType.bluetoothSco,
    AudioDeviceType.wiredHeadphones,
    AudioDeviceType.wiredHeadset,
    AudioDeviceType.usbAudio,
    AudioDeviceType.airPlay,
    AudioDeviceType.lineAnalog,
    AudioDeviceType.lineDigital,
  };

  @override
  Stream<VoiceOutputRoute> watch() async* {
    try {
      final session = await AudioSession.instance;
      yield await _readRoute(session);
      await for (final _ in session.devicesChangedEventStream) {
        yield await _readRoute(session);
      }
    } catch (_) {
      yield const VoiceOutputRoute.unknown();
    }
  }

  Future<VoiceOutputRoute> _readRoute(AudioSession session) async {
    try {
      final outputs = await session.getDevices(includeInputs: false);
      final privateOutput = outputs.cast<AudioDevice?>().firstWhere(
            (device) => device != null && device.isOutput && _privateOutputTypes.contains(device.type),
            orElse: () => null,
          );
      if (privateOutput == null) return const VoiceOutputRoute.speaker();
      final name = privateOutput.name.trim();
      return VoiceOutputRoute.headphones(name);
    } catch (_) {
      return const VoiceOutputRoute.unknown();
    }
  }
}
