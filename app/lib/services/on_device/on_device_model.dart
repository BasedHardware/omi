import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/preferences.dart';

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

  String? get engine => null;

  /// False until the first [refresh] reports which engine this phone will use.
  /// An unknown engine is loading, not Parakeet.
  bool get engineResolved => true;

  /// Detection finished without a usable engine. Never treat this as Parakeet.
  bool get detectionFailed => false;

  bool get isOsManaged => engine == 'speech_analyzer' || engine == 'sfspeech';

  /// Re-reads what is on disk.
  Future<void> refresh();

  Future<void> download({required bool wifiOnly});

  void cancel();

  Future<void> remove();

  /// Android uses the existing Whisper directory. Apple assets and Parakeet are
  /// selected by the native capability bridge, availability-gated from iOS 15.
  static OnDeviceModel forPlatform() => Platform.isIOS
      ? AppleOnDeviceModel()
      : Platform.isAndroid
          ? WhisperOnDeviceModel()
          : UnavailableOnDeviceModel();
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
  StreamSubscription<List<ConnectivityResult>>? _wifiSubscription;

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
    var wifiLost = false;
    if (wifiOnly) {
      _wifiSubscription = Connectivity().onConnectivityChanged.listen((networks) {
        if (!networks.contains(ConnectivityResult.wifi)) {
          wifiLost = true;
          cancel();
        }
      });
    }
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
      await _freemium.checkReadiness();
      _set(OnDeviceModelStatus(phase: OnDeviceModelPhase.installed, sizeBytes: received));
    } catch (e) {
      Logger.debug('[OnDeviceModel] download stopped: $e');
      final cancelled = e is http.ClientException && !identical(_client, client);
      _set(OnDeviceModelStatus(
          phase: wifiLost
              ? OnDeviceModelPhase.waitingForWifi
              : cancelled
                  ? OnDeviceModelPhase.notDownloaded
                  : OnDeviceModelPhase.failed));
    } finally {
      await _wifiSubscription?.cancel();
      _wifiSubscription = null;
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

/// Apple assets are OS-managed; Parakeet v2 is an explicit Wi-Fi-aware setup download.
class AppleOnDeviceModel extends OnDeviceModel {
  AppleOnDeviceModel({this.detectionTimeout = const Duration(seconds: 4)});

  /// Bounds a native status call that never returns. After this, the UI shows
  /// unavailable with retry instead of waiting forever or guessing Parakeet.
  final Duration detectionTimeout;

  static const channel = MethodChannel('com.omi/on_device');
  OnDeviceModelStatus _status = const OnDeviceModelStatus(phase: OnDeviceModelPhase.notDownloaded);
  String? _engine;
  bool _engineResolved = false;
  bool _detectionFailed = false;
  Timer? _poll;
  @override
  String? get engine => _engine;
  @override
  bool get engineResolved => _engineResolved;
  @override
  bool get detectionFailed => _detectionFailed;
  @override
  OnDeviceModelStatus get status => _status;
  Map<String, dynamic> get _args => {
        'language':
            SharedPreferencesUtil().userPrimaryLanguage.isEmpty ? 'en' : SharedPreferencesUtil().userPrimaryLanguage
      };
  void _markDetectionUnavailable() {
    _engine = null;
    _detectionFailed = true;
    _engineResolved = true;
    _status = const OnDeviceModelStatus(phase: OnDeviceModelPhase.unsupported);
  }

  void _applyStatus(Map<String, dynamic>? value) {
    final engine = value?['engine'] as String?;
    if (engine == null || engine.isEmpty) {
      _markDetectionUnavailable();
      return;
    }
    _engine = engine;
    _detectionFailed = false;
    _engineResolved = true;
    _status = OnDeviceModelStatus(
        phase: OnDeviceModelPhase.values
            .firstWhere((v) => v.name == value?['phase'], orElse: () => OnDeviceModelPhase.failed),
        progress: (value?['progress'] as num?)?.toDouble() ?? 0,
        sizeBytes: (value?['sizeBytes'] as num?)?.toInt() ?? 0);
  }

  @override
  Future<void> refresh() async {
    try {
      final value = await channel.invokeMapMethod<String, dynamic>('status', _args).timeout(detectionTimeout);
      _applyStatus(value);
    } on TimeoutException {
      _markDetectionUnavailable();
    } on PlatformException {
      _markDetectionUnavailable();
    } on MissingPluginException {
      _engine = null;
      _detectionFailed = false;
      _engineResolved = true;
      _status = const OnDeviceModelStatus(phase: OnDeviceModelPhase.unsupported);
    }
    notifyListeners();
  }

  @override
  Future<void> download({required bool wifiOnly}) async {
    if (_status.phase == OnDeviceModelPhase.downloading) return;
    if (wifiOnly && !isOsManaged && !(await Connectivity().checkConnectivity()).contains(ConnectivityResult.wifi)) {
      _status = OnDeviceModelStatus(phase: OnDeviceModelPhase.waitingForWifi, sizeBytes: _status.sizeBytes);
      notifyListeners();
      return;
    }
    _poll = Timer.periodic(const Duration(milliseconds: 500), (_) => unawaited(refresh()));
    try {
      await channel.invokeMethod<void>('download', {..._args, 'wifiOnly': wifiOnly && !isOsManaged});
    } on PlatformException {
      _status = const OnDeviceModelStatus(phase: OnDeviceModelPhase.failed);
    } finally {
      _poll?.cancel();
      _poll = null;
      await refresh();
    }
  }

  @override
  void cancel() => unawaited(channel.invokeMethod<void>('cancel'));
  @override
  Future<void> remove() async {
    await channel.invokeMethod<void>('remove', _args);
    await refresh();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }
}
