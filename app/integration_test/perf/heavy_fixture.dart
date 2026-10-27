/// Synthetic heavy-account fixture for the physical-device profile harness
/// (David 2026-10-25: ~6.5k pending WALs, ~2k conversations, long transcripts).
/// No real user data: deterministic generators, synthetic identities only.
///
/// Sizes are knobs so attribution runs can scale one axis:
///   --dart-define=PERF_SIM_CONVERSATIONS=2000 (1..5000)
///   --dart-define=PERF_SIM_WALS=6500 (0..20000)
///   --dart-define=PERF_SIM_WAL_FILES=6500 (files actually written to disk)
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider/path_provider.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_frame_encoder.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'heavy_storage_budget.dart';

int _knob(String name, String raw, int fallback, {required int min, required int max}) {
  if (raw.isEmpty) return fallback;
  final value = int.tryParse(raw);
  if (value == null || value < min || value > max) {
    throw ArgumentError('$name must be $min..$max, got "$raw"');
  }
  return value;
}

const _conversationsDefine = String.fromEnvironment('PERF_SIM_CONVERSATIONS');
const _walsDefine = String.fromEnvironment('PERF_SIM_WALS');
const _walFilesDefine = String.fromEnvironment('PERF_SIM_WAL_FILES');
const _detailSegmentsDefine = String.fromEnvironment('PERF_SIM_DETAIL_SEGMENTS');

final heavyConversationCount = _knob('PERF_SIM_CONVERSATIONS', _conversationsDefine, 2000, min: 1, max: 5000);
final heavyWalCount = _knob('PERF_SIM_WALS', _walsDefine, 6500, min: 0, max: 20000);
final heavyWalFileCount = _knob('PERF_SIM_WAL_FILES', _walFilesDefine, 6500, min: 0, max: 20000);
final heavyDetailSegments = _knob('PERF_SIM_DETAIL_SEGMENTS', _detailSegmentsDefine, 120, min: 1, max: 2000);

const heavyFixtureUid = 'omi-perf-heavy-fixture-uid';
const heavyFixtureEmail = 'perf-fixture@example.invalid';
final heavySeedDate = DateTime.utc(2026, 10, 20, 9);

/// Conversations spaced ~11 minutes apart over ~15 days, so Home's day-group
/// headers exercise grouping over many days. The newest conversation carries
/// the long transcript the detail scenario opens.
ServerConversation heavyConversation(int i) {
  final createdAt = heavySeedDate.subtract(Duration(minutes: 11 * i));
  final segmentCount = i == 0 ? heavyDetailSegments : 60;
  return ServerConversation(
    id: 'perf-heavy-conv-$i',
    createdAt: createdAt,
    structured: Structured(
      'Heavy fixture conversation $i',
      'Deterministic summary $i covering capacity planning, lane assignments and rollout order.',
      emoji: '🧠',
      category: 'other',
    )..actionItems = [for (var j = 0; j < 3; j++) ActionItem('Synthetic next step $j for conversation $i')],
    transcriptSegments: [
      for (var j = 0; j < segmentCount; j++)
        TranscriptSegment(
          id: 'perf-heavy-seg-$i-$j',
          text: 'Deterministic transcript line $j of conversation $i: we discussed the project, '
              'its next steps, capacity, and who owns each lane.',
          speaker: j % 5 == 0 ? 'SPEAKER_01' : 'SPEAKER_00',
          isUser: j % 5 != 0,
          personId: j % 5 == 0 ? 'perf-person-${i % 40}' : null,
          translations: [],
          start: j * 5.0,
          end: j * 5.0 + 4,
        )
    ],
  );
}

