import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/pigeon_communicator.g.dart' show BleDisconnectEvent;
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/wals/wal_service.dart';

/// Final segments already transcribed in the heavy live session (8 s each, ~2h13m).
const heavyLiveFinalSegments = 1000;

/// Preview words arrive several times a second, as the on-device recognizer revises them.
const heavyLivePreviewInterval = Duration(milliseconds: 200);

const heavyLiveConversationId = 'perf-heavy-live-conv';

/// Scripted on-device preview engine (minimal copy of test/support/live_preview_fakes.dart, which
/// the device harness cannot import): no platform channel, no audio.
class HeavyLivePreviewEngine implements LivePreviewEngine {
  final StreamController<LivePreviewResult> _results = StreamController.broadcast(sync: true);

  @override
  Stream<LivePreviewResult> get results => _results.stream;

  void emit(String id, String text, bool isFinal, {required DateTime startedAt, required DateTime endedAt}) => _results
      .add(LivePreviewResult(segmentId: id, text: text, isFinal: isFinal, startedAt: startedAt, endedAt: endedAt));

  @override
  Future<LivePreviewStart> start(String language, {Set<LivePreviewEngineKind> exclude = const {}}) async =>
      const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok);

  @override
  Future<bool> feedPcm16(Uint8List pcm, {DateTime? startedAt}) async => true;

  @override
  Future<void> stop() async {}
}

/// A pendant capture with an admitted on-device preview, over the harness's real WAL service.
/// Server admission needs a listen socket the fixture does not run, so only the admission flag
/// is asserted here; the preview controller itself is installed through
/// [CaptureController.installLivePreview] and admitted through its own [LivePreviewController.admit].
class HeavyLiveCapture extends CaptureProvider {
  HeavyLiveCapture({required WalService walService, required this.origin})
      : super(
          walService: walService,
          connectivity: CaptureConnectivityBoundary(
              initiallyConnected: true, changes: const Stream.empty(), isConnected: () => true),
          bleListeners: _NoBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  /// Server conversation start: final segment offsets are relative to it.
  final DateTime origin;

  @override
  String? get liveCaptureSource => 'omi';

  @override
  String? get topConversationId => heavyLiveConversationId;

  @override
  DateTime? get liveTranscriptStartedAt => origin;

  @override
  DateTime? get liveCaptureStartedAt => origin;

  @override
  bool get localPreviewAdmitted => true;
}

class _NoBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}

  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

TranscriptSegment heavyLiveSegment(int i) => TranscriptSegment(
      id: 'perf-live-seg-$i',
      text: 'Live line $i of the long planning session: capacity, lanes, migration order and owners.',
      speaker: i % 5 == 0 ? 'SPEAKER_01' : 'SPEAKER_00',
      isUser: i % 5 != 0,
      personId: null,
      translations: [],
      start: i * 8.0,
      end: i * 8.0 + 7,
    );

/// The live session the three live windows share: ~1,000 final segments through the production
/// segment seam, an admitted preview whose 200-line window mostly overlaps the finals (as on a
/// real long session) and a driver that revises the newest line every [heavyLivePreviewInterval].
class HeavyLiveSession {
  HeavyLiveSession._(this.capture, this.preview, this.engine, this.episodes);

  final HeavyLiveCapture capture;
  final LivePreviewController preview;
  final HeavyLivePreviewEngine engine;
  final EpisodeProvider episodes;
  Timer? _driver;
  int _nextFinal = heavyLiveFinalSegments;
  int _line = 0;
  int _tick = 0;

