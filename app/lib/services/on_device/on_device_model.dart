import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/services/on_device/on_device_tuning.dart';
import 'package:omi/utils/logger.dart';

enum OnDeviceModelPhase {
  /// This phone cannot run the speech model (or the app does not ship one for it yet).
  unsupported,
  notDownloaded,

  /// The reader chose Wi-Fi only and the phone is not on Wi-Fi.
  waitingForWifi,
  downloading,
  installed,
  failed,
}

@immutable
class OnDeviceModelStatus {
  const OnDeviceModelStatus({
    required this.phase,
    this.progress = 0,
    this.sizeBytes = OnDeviceTuning.modelSizeBytes,
    this.timeLeft,
  });

  final OnDeviceModelPhase phase;

  /// 0–1 while [OnDeviceModelPhase.downloading].
  final double progress;

  /// Download size, or the installed file's size.
  final int sizeBytes;

  /// Estimated remaining download time, when the rate is known.
  final Duration? timeLeft;

  bool get isInstalled => phase == OnDeviceModelPhase.installed;
  bool get isSupported => phase != OnDeviceModelPhase.unsupported;

  @override
  bool operator ==(Object other) =>
      other is OnDeviceModelStatus &&
      other.phase == phase &&
      other.progress == progress &&
      other.sizeBytes == sizeBytes &&
      other.timeLeft == timeLeft;

  @override
  int get hashCode => Object.hash(phase, progress, sizeBytes, timeLeft);
}

/// The speech model on-device transcription runs on: whether it is here, and getting or removing
/// it. UI reads [status] and listens; it never touches files.
abstract class OnDeviceModel extends ChangeNotifier {
  OnDeviceModelStatus get status;

  /// Re-reads what is on disk.
  Future<void> refresh();

  Future<void> download({required bool wifiOnly});

  void cancel();

  Future<void> remove();

  /// Android runs the Whisper model the app already downloads for on-device STT. iOS has no
  /// on-device batch model in the app yet (Parakeet is pending), so it reports unsupported.
  static OnDeviceModel forPlatform() => Platform.isAndroid ? WhisperOnDeviceModel() : UnavailableOnDeviceModel();
}

/// A model this phone does not have and cannot get yet.
class UnavailableOnDeviceModel extends OnDeviceModel {
  @override
  OnDeviceModelStatus get status => const OnDeviceModelStatus(phase: OnDeviceModelPhase.unsupported);

  @override
  Future<void> refresh() async {}

  @override
  Future<void> download({required bool wifiOnly}) async {}

  @override
  void cancel() {}

  @override
  Future<void> remove() async {}
}

/// The Android Whisper model, in the directory [FreemiumTranscriptionService] already reads
/// (`<app support>/models/ggml-<name>.bin`), from the same source the Transcription settings page
/// downloads it from.
class WhisperOnDeviceModel extends OnDeviceModel {
  WhisperOnDeviceModel({
    FreemiumTranscriptionService? freemium,
    Future<List<ConnectivityResult>> Function()? checkConnectivity,
  })  : _freemium = freemium ?? FreemiumTranscriptionService(),
        _checkConnectivity = checkConnectivity ?? Connectivity().checkConnectivity;

  static const modelName = OnDeviceTuning.androidWhisperModel;

  final FreemiumTranscriptionService _freemium;
  final Future<List<ConnectivityResult>> Function() _checkConnectivity;
  OnDeviceModelStatus _status = const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded);
  http.Client? _client;

  @override
  OnDeviceModelStatus get status => _status;

  void _set(OnDeviceModelStatus status) {
    if (status == _status) return;
    _status = status;
    notifyListeners();
  }

  @override
  Future<void> refresh() async {
    if (_status.phase == OnDeviceModelPhase.downloading) return;
    final readiness = await _freemium.checkReadiness();
    final path = _freemium.cachedModelPath;
    if (readiness == FreemiumReadiness.ready && path != null) {
      final file = File(path);
      _set(OnDeviceModelStatus(
        phase: OnDeviceModelPhase.installed,
        sizeBytes: await file.exists() ? await file.length() : OnDeviceTuning.modelSizeBytes,
      ));
    } else {
      _set(const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded));
    }
  }

  @override
  Future<void> download({required bool wifiOnly}) async {
    if (_status.phase == OnDeviceModelPhase.downloading) return;
    if (wifiOnly && !(await _checkConnectivity()).contains(ConnectivityResult.wifi)) {
      _set(const OnDeviceModelStatus(phase: OnDeviceModelPhase.waitingForWifi));
      return;
    }
    _set(const OnDeviceModelStatus(phase: OnDeviceModelPhase.downloading));
    final client = _client = http.Client();
    IOSink? sink;
    File? partial;
    try {
      final dir = Directory('${(await getApplicationSupportDirectory()).path}/models');
      if (!await dir.exists()) await dir.create(recursive: true);
      const fileName = 'ggml-$modelName.bin';
      final url = Uri.parse('https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$fileName');
      final response = await client.send(http.Request('GET', url));
      if (response.statusCode != 200) throw HttpException('Model download failed: ${response.statusCode}');
      final total = response.contentLength ?? OnDeviceTuning.modelSizeBytes;
      partial = File('${dir.path}/$fileName.part');
      sink = partial.openWrite();
      final started = DateTime.now();
      var received = 0;
      await response.stream.listen((chunk) {
        sink!.add(chunk);
        received += chunk.length;
        final elapsed = DateTime.now().difference(started);
        final rate = elapsed.inMilliseconds > 0 ? received / elapsed.inMilliseconds : 0;
        _set(OnDeviceModelStatus(
          phase: OnDeviceModelPhase.downloading,
          progress: (received / total).clamp(0.0, 1.0),
          sizeBytes: total,
          timeLeft: rate > 0 ? Duration(milliseconds: ((total - received) / rate).round()) : null,
        ));
      }, cancelOnError: true).asFuture<void>();
      await sink.close();
      sink = null;
      await partial.rename('${dir.path}/$fileName');
      partial = null;
      await refresh();
    } catch (e) {
      Logger.debug('[OnDeviceModel] download stopped: $e');
      final cancelled = e is http.ClientException && !identical(_client, client);
      _set(OnDeviceModelStatus(phase: cancelled ? OnDeviceModelPhase.notDownloaded : OnDeviceModelPhase.failed));
    } finally {
      await sink?.close();
      if (partial != null && await partial.exists()) await partial.delete();
      client.close();
      if (identical(_client, client)) _client = null;
    }
  }

  @override
  void cancel() {
    final client = _client;
    _client = null;
    client?.close();
  }

  @override
  Future<void> remove() async {
    cancel();
    final path = _freemium.cachedModelPath;
    if (path != null) {
      final file = File(path);
      if (await file.exists()) await file.delete();
    }
    _set(const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded));
  }
}
