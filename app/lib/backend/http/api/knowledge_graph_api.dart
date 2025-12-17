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
    );

    if (response != null && response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      throw Exception('Failed to load knowledge graph: ${response?.body}');
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
}
