import 'package:flutter/material.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/deleted_account_uids.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/auth/clear_deleted_account_session.dart';
import 'package:omi/utils/auth/clear_user_state.dart';
import 'package:omi/utils/wal_file_manager.dart';

/// Shared with the normal deletion flow: erase local audio only after the server accepts deletion.
Future<void> clearFinishedDeletion(BuildContext context) async {
  final uid = SharedPreferencesUtil().uid;
  final deleted = await readDeletedAccountUids();
  if (!context.mounted) return;
  await clearDeletedAccountSession(
    authService: AuthService.instance,
    purgeAccountAudio: () async {
      final phone = ServiceManager.instance().wal.getSyncs().phone as LocalWalSync;
      await phone.purgeAccountWals(uid);
    },
    clearUserState: () => clearAllUserState(context),
    clearWal: WalFileManager.clearAll,
    clearPreferences: SharedPreferencesUtil().clear,
    rememberDeletedAccount: uid.isEmpty ? null : () => saveDeletedAccountUids(withDeletedAccountUid(deleted, uid)),
  );
}
