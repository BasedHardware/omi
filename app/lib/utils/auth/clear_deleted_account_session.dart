import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

Future<void> clearDeletedAccountSession({
  required AuthService authService,
  required void Function() clearUserState,
  required Future<void> Function() clearWal,
  required Future<void> Function() clearPreferences,
}) async {
  clearUserState();
  await authService.expireSession(const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.accountDeleted));
  try {
    await clearWal();
  } catch (_) {
    // Preferences still contain the primary identity/auth material and must
    // be cleared even when local audio cleanup fails.
  } finally {
    try {
      await clearPreferences();
    } catch (_) {
      // Best-effort cleanup: do not turn a completed server deletion into a
      // misleading failure screen because local storage is already degraded.
    }
  }
}
