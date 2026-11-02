import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

Future<void> clearDeletedAccountSession({
  required AuthService authService,
  required void Function() clearUserState,
  required Future<void> Function() clearWal,
  required Future<void> Function() clearPreferences,
  Future<void> Function()? purgeAccountAudio,
  Future<void> Function()? rememberDeletedAccount,
}) async {
  // The deleted account's local recordings go first, while the WAL session
  // still belongs to that account: clearUserState retires them otherwise and
  // the next sign-in parks them as another account's audio forever.
  if (purgeAccountAudio != null) {
    try {
      await purgeAccountAudio();
    } catch (_) {
      // Best effort; the load-time purge keyed on rememberDeletedAccount
      // removes anything left behind.
    }
  }
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
    // After the wipe so the record survives it.
    if (rememberDeletedAccount != null) {
      try {
        await rememberDeletedAccount();
      } catch (_) {}
    }
  }
}
