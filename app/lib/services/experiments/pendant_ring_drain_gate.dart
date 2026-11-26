import 'package:omi/backend/http/api/flags.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/services/auth_service.dart';

/// Default-on remote switch for independent pendant ring scheduling.
/// Mobile resolves registry flags through Omi's authenticated flag store.
abstract final class PendantRingDrainGate {
  static const enabledFlag = 'mobile-pendant-independent-ring-drain';

  static Future<bool> independentDrainAllowed({Future<bool?> Function(String)? readFlag}) async {
    try {
      return await (readFlag ?? _readFlag)(enabledFlag).timeout(const Duration(seconds: 2)) ?? true;
    } catch (_) {
      return true;
    }
  }

  static Future<bool?> _readFlag(String key) async {
    final auth = AuthService.instance;
    final session = auth.captureSessionSnapshot();
    if (session == null) return null;
    final result = await const OmiFlagsApi().getClientFlags();
    if (!auth.isSessionSnapshotCurrent(session)) return null;
    if (result case ApiSuccess(:final data)) {
      for (final flag in data) {
        if (flag.key == key && flag.variant == null) return flag.enabled;
      }
    }
    return null;
  }
}
