/// E2EE Middleware — thin wrapper for encrypt/decrypt with E2EE-enabled check.
///
/// Use these static helpers around API calls so that sensitive fields
/// are transparently encrypted before sending and decrypted after receiving.
///
/// The middleware reads the current data protection level from the global
/// UserProvider. If the level is 'e2ee', data is encrypted/decrypted using
/// [E2eeService]; otherwise it passes through unchanged.

import 'package:omi/services/e2ee_service.dart';
import 'package:omi/backend/preferences.dart';

class E2eeMiddleware {
  static final E2eeService _service = E2eeService();

  /// Returns true if the user's data protection level is 'e2ee'.
  static bool isE2eeEnabled() {
    // We store the protection level in SharedPreferencesUtil for fast sync access.
    // This avoids needing a BuildContext / Provider lookup in static API helpers.
    return SharedPreferencesUtil().e2eeEnabled;
  }

  /// Encrypt [data] if E2EE is enabled; otherwise return as-is.
  static Future<String> encryptIfEnabled(String data) async {
    if (!isE2eeEnabled() || data.isEmpty) return data;
    return _service.encrypt(data);
  }

  /// Decrypt [data] if E2EE is enabled; otherwise return as-is.
  static Future<String> decryptIfEnabled(String data) async {
    if (!isE2eeEnabled() || data.isEmpty) return data;
    return _service.decrypt(data);
  }
}
