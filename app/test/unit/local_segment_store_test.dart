import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/utils/transcript_hash.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';

TranscriptSegment _seg(String id, String text, {String speaker = 'Alice'}) {
  return TranscriptSegment(
    id: id,
    text: text,
    speaker: speaker,
    isUser: false,
    personId: null,
    start: 0,
    end: 1,
    translations: const [],
  );
}

void main() {
  late Directory dir;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('s21-segments-');
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  tearDown(() async {
    if (await dir.exists()) {
      await dir.delete(recursive: true);
    }
  });

  test('disabled store writes nothing', () async {
    final store = LocalSegmentStore.disabled();
    await store.replaceSession('live-1', [_seg('a', 'hello')]);
    expect(await store.loadSession('live-1'), isEmpty);
    expect(dir.listSync(), isEmpty);
  });

  test('replace + new store instance reloads the exact hash payload', () async {
    const sessionId = 'live-1700000000';
    final first = LocalSegmentStore.at(dir);
    final segments = [_seg('a', 'I agree', speaker: 'Alice'), _seg('b', 'I refuse', speaker: 'Bob')];
    await first.replaceSession(sessionId, segments);

    final killed = LocalSegmentStore.at(dir);
    final loaded = await killed.loadSession(sessionId);
    expect(loaded, hasLength(2));
    expect(transcriptSha256(loaded), '6698e08ad93c92100b75e3ab279d15bfa3a70288b1693377841759a26e588d40');
    expect(await killed.loadDigest(sessionId), transcriptSha256(loaded));
  });

  test('reload preserves an explicit speaker_id that the label does not name', () async {
    const sessionId = 'live-7';
    final original = _seg('a', 'I approved the transfer', speaker: 'SPEAKER_00');
    original.speakerId = 7;
    await LocalSegmentStore.at(dir).replaceSession(sessionId, [original]);

    final loaded = await LocalSegmentStore.at(dir).loadSession(sessionId);
    expect(loaded.single.speakerId, 7);
    expect(transcriptSha256(loaded), 'd7dfcd646cda9e7d068693db981c82e11d144d376c800ba0640b611d3768ecdf');
  });

  test('release deletes the session file after projection acceptance', () async {
    const sessionId = 'live-done';
    final store = LocalSegmentStore.at(dir);
    await store.replaceSession(sessionId, [_seg('a', 'hello')]);
    expect(await store.loadSession(sessionId), isNotEmpty);
    await store.release(sessionId);
    expect(await store.loadSession(sessionId), isEmpty);
    expect(await store.loadDigest(sessionId), isNull);
  });

  test('CaptureProvider listener persists when a live session is active', () async {
    TestWidgetsFlutterBinding.ensureInitialized();
    final store = LocalSegmentStore.at(dir);
    final provider = CaptureProvider(localSegmentStore: store);
    addTearDown(provider.dispose);
    provider.testSessionStartSeconds = 1700000000;
    provider.segments = [_seg('a', 'I agree', speaker: 'Alice'), _seg('b', 'I refuse', speaker: 'Bob')];
    provider.notifyListeners();
    await pumpEventQueue();

    final loaded = await LocalSegmentStore.at(dir).loadSession('live-1700000000');
    expect(transcriptSha256(loaded), '6698e08ad93c92100b75e3ab279d15bfa3a70288b1693377841759a26e588d40');
  });
}
