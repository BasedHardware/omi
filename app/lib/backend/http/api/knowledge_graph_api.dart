import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

class KnowledgeGraphApi {
  static final String _baseUrl = '${Env.apiBaseUrl}v1/knowledge-graph';

  static Future<Map<String, dynamic>> getKnowledgeGraph() async {
    final response = await makeApiCall(
      url: _baseUrl,
      headers: {},
      body: '',
      method: 'GET',
      timeout: const Duration(seconds: 60),
      retries: 2,
    );

    if (response != null && response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      throw Exception('Failed to load knowledge graph: ${response?.body}');
    }
  }

  static Future<Map<String, dynamic>> rebuildKnowledgeGraph() async {
    final response = await makeApiCall(
      url: '$_baseUrl/rebuild',
      headers: {},
      body: '{}',
      method: 'POST',
    );

    if (response != null && response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      throw Exception('Failed to rebuild knowledge graph: ${response?.body}');
    }
  }

  static Future<void> deleteKnowledgeGraph() async {
    final response = await makeApiCall(
      url: _baseUrl,
      headers: {},
      body: '{}',
      method: 'DELETE',
    );

    if (response == null || response.statusCode != 200) {
      throw Exception('Failed to delete knowledge graph: ${response?.body}');
    }
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
