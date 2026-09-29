import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as action_wire;
import 'package:omi/backend/schema/gen/search_wire.g.dart' as search_wire;
import 'package:omi/backend/schema/gen/users_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// One folder tile in the search overlay.
class SearchFolderCount {
  const SearchFolderCount({required this.id, required this.name, required this.icon, required this.color, this.count});

  final String id;
  final String name;
  final String icon;
  final String color;

  /// Null when the server could not count it; the tile then shows no number.
  final int? count;
}

/// What the search overlay shows before anything is typed: how many of each thing there are.
/// Every count is decoration: null (an older backend without the route) never hides a tile.
class SearchOverview {
  const SearchOverview({
    this.starred,
    this.folders = const [],
    this.recaps,
    this.memories,
    this.people,
    this.places,
  });

  final int? starred;
  final List<SearchFolderCount> folders;
  final int? recaps;
  final int? memories;
  final int? people;
  final int? places;

  factory SearchOverview.fromGenerated(search_wire.GeneratedSearchOverviewResponse generated) {
    return SearchOverview(
      starred: generated.starred,
      recaps: generated.recaps,
      memories: generated.memories,
      people: generated.people,
      places: generated.places,
      folders: [
        for (final f in generated.folders ?? const <search_wire.GeneratedSearchOverviewFolder>[])
          SearchFolderCount(id: f.id, name: f.name, icon: f.icon, color: f.color, count: f.count),
      ],
    );
  }
}

/// `GET /v1/search/overview`. Null when it cannot be read (an older backend has no such route):
/// the overlay still shows its tiles, without numbers.
Future<SearchOverview?> getSearchOverview() async {
  final response = await makeApiCall(url: '${Env.apiBaseUrl}v1/search/overview', headers: {}, method: 'GET', body: '');
  if (response == null || response.statusCode != 200) return null;
  try {
    return SearchOverview.fromGenerated(
      search_wire.GeneratedSearchOverviewResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>),
    );
  } catch (e) {
    Logger.debug('getSearchOverview parse error: $e');
    return null;
  }
}

/// `GET /v1/users/daily-summaries/search`: recaps whose words match [query], newest first.
Future<List<DailySummary>> searchDailySummaries(String query, {int limit = 10}) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/daily-summaries/search?query=${Uri.encodeQueryComponent(query)}&limit=$limit',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null || response.statusCode != 200) return const [];
  try {
    final data = wire.GeneratedDailySummariesResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    return data.summaries?.map(DailySummary.fromGenerated).toList() ?? const [];
  } catch (e) {
    Logger.debug('searchDailySummaries parse error: $e');
    return const [];
  }
}

/// `GET /v1/action-items/search`: tasks semantically close to [query].
Future<List<ActionItemWithMetadata>> searchActionItems(String query, {int limit = 10}) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items/search?query=${Uri.encodeQueryComponent(query)}&limit=$limit',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null || response.statusCode != 200) return const [];
  try {
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    final items = body['action_items'];
    if (items is! List) return const [];
    return [
      for (final item in items.whereType<Map<String, dynamic>>())
        action_wire.GeneratedActionItemResponse.fromJson(item),
    ];
  } catch (e) {
    Logger.debug('searchActionItems parse error: $e');
    return const [];
  }
}

/// A memory matched by search: enough to show the row and find it again on the Memories page.
class MemorySearchHit {
  const MemorySearchHit({required this.id, required this.content});

  final String id;
  final String content;
}

/// `GET /memory/search`: the memories the user sees by default whose content matches [query].
Future<List<MemorySearchHit>> searchMemories(String query, {int limit = 10}) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}memory/search?query=${Uri.encodeQueryComponent(query)}&limit=$limit',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null || response.statusCode != 200) return const [];
  try {
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    final items = body['items'];
    if (items is! List) return const [];
    return [
      for (final item in items.whereType<Map<String, dynamic>>())
        if (item['memory_id'] is String && item['content'] is String)
          MemorySearchHit(id: item['memory_id'] as String, content: item['content'] as String),
    ];
  } catch (e) {
    Logger.debug('searchMemories parse error: $e');
    return const [];
  }
}
