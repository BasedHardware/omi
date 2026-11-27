import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/live_preview/live_words_coordinator.dart';
import 'package:omi/services/live_preview/vendor_live_words.dart';
import 'package:omi/utils/enums.dart';

import '../../support/live_preview_fakes.dart';
import 'vendor_live_words_test.dart' show FakeSocket, pendantPacket;

// Reliability experiment vendor_recognizer_on_opened_app: when the live-words layer runs. Capture
// active and the app exactly in front: the phone's recogniser runs without the grant and the vendor
// stream is open. Background, pause or stop: the stream closes.

class FakeCapture extends ChangeNotifier implements LiveWordsCapture {
  @override
  RecordingState recordingState = RecordingState.stop;
  @override
  bool isPaused = false;
  int seals = 0;
  final List<bool> shown = [];

  @override
  void sealOpenPhoneFile() => seals++;
  @override
  void showLiveWordsInFront(bool value) {
    if (shown.isEmpty || shown.last != value) shown.add(value);
  }

  void set({RecordingState? state, bool? paused}) {
    recordingState = state ?? recordingState;
    isPaused = paused ?? isPaused;
    notifyListeners();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FakeCapture capture;
  late FakeLivePreviewEngine engine;
  late LivePreviewController preview;
  late VendorLiveWords vendor;
  late List<FakeSocket> sockets;
  late List<(String, Map<String, Object?>)> logged;
  late LiveWordsCoordinator coordinator;
  var enabled = true;
  AppLifecycleState? lifecycle = AppLifecycleState.resumed;
  var clock = DateTime.utc(2026, 11, 25, 12);

  void speak(int frames) {
    for (var i = 0; i < frames; i++) {
      clock = clock.add(const Duration(milliseconds: 20));
      vendor.onPendantPacket(pendantPacket(i % 256), BleAudioCodec.opusFS320);
    }
  }

  void build() {
    coordinator = LiveWordsCoordinator(
      capture: capture,
      preview: preview,
      vendor: vendor,
      enabled: () => enabled,
      language: () => 'en',
      lifecycleState: () => lifecycle,
      log: (event, fields) => logged.add((event, fields)),
    )..start();
  }

  setUp(() {
    enabled = true;
    lifecycle = AppLifecycleState.resumed;
    clock = DateTime.utc(2026, 11, 25, 12);
    capture = FakeCapture();
    engine = FakeLivePreviewEngine();
    sockets = [];
    logged = [];
    preview = LivePreviewController(
      engine: engine,
      telemetry: LivePreviewTelemetry(emit: (_) {}),
      platform: LivePreviewPlatform.ios,
      osMajor: 26,
      now: () => clock,
      ownResultsMuted: () => false,
    );
    vendor = VendorLiveWords(
      onLines: preview.onVendorLines,
      connect: (url) {
        final socket = FakeSocket(url);
        sockets.add(socket);
        return socket;
      },
      now: () => clock,
      baseUrl: () => 'ws://server/',
      uid: () => 'owner',
    );
  });
  tearDown(() {
    coordinator.dispose();
    preview.dispose();
  });

  test('off: capture in front starts nothing, connects nothing, seals nothing', () async {
    enabled = false;
    build();
    capture.set(state: RecordingState.deviceRecord);
    speak(50);
    coordinator.onLifecycle(AppLifecycleState.paused);
    coordinator.onLifecycle(AppLifecycleState.resumed);
    speak(50);
    await pumpEventQueue();
    expect(preview.phase, LivePreviewPhase.inactive);
    expect(preview.frontAdmitted, isFalse);
    expect(engine.startedLanguages, isEmpty);
    expect(sockets, isEmpty);
    expect(vendor.ringFramesForTesting, 0);
    expect(capture.seals, 0);
    expect(capture.shown, [false]);
    expect(logged, isEmpty);
  });

  test('capture active in front: the phone\'s recogniser starts without a grant and the stream opens', () async {
    build();
    expect(preview.phase, LivePreviewPhase.inactive); // Nothing is capturing yet.
    capture.set(state: RecordingState.deviceRecord);
    await pumpEventQueue();
    expect(engine.startedLanguages, ['en']);
    expect(preview.phase, LivePreviewPhase.streaming);
    expect(capture.shown, [false, true]); // The screens were told live words can show.
    speak(5);
    await pumpEventQueue();
    expect(sockets.single.sent, hasLength(5));
    expect(logged.first.$1, 'active');
    expect(logged.first.$2['active'], true);
  });

  test('the app leaving the front closes the stream and stops an ungranted recogniser', () async {
    build();
    capture.set(state: RecordingState.deviceRecord);
    speak(5);
    await pumpEventQueue();
    coordinator.onLifecycle(AppLifecycleState.inactive); // The notification shade is not "in front".
    await pumpEventQueue();
    expect(sockets.single.stops, 1);
    expect(preview.phase, LivePreviewPhase.inactive);
    expect(engine.stops, 1);
    expect(capture.shown, [false, true, false]);
    speak(50); // Audio keeps coming in the background: lead-in only.
    expect(sockets, hasLength(1));
    expect(logged.map((entry) => entry.$1), containsAllInOrder(['active', 'active', 'counters']));
  });

  test('coming back to the front seals the open phone file, restarts the recogniser and redials', () async {
    build();
    capture.set(state: RecordingState.deviceRecord);
    speak(5);
    await pumpEventQueue();
    coordinator.onLifecycle(AppLifecycleState.paused);
    speak(200);
    coordinator.onLifecycle(AppLifecycleState.resumed);
    expect(capture.seals, 1);
    await pumpEventQueue();
    expect(preview.phase, LivePreviewPhase.streaming);
    speak(1);
    await pumpEventQueue();
    expect(sockets, hasLength(2));
    // The last 3 s captured in the background go first.
    expect(sockets[1].sent, hasLength(150));
  });

  test('a granted session keeps its recogniser in the background; only the stream closes', () async {
    build();
    preview.admit(language: 'en');
    capture.set(state: RecordingState.deviceRecord);
    speak(5);
    await pumpEventQueue();
    coordinator.onLifecycle(AppLifecycleState.paused);
    await pumpEventQueue();
    expect(sockets.single.stops, 1);
    expect(preview.phase, LivePreviewPhase.streaming);
    expect(engine.stops, 0);
  });

  test('pause and stop close the stream each time; resume opens it again', () async {
    build();
    capture.set(state: RecordingState.deviceRecord);
    speak(5);
    await pumpEventQueue();
    capture.set(state: RecordingState.pause, paused: true);
    expect(sockets[0].stops, 1);
    expect(vendor.ringFramesForTesting, 0);
    speak(50); // A paused pendant sends nothing, and anything that did arrive is not kept.
    expect(sockets, hasLength(1));
    capture.set(state: RecordingState.deviceRecord, paused: false);
    speak(5);
    await pumpEventQueue();
    expect(sockets, hasLength(2));
    capture.set(state: RecordingState.stop);
    expect(sockets[1].stops, 1);
    await pumpEventQueue();
    expect(preview.phase, LivePreviewPhase.inactive);
    expect(capture.seals, 0); // Only coming to the front seals.
  });

  test('a start in the background is not "in front" until the app is resumed', () async {
    lifecycle = null; // What iOS reports for a launch in the background.
    build();
    capture.set(state: RecordingState.deviceRecord);
    speak(50);
    await pumpEventQueue();
    expect(coordinator.inFront, isFalse);
    expect(sockets, isEmpty);
    expect(preview.phase, LivePreviewPhase.inactive);
    coordinator.onLifecycle(AppLifecycleState.resumed);
    speak(1);
    await pumpEventQueue();
    expect(sockets, hasLength(1));
    expect(preview.phase, LivePreviewPhase.streaming);
  });

  test('phone-microphone capture counts as active too', () async {
    build();
    capture.set(state: RecordingState.record);
    await pumpEventQueue();
    expect(preview.phase, LivePreviewPhase.streaming);
    clock = clock.add(const Duration(milliseconds: 20));
    vendor.onPhonePcm(List.filled(640, 1));
    await pumpEventQueue();
    expect(sockets.single.url, contains('codec=pcm16'));
  });

  test('vendor lines reach every screen through the one merged list', () async {
    build();
    capture.set(state: RecordingState.deviceRecord);
    final start = clock;
    speak(250);
    await pumpEventQueue();
    sockets.single.serverSays({
      'type': 'lines',
      'lines': [
        {
          'id': 'a',
          'start': 1.0,
          'end': 2.0,
          'text': 'only the vendor heard this',
          'words': [
            ['only', 1.0, 1.2],
            ['the', 1.2, 1.3],
            ['vendor', 1.3, 1.6],
            ['heard', 1.6, 1.8],
            ['this', 1.8, 2.0],
          ],
        }
      ],
    });
    expect(preview.lines.single.text, 'only the vendor heard this');
    expect(preview.lines.single.startedAt, start.add(const Duration(seconds: 1)));
    expect(preview.latestLine, 'only the vendor heard this');
  });
}