/// Seeds the fixture principal, gates, and the heavy conversations cache.
/// The conversations cache is the real cold-start decode path: Home restores
/// the list from SharedPreferences when the server page is empty.
Future<void> seedHeavyPreferences() async {
  FlutterSecureStorage.setMockInitialValues({});
  // Never reconcile a synthetic capture policy into the native dev app.
  SharedPreferencesUtil.capturePolicyBridgeForTesting = (method, arguments) async => 0;
  final conversations = [for (var i = 0; i < heavyConversationCount; i++) heavyConversation(i)];
  SharedPreferences.setMockInitialValues({
    'uid': heavyFixtureUid,
    'email': heavyFixtureEmail,
    'authToken': 'perf-fixture-bearer',
    'tokenExpirationTime': DateTime.now().add(const Duration(hours: 8)).millisecondsSinceEpoch,
    'onboardingCompleted': true,
    'aiConsentGiven': true,
    'permissionsCompleted': true,
    'migratedMemories': false,
    'showDiscardedMemories': false,
    'devLogsToFileEnabled': false,
    'cachedConversations': [for (final conversation in conversations) jsonEncode(conversation.toJson())],
    'cachedPeople': [
      for (var i = 0; i < 40; i++)
        jsonEncode(
            Person(id: 'perf-person-$i', name: 'Fixture person $i', createdAt: heavySeedDate, updatedAt: heavySeedDate)
                .toJson()),
    ],
  });
  await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);
}

/// Redirect every Dart documents/support/temp lookup before touching a WAL.
/// A unique run directory keeps even an installed development app's audio safe.
Future<Directory> isolateHeavyStorage() async {
  final root = await getTemporaryDirectory();
  final directory = await HeavyStorageBudget(Directory('${root.path}/omi-heavy-perf-fixtures-v1')).reserve();
  PathProviderPlatform.instance = _HeavyPaths(directory.path);
  return directory;
}

class _HeavyPaths extends PathProviderPlatform {
  _HeavyPaths(this.path);
  final String path;
  @override
  Future<String?> getApplicationDocumentsPath() async => path;
  @override
  Future<String?> getApplicationSupportPath() async => path;
  @override
  Future<String?> getTemporaryPath() async => path;
}

/// Rewrites the WAL index (+ a bounded number of real audio files) so the
/// production WAL service loads ~6.5k pending records and keeps its admission
/// cap engaged — David's heavy-account shape. The index is the real cold-start
/// WAL decode; the files give sync real bytes to chew on.
Future<int> seedHeavyWals() async {
  await WalFileManager.init();
  final documents = await getApplicationDocumentsDirectory();
  // isolateHeavyStorage gives each process a fresh, fixture-only directory.
  final wals = <Wal>[];
  final files = <String, Uint8List>{};
  final payload = _syntheticOpusPayload();
  for (var i = 0; i < heavyWalCount; i++) {
    final timerStart = heavySeedDate.subtract(Duration(minutes: 20 * i)).millisecondsSinceEpoch ~/ 1000;
    final fileName = 'audio_omiperf_${timerStart}_$i.bin';
    Wal? wal;
    if (i < heavyWalFileCount) {
      wal = Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        seconds: 5,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'phone',
        deviceModel: 'Perf fixture',
        ownerUid: heavyFixtureUid,
        filePath: fileName,
        totalFrames: 5 * 100,
      );
      files[fileName] = payload;
    } else {
      // Records without local audio still count toward admission pressure and
      // every list scan; real backlogged phones carry many of both shapes.
      wal = Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        seconds: 5,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'phone',
        deviceModel: 'Perf fixture',
        ownerUid: heavyFixtureUid,
      );
    }
    wals.add(wal);
  }
  for (final entry in files.entries) {
    await File('${documents.path}/${entry.key}').writeAsBytes(entry.value);
  }
  final indexSaved = await WalFileManager.saveWals(wals);
  if (!indexSaved) {
    throw StateError('heavy fixture: WAL index save failed');
  }
  final loaded = await WalFileManager.loadWals();
  if (loaded.length != heavyWalCount) {
    throw StateError('heavy fixture: expected $heavyWalCount WALs, loaded ${loaded.length}');
  }
  return files.length;
}

Uint8List _syntheticOpusPayload() {
  // Valid length-prefixed Opus silence packets, not arbitrary bytes whose
  // first four bytes could advertise gigabytes of payload to a frame reader.
  return encodeWalFrames(List<List<int>>.generate(500, (_) => const [0xf8, 0xff, 0xfe]));
}