  static Future<HeavyLiveSession> start(WalService walService) async {
    final now = DateTime.now();
    final origin = now.subtract(const Duration(seconds: heavyLiveFinalSegments * 8 + 20));
    final capture = HeavyLiveCapture(walService: walService, origin: origin);
    for (var batch = 0; batch * 10 < heavyLiveFinalSegments; batch++) {
      capture.onSegmentReceived([
        for (var j = batch * 10; j < (batch + 1) * 10 && j < heavyLiveFinalSegments; j++) heavyLiveSegment(j),
      ]);
      await Future<void>.delayed(Duration.zero);
    }
    final engine = HeavyLivePreviewEngine();
    final preview = LivePreviewController(
      engine: engine,
      telemetry: LivePreviewTelemetry(emit: (_) {}),
      platform: LivePreviewPlatform.ios,
      osMajor: 27,
      requestAllowed: () async => true,
      // Never a conversation boundary inside the measured windows.
      conversationGap: () => const Duration(hours: 1),
    );
    capture.installLivePreview(preview);
    preview.admit(language: 'en');
    final episode = Episode(
      id: 'perf-heavy-live-episode',
      live: true,
      startedAt: origin,
      lastActivityAt: now,
      stateUpdatedAt: now,
      title: 'Long planning session',
      bullets: const ['Capacity review', 'Lane assignments', 'Migration order'],
      conversationIds: const [heavyLiveConversationId],
    );
    final episodes = EpisodeProvider(
      fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: episode)),
      lookup: (_) async => ApiSuccess(EpisodeRead(enabled: true, episode: episode)),
    );
    await episodes.refreshLive();
    final session = HeavyLiveSession._(capture, preview, engine, episodes);
    await session._seedPreviewLines(origin);
    return session;
  }

  /// 200 earlier preview lines (the controller's cap): all but the newest few are already covered
  /// by finals, so coverage walks the full span list for each of them.
  Future<void> _seedPreviewLines(DateTime origin) async {
    while (preview.phase != LivePreviewPhase.streaming) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
    }
    for (var i = 0; i < preview.maxLines - 4; i++) {
      final segment = heavyLiveFinalSegments - (preview.maxLines - 4) + i;
      final start = origin.add(Duration(seconds: segment * 8));
      engine.emit('perf-preview-$segment', 'Preview words for line $segment of the long session.', true,
          startedAt: start, endedAt: start.add(const Duration(seconds: 7)));
    }
    _line = heavyLiveFinalSegments;
  }

  /// Revises the newest preview line several times a second; every 40 revisions (8 s) it becomes
  /// final, a new line starts, and the server's final transcript catches up by one segment.
  void startUpdates() {
    _driver ??= Timer.periodic(heavyLivePreviewInterval, (_) {
      final origin = capture.origin;
      final start = origin.add(Duration(seconds: _line * 8));
      final words = 1 + _tick % 40;
      final isFinal = words == 40;
      engine.emit('perf-preview-$_line', List.filled(words, 'word').join(' '), isFinal,
          startedAt: start, endedAt: start.add(Duration(milliseconds: words * 175)));
      _tick++;
      if (isFinal) {
        _line++;
        capture.onSegmentReceived([heavyLiveSegment(_nextFinal++)]);
      }
    });
  }

  void stopUpdates() {
    _driver?.cancel();
    _driver = null;
  }

  int get updates => _tick;

  void dispose() {
    stopUpdates();
    episodes.dispose();
    capture.dispose();
  }
}

/// A connected pendant for Device Settings. The production provider subscribes to the BLE
/// service manager in its constructor, which this harness never initializes; this fake answers
/// only what the page reads, and anything else throws so a new read cannot pass silently.
class HeavyConnectedDevice extends ChangeNotifier implements DeviceProvider {
  @override
  BtDevice? connectedDevice = BtDevice(id: 'AA:AA:AA:AA:AA:01', name: 'Omi', type: DeviceType.omi, rssi: -40);
  @override
  BtDevice? pairedDevice;
  @override
  bool isConnected = true;
  @override
  bool isConnecting = false;
  @override
  bool isCharging = false;
  @override
  int batteryLevel = 80;
  @override
  bool isDeviceStorageSupport = false;
  @override
  bool supportsMultiFileSync = false;
  @override
  bool get havingNewFirmware => false;
  @override
  String get latestStableFirmwareVersion => '';
  @override
  Map<String, dynamic> get latestOmiGlassFirmwareDetails => const {};
  @override
  Future<void> getDeviceInfo() async {}
  @override
  Future<List<BleDisconnectEvent>> disconnectHistory() async => const [];
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
