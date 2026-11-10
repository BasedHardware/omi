import 'dart:collection';
import 'dart:io';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/coordinators/provider_capture_external_actions.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Notify amplification guards.
///
/// The root MultiProvider (lib/main.dart) wires ChangeNotifierProxyProviders
/// whose update hooks run on every upstream notify. A hook that notifies
/// unconditionally turns one chat token, list refresh or transcript segment
/// into a rebuild of every downstream listener (Conversation/Message/People/
/// Usage -> Capture -> Device). Listeners that walk the whole transcript turn
/// each of those notifies into O(transcript) work on the UI isolate.
/// These tests fail on that shape.

int _countNotifies(Listenable notifier, void Function() body) {
  var count = 0;
  void listener() => count++;
  notifier.addListener(listener);
  try {
    body();
  } finally {
    notifier.removeListener(listener);
  }
  return count;
}

/// A transcript that counts how often something walks it.
class _CountingSegments extends ListBase<TranscriptSegment> {
  _CountingSegments(this._inner);

  final List<TranscriptSegment> _inner;
  @override
  int get length => _inner.length;

  @override
  set length(int value) => _inner.length = value;

  @override
  void add(TranscriptSegment element) => _inner.add(element);

  /// Element reads; a full walk of N segments reads N elements.
  int reads = 0;

  @override
  TranscriptSegment operator [](int index) {
    reads++;
    return _inner[index];
  }

  @override
  void operator []=(int index, TranscriptSegment value) => _inner[index] = value;

  @override
  Iterator<TranscriptSegment> get iterator {
    reads += _inner.length;
    return _inner.iterator;
  }
}

TranscriptSegment _seg(int i) => TranscriptSegment(
      id: 'seg-$i',
      text: 'Segment $i of a long live capture.',
      speaker: 'SPEAKER_00',
      isUser: false,
      personId: null,
      start: i.toDouble(),
      end: i + 1.0,
      translations: const [],
    );

class _OfflineConnectivity extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _OfflineConnectivity();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Already initialized by another test in this isolate.
    }
  });

  test('re-installing the same capture external actions does not notify', () {
    final conversations = ConversationProvider(isSignedIn: () => false);
    final messages = MessageProvider();
    final people = PeopleProvider(loadPeople: () async => null);
    final usage = UsageProvider();
    final capture = CaptureProvider();
    addTearDown(capture.dispose);
    ProviderCaptureExternalActions adapter() => ProviderCaptureExternalActions(
        conversationProvider: conversations, messageProvider: messages, peopleProvider: people, usageProvider: usage);

    expect(_countNotifies(capture, () => capture.updateExternalActions(adapter())), 1,
        reason: 'installing new backing providers is a real change');
    final repeats = _countNotifies(capture, () {
      for (var i = 0; i < 50; i++) {
        capture.updateExternalActions(adapter());
      }
    });
    expect(repeats, 0, reason: 'the proxy rebuilds the adapter on every upstream notify; that is not a capture change');
  });

  test('re-binding the same providers into DeviceProvider does not notify', () {
    final capture = CaptureProvider();
    final recordings = LocalRecordingsProvider(initialize: false);
    final device = DeviceProvider();
    addTearDown(capture.dispose);
    addTearDown(device.dispose);

    expect(_countNotifies(device, () => device.setProviders(capture, recordings)), 1);
    final repeats = _countNotifies(device, () {
      for (var i = 0; i < 50; i++) {
        device.setProviders(capture, recordings);
      }
    });
    expect(repeats, 0, reason: 'DeviceProvider re-binds on every CaptureProvider notify, i.e. per transcript segment');
  });

  test('capture notifies that leave the transcript alone do not walk it', () async {
    final dir = await Directory.systemTemp.createTemp('notify-amplification-');
    addTearDown(() => dir.delete(recursive: true));
    final capture = CaptureProvider(localSegmentStore: LocalSegmentStore.at(dir));
    addTearDown(capture.dispose);
    capture.testSessionStartSeconds = 1700000100;
    final transcript = _CountingSegments([for (var i = 0; i < 400; i++) _seg(i)]);
    capture.segments = transcript;
    capture.notifyListeners();
    await capture.pendingLiveSegmentWrite;
    final readsAfterFirstPersist = transcript.reads;

    for (var i = 0; i < 200; i++) {
      capture.notifyListeners();
    }
    await capture.pendingLiveSegmentWrite;

    expect(transcript.reads - readsAfterFirstPersist, 0,
        reason: 'state/metrics/socket notifies must not cost O(transcript) on the UI isolate');
  });

  test('a burst of transcript events costs one snapshot per write, not one walk per event', () async {
    final dir = await Directory.systemTemp.createTemp('notify-amplification-burst-');
    addTearDown(() => dir.delete(recursive: true));
    final capture = CaptureProvider(localSegmentStore: LocalSegmentStore.at(dir));
    addTearDown(capture.dispose);
    capture.testSessionStartSeconds = 1700000200;
    final transcript = _CountingSegments([for (var i = 0; i < 400; i++) _seg(i)]);
    capture.segments = transcript;

    // 50 new segments arrive faster than a write completes.
    for (var i = 400; i < 450; i++) {
      transcript.add(_seg(i));
      capture.notifyListeners();
    }
    await capture.pendingLiveSegmentWrite;

    expect(transcript.reads, lessThan(transcript.length * 3),
        reason: 'each segment event must not walk the whole transcript on the UI isolate');
    final saved = await LocalSegmentStore.at(dir).loadSession('live-1700000200');
    expect(saved.length, 450, reason: 'the coalesced write still lands the latest transcript');
  });
}
