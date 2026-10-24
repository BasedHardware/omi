import 'dart:io';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/native_batch_geolocation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/native_recording_intake.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/batch_recording.dart';
import 'package:omi/services/wals/legacy_recording_owners.dart';

/// Overflow discovery belongs to on-device custody, including in its background
/// isolate. It no longer depends on Home's view or the retired owners writer.
Future<void> intakeOnDeviceOverflow(LocalWalSyncImpl ledger) async {
  final generation = ledger.sessionGeneration;
  final uid = SharedPreferencesUtil().uid;
  if (uid.isEmpty) return;
  final dir = await nativeRecordingDirectory();
  if (!await dir.exists()) return;
  final owners = await LegacyRecordingOwners.read(dir);
  await for (final entry in dir.list()) {
    if (entry is! File) continue;
    final name = entry.path.split('/').last;
    // This is a discovery prefix, not a separate marker/codec parser.
    if (!name.startsWith('audio_omibatchoverflow_') || !name.endsWith('.bin')) continue;
    final existing = ledger.nativeWalForFileName(name);
    if (existing != null) {
      if (!await ledger.nativeWalIsDurable(existing, generation)) await ledger.persistRetryMetadata(existing);
      continue;
    }
    final info = BatchRecordingInfo.fromFileName(name);
    if (info == null || !info.isOverflow) continue;
    final owner = await owners.resolve(entry, name, uid, timerStart: info.timerStart);
    if (owner == null) continue;
    final bytes = await entry.length();
    if (bytes == 0) continue;
    final frames = await countBatchRecordingFrames(entry.path);
    if (generation != ledger.sessionGeneration || uid != SharedPreferencesUtil().uid) return;
    if (!await ledger.ensureStorageAdmission(bytes: bytes, admittedGeneration: generation)) {
      throw StateError('Overflow custody admission deferred');
    }
    final wal = Wal(
        timerStart: info.timerStart,
        codec: info.codec,
        seconds: info.secondsFromFrameCount(frames),
        sampleRate: info.sampleRate,
        totalFrames: frames,
        storage: WalStorage.disk,
        status: WalStatus.miss,
        device: info.marker,
        filePath: name,
        ownerUid: owner,
        onDeviceOnly: true,
        capturedOnDeviceOnly: true,
        geolocation: await readNativeBatchGeolocation(entry.path))
      ..frameSize = info.frameSize;
    await ledger.addExternalWal(wal, admittedGeneration: generation);
    if (!await ledger.nativeWalIsDurable(wal, generation)) throw StateError('Overflow WAL index is not durable');
  }
}
