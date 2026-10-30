import 'package:omi/backend/preferences.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Accounts deleted from this phone, newest last, bounded to [maxDeletedAccountUids].
/// The list survives sign-out and the preference wipe of a later deletion, so the WAL
/// index can purge the audio those accounts left on disk.
const String deletedAccountUidsKey = 'deletedAccountUids';
const int maxDeletedAccountUids = 20;

/// Read through the plugin's typed getter, which needs no `SharedPreferencesUtil.init` and
/// converts the list that comes back from disk untyped (`List<Object?>`) after a cold start.
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
