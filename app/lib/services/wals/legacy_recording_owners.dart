import 'dart:convert';
import 'dart:io';
import 'package:omi/utils/off_ui_isolate.dart';
import 'native_custody_diagnostics.dart';

class LegacyRecordingOwners {
  LegacyRecordingOwners(this.stamps, this.corruptModified);
  final Map<String, String> stamps;
  final DateTime? corruptModified;
  static Future<LegacyRecordingOwners> read(Directory dir) async {
    final file = File('${dir.path}/omibatch_owners.json');
    if (!await file.exists()) return LegacyRecordingOwners({}, null);
    final modified = (await file.stat()).modified;
    try {
      final raw = await file.readAsString();
      final stamps = await offUiIsolate(() => Map<String, String>.from(jsonDecode(raw) as Map),
          size: raw.length, threshold: 16 * 1024);
      return LegacyRecordingOwners(stamps, null);
    } catch (_) {
      return LegacyRecordingOwners({}, modified);
    }
  }

  Future<String?> resolve(File file, String name, String uid, {required int timerStart}) async {
    if (corruptModified != null) {
      // Native timestamp is creation time; also require newer file metadata.
      final modified = (await file.stat()).modified;
      if (timerStart * 1000 <= corruptModified!.millisecondsSinceEpoch || !modified.isAfter(corruptModified!)) {
        nativeCustodyObserved(NativeCustodyObservedOutcome.legacyOwnersDeferred);
        return null;
      }
    }
    return stamps[name] ?? uid;
  }
}
