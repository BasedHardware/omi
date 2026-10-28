import 'dart:convert';

import 'package:omi/backend/preferences.dart';

typedef PendingConversationMerge = ({List<String> ids, String? target});

/// A persistence adapter for IDs only, never transcripts or audio. Account and
/// API origin are explicit so a backend switch cannot adopt another journal.
class ConversationMergeJournal {
  ConversationMergeJournal(this.owner, this.origin);
  final String owner;
  final String origin;
  String get _key => 'pendingConversationMerges:$owner';

  static bool hasEntries(String owner) =>
      owner.isNotEmpty && SharedPreferencesUtil().getString('pendingConversationMerges:$owner').isNotEmpty;

  List<PendingConversationMerge> load() {
    final raw = SharedPreferencesUtil().getString(_key);
    if (raw.isEmpty) return [];
    final rows = (jsonDecode(raw) as Map)[origin] as List? ?? const [];
    return [for (final row in rows) (ids: (row['ids'] as List).cast<String>(), target: row['target'] as String?)];
  }

  Future<bool> save(Iterable<PendingConversationMerge> pending) {
    if (SharedPreferencesUtil().uid != owner) return Future.value(false);
    Map<String, dynamic> backends;
    try {
      backends =
          Map<String, dynamic>.from(jsonDecode(SharedPreferencesUtil().getString(_key, defaultValue: '{}')) as Map);
    } catch (_) {
      backends = {};
    }
    backends[origin] = [
      for (final row in pending) {'ids': row.ids, 'target': row.target}
    ];
    return SharedPreferencesUtil().saveString(_key, jsonEncode(backends));
  }
}
