import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as action_wire;
import 'package:omi/backend/schema/gen/search_wire.g.dart' as search_wire;
import 'package:omi/backend/schema/gen/users_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

Map<String, dynamic> _responseObject(String body) {
  final decoded = jsonDecode(body);
  if (decoded is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
  return decoded;
}

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

/// `GET /v1/search/overview`. A missing route remains a distinct failure.
Future<ApiResult<SearchOverview>> getSearchOverview({ApiSend? send}) => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/search/overview', method: 'GET'),
      send: send,
      decode: (body) => SearchOverview.fromGenerated(search_wire.GeneratedSearchOverviewResponse.fromJson(
        _responseObject(body),
      )),
    );

/// `GET /v1/users/daily-summaries/search`: recaps whose words match [query], newest first.
Future<ApiResult<List<DailySummary>>> searchDailySummaries(String query, {int limit = 10, ApiSend? send}) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/users/daily-summaries/search?query=${Uri.encodeQueryComponent(query)}&limit=$limit',
        method: 'GET',
      ),
      send: send,
      decode: (body) {
        final response = wire.GeneratedDailySummariesResponse.fromJson(_responseObject(body));
        return [
          for (final summary in response.summaries ?? const <wire.GeneratedDailySummaryResponse>[])
            DailySummary.fromGenerated(summary),
        ];
      },
    );

/// `GET /v1/action-items/search`: tasks semantically close to [query].
Future<ApiResult<List<ActionItemWithMetadata>>> searchActionItems(String query, {int limit = 10, ApiSend? send}) =>
    executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/action-items/search?query=${Uri.encodeQueryComponent(query)}&limit=$limit',
        method: 'GET',
      ),
      send: send,
      decode: (body) => action_wire.GeneratedActionItemsSearchResponse.fromJson(_responseObject(body)).actionItems,
    );

/// A memory matched by search: enough to show the row and find it again on the Memories page.
class MemorySearchHit {
  const MemorySearchHit({required this.id, required this.content});

  final String id;
  final String content;
}

/// `GET /memory/search`: the memories the user sees by default whose content matches [query].
Future<ApiResult<List<MemorySearchHit>>> searchMemories(String query, {int limit = 10, ApiSend? send}) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}memory/search?query=${Uri.encodeQueryComponent(query)}&limit=$limit',
        method: 'GET',
      ),
      send: send,
      decode: (body) => [
        for (final item in search_wire.GeneratedProductMemorySearchResponse.fromJson(_responseObject(body)).items)
          MemorySearchHit(id: item.memoryId, content: item.content),
      ],
    );
