import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/misc_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/memory_graph_identity.dart';

class KnowledgeGraphApi {
  /// Short user-facing copy for a knowledge-graph HTTP failure.
  ///
  /// [statusCode] and [body] are accepted so a regression that interpolates
  /// them into the returned string is caught by tests. They belong in debug
  /// logs only.
  @visibleForTesting
  static String knowledgeGraphHttpUserMessage({required String action, int? statusCode, String? body}) {
    final _ = (statusCode, body);
    return "Couldn't $action knowledge graph";
  }

  static Never _throwHttpFailure({required String action, int? statusCode, String? body}) {
    Logger.debug('Failed to $action knowledge graph: status=$statusCode body=$body');
    throw Exception(knowledgeGraphHttpUserMessage(action: action, statusCode: statusCode, body: body));
  }

  /// Preserve the compatibility/shared projection (including #12878) when it
  /// already has a map. Empty/owner-only views recover through the canonical
  /// catalog and signed pages. Never mix two canonical read revisions.
  /// No read, refresh, or Load More action mutates/rebuilds memory state.
  static Future<Map<String, dynamic>> getKnowledgeGraph({
    String? cursor,
    @visibleForTesting Future<http.Response?> Function(String url)? apiCaller,
    @visibleForTesting bool Function()? isCurrent,
  }) async {
    // Capture explicit endpoint URLs before awaiting: the request stays pinned
    // and the app-client schema inventory can see each public contract.
    final origin = Env.apiBaseUrl;
    final baseUrl = '${Env.apiBaseUrl}v1/knowledge-graph';
    final canonicalUrl = '${Env.apiBaseUrl}v1/knowledge-graph/canonical';
    final session = apiCaller == null ? AuthService.instance.captureSessionSnapshot() : null;
    bool current() =>
        Env.apiBaseUrl == origin &&
        (isCurrent?.call() ??
            (apiCaller != null || (session != null && AuthService.instance.isSessionSnapshotCurrent(session))));
    Future<http.Response?> read(String url) async {
      if (!current()) throw const KnowledgeGraphSessionChanged();
      final response = apiCaller != null
          ? await apiCaller(url)
          : await makeApiCall(
              url: url,
              headers: {},
              body: '',
              method: 'GET',
              timeout: const Duration(seconds: 30),
              retries: 0,
              canSend: current,
            );
      if (!current()) throw const KnowledgeGraphSessionChanged();
      return response;
    }

    Map<String, dynamic>? legacy;
    if (cursor == null) {
      final compatibility = await read(baseUrl);
      if (compatibility?.statusCode == 401 || compatibility?.statusCode == 403) {
        throw const KnowledgeGraphSessionChanged();
      }
      // Recover a successfully read empty view, not a failed expensive read.
      // A gateway failure must not fan out into another graph request.
      if (compatibility == null || compatibility.statusCode != 200) {
        _throwHttpFailure(action: 'load', statusCode: compatibility?.statusCode, body: compatibility?.body);
      }
      legacy = wire.GeneratedKnowledgeGraphResponse.fromJson(jsonDecode(compatibility.body) as Map<String, dynamic>)
          .toJson();
      if ((legacy['nodes'] as List).any((node) => !memoryGraphIsUserNode(node as Map))) {
        return {
          ...legacy,
          '_backend_origin': baseUrl,
          '_owner_generation': session == null ? null : '${session.ownerUid}:${session.generation}'
        };
      }
    }
    final uri = Uri.parse(canonicalUrl).replace(queryParameters: {
      'limit': '100',
      if (cursor != null) 'cursor': cursor,
    });
    final response = await read(uri.toString());
    if (response?.statusCode == 200) {
      final page =
          wire.GeneratedCanonicalKnowledgeGraphResponse.fromJson(jsonDecode(response!.body) as Map<String, dynamic>);
      if (page.hasMore && (page.nextCursor == null || page.nextCursor!.isEmpty || page.nextCursor == cursor)) {
        throw const FormatException('Invalid knowledge graph cursor');
      }
      return mergeKnowledgeGraphPages({
        'nodes': [],
        'edges': []
      }, {
        ...page.toJson(),
        'canonical': true,
        '_backend_origin': baseUrl,
        'truncated': page.hasMore,
        '_owner_generation': session == null ? null : '${session.ownerUid}:${session.generation}',
      });
    }
    if (cursor != null && response?.statusCode == 400) {
      throw const KnowledgeGraphCursorExpired();
    }
    if (response?.statusCode == 401 || response?.statusCode == 403) {
      throw const KnowledgeGraphSessionChanged();
    }
    // The existing compatibility route serves legacy-only accounts. An empty
    // compatibility response during a canonical outage cannot prove emptiness.
    if (cursor == null &&
        legacy != null &&
        (response?.statusCode == 404 ||
            (response?.statusCode == 503 && response?.headers['x-omi-knowledge-graph-state'] == 'unestablished'))) {
      return {
        ...legacy,
        '_backend_origin': baseUrl,
        '_owner_generation': session == null ? null : '${session.ownerUid}:${session.generation}'
      };
    }
    _throwHttpFailure(action: 'load', statusCode: response?.statusCode, body: response?.body);
  }

