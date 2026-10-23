import 'package:omi/backend/preferences.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Accounts deleted from this phone, newest last, bounded to [maxDeletedAccountUids].
/// The list survives sign-out and the preference wipe of a later deletion, so the WAL
/// index can purge the audio those accounts left on disk.
const String deletedAccountUidsKey = 'deletedAccountUids';
const int maxDeletedAccountUids = 20;

/// Read through the plugin's typed getter: after a cold start a list comes back from
/// disk untyped (`List<Object?>`), and `SharedPreferencesUtil.getStringList` would
/// quarantine it as a type mismatch instead of returning it.
Future<List<String>> readDeletedAccountUids() async {
  try {
    return (await SharedPreferences.getInstance()).getStringList(deletedAccountUidsKey) ?? const [];
  } catch (_) {
    return const [];
  }
}

/// Returns [previous] plus [uid] (deduplicated, newest last, bounded).
List<String> withDeletedAccountUid(List<String> previous, String uid) {
  final next = [...previous.where((u) => u != uid), uid];
  return next.length > maxDeletedAccountUids ? next.sublist(next.length - maxDeletedAccountUids) : next;
}

Future<bool> saveDeletedAccountUids(List<String> uids) =>
    SharedPreferencesUtil().saveStringList(deletedAccountUidsKey, uids);
