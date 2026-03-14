/// E2EE Middleware — encrypt/decrypt wrapper for API calls.

import 'package:omi/services/e2ee_service.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/logger.dart';

class E2eeMiddleware {
  static final E2eeService _service = E2eeService();

  static bool isE2eeEnabled() {
    return SharedPreferencesUtil().e2eeEnabled;
  }

  static Future<String> encryptIfEnabled(String data) async {
    if (!isE2eeEnabled() || data.isEmpty) return data;
    return _service.encrypt(data);
  }

  static Future<String> decryptIfEnabled(String data) async {
    if (!isE2eeEnabled() || data.isEmpty) return data;
    try {
      return await _service.decrypt(data);
    } catch (e) {
      Logger.error('[E2EE Middleware] Decryption error: $e');
      return '[Encrypted — unable to decrypt. Check your recovery key.]';
    }
  }
}