  /// Optional onboarding warm-up. Only a successfully read empty legacy graph
  /// may schedule a rebuild; canonical graphs are derived on read.
  /// Read failures (including a replaced session) propagate to onboarding's
  /// best-effort boundary. They are not evidence that legacy recovery is safe.
  static Future<void> prebuildForOnboarding() async {
    final current = await getKnowledgeGraph();
    if (current['canonical'] == true) return;
    final nodes = current['nodes'] as List<dynamic>? ?? const [];
    final hasGraph = nodes.any((node) => (node['id'] ?? '') != 'user-node');
    if (hasGraph) return;

    final rebuildResult = await rebuildKnowledgeGraph();
    final status = rebuildResult['status'];
    // 'canonical_up_to_date' is the synthetic client status returned on HTTP 409.
    if (status == 'canonical_up_to_date') {
      return;
    }
    await waitForGraphStability(
      timeout: const Duration(seconds: 25),
      interval: const Duration(seconds: 2),
      stabilityChecks: 1,
    );
  }

  /// Triggers a rebuild of the knowledge graph.
  ///
  /// Accounts with canonical memory assertions return HTTP 409
  /// (CANONICAL_GRAPH_MUTATION_CONFLICT) because their derived state is
  /// protected. A conflict does not prove that the map is populated or current.
  /// This method preserves the historical client-side
  /// [wire.GeneratedRebuildResponse] with status `'canonical_up_to_date'` so
  /// callers can recognize this terminal state without polling or failing.
  static Future<Map<String, dynamic>> rebuildKnowledgeGraph({
    @visibleForTesting
    Future<http.Response?> Function({
      required String url,
      required Map<String, String> headers,
      required String body,
      required String method,
    })? apiCaller,
  }) async {
    final makeCall = apiCaller ?? makeApiCall;
    final response =
        await makeCall(url: '${Env.apiBaseUrl}v1/knowledge-graph/rebuild', headers: {}, body: '{}', method: 'POST');

    if (response != null && response.statusCode == 200) {
      return wire.GeneratedRebuildResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>).toJson();
    }
    if (response != null && response.statusCode == 409) {
      Logger.debug('Knowledge graph rebuild skipped: account has canonical graph state');
      // Historical status name: mutation is disabled; this is not a freshness check.
      return const wire.GeneratedRebuildResponse(
        edgesCount: 0,
        nodesCount: 0,
        status: 'canonical_up_to_date',
      ).toJson();
    }
    _throwHttpFailure(action: 'rebuild', statusCode: response?.statusCode, body: response?.body);
  }

  /// Polls the graph endpoint until the node count stabilizes or timeout is reached.
  /// Returns the final graph data.
  static Future<Map<String, dynamic>> waitForGraphStability({
    Duration timeout = const Duration(seconds: 45),
    Duration interval = const Duration(seconds: 2),
    int stabilityChecks = 2,
  }) async {
    int stableCount = 0;
    int lastCount = -1;
    final stopwatch = Stopwatch()..start();

    while (stopwatch.elapsed < timeout) {
      try {
        await Future.delayed(interval);

        final data = await getKnowledgeGraph();
        final nodes = data['nodes'] as List<dynamic>? ?? [];
        final count = nodes.length;

        // Reset stability count if node count changes
        if (count > 0 && count == lastCount) {
          stableCount++;
        } else {
          stableCount = 0;
        }

        lastCount = count;

        // If stable for [stabilityChecks] cycles and we have data, return it
        if (stableCount >= stabilityChecks && count > 0) {
          return data;
        }
      } catch (e) {
        // Silently ignore temporary fetch errors during polling
        print('Polling error: $e');
      }
    }

    // Return whatever we have at timeout
    return await getKnowledgeGraph();
  }
}

/// Merge only server-authored records. Catalog entries remain separate from
/// graph entities: a memory's existence does not establish a relationship.
Map<String, dynamic> mergeKnowledgeGraphPages(Map<String, dynamic> earlier, Map<String, dynamic> page) {
  final owner = earlier['_owner_generation'];
  if ((owner != null && page['_owner_generation'] != owner) ||
      (earlier['_backend_origin'] != null && page['_backend_origin'] != earlier['_backend_origin'])) {
    throw const KnowledgeGraphSessionChanged();
  }
  List<Map<String, dynamic>> records(String key) {
    final byId = <String, Map<String, dynamic>>{};
    for (final record in [...?earlier[key] as List?, ...?page[key] as List?]) {
      final value = Map<String, dynamic>.from(record as Map);
      final id = value['id'] as String?;
      if (id != null && id.isNotEmpty) byId[id] = value;
    }
    return byId.values.toList();
  }

  final nodes = records('nodes');
  final ids = nodes.map((node) => node['id']).toSet();
  final edges =
      records('edges').where((edge) => ids.contains(edge['source_id']) && ids.contains(edge['target_id'])).toList();
  final sharedTruncated = earlier['shared_truncated'] ?? earlier['truncated'] ?? false;
  return {
    'canonical': page['canonical'] == true,
    '_backend_origin': page['_backend_origin'],
    '_owner_generation': page['_owner_generation'],
    'nodes': nodes,
    'edges': edges,
    'catalog_nodes': records('catalog_nodes'),
    'has_more': page['has_more'] ?? false,
    'next_cursor': page['next_cursor'],
    'shared_truncated': sharedTruncated,
    'truncated': sharedTruncated == true || page['has_more'] == true,
    'node_count': nodes.length,
    'edge_count': edges.length,
  };
}

/// A graph revision changed between pages. Restart the read, never rebuild it.
class KnowledgeGraphCursorExpired implements Exception {
  const KnowledgeGraphCursorExpired();
}

class KnowledgeGraphSessionChanged implements Exception {
  const KnowledgeGraphSessionChanged();
}
