import 'dart:convert';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/home_feed.dart';
import 'package:omi/utils/off_ui_isolate.dart';

/// Policy-versioned, account-scoped display cache. Never stores source/detail payloads or cursors.
class HomeFeedCache {
  static String key(String owner) => 'homeFeedCards:v2:$owner';
  Future<List<HomeFeedCard>> read(String owner) async {
    final raw = SharedPreferencesUtil().getString(key(owner));
    if (raw.isEmpty) return const [];
    try {
      return await offUiIsolate(
          () => [for (final j in jsonDecode(raw) as List) HomeFeedCard.fromJson(Map<String, dynamic>.from(j))],
          size: raw.length,
          threshold: 16 * 1024,
          debugName: 'home-feed-cache-read');
    } on FormatException {
      return const [];
    } on TypeError {
      return const [];
    }
  }

  Future<void> write(String owner, List<HomeFeedCard> cards, bool Function() current) async {
    final snapshot = [for (final c in cards) c.withoutText().toJson()];
    final raw = await offUiIsolate(() => jsonEncode(snapshot),
        size: snapshot.length, threshold: 32, debugName: 'home-feed-cache-write');
    if (current()) await SharedPreferencesUtil().saveString(key(owner), raw);
  }
}
