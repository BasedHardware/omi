import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/env/env.dart';

class _TestEnvFields implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.test/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  setUpAll(() {
    try {
      Env.init(_TestEnvFields());
    } catch (_) {}
  });
  group('knowledgeGraphHttpUserMessage', () {
    test('does not contain the response body', () {
      const body = '{"detail":"index memories (updated_at DESC, __name__ ASC) is not ready SECRET_INTERNAL_TRACE"}';

      final loadMessage = KnowledgeGraphApi.knowledgeGraphHttpUserMessage(action: 'load', statusCode: 503, body: body);
      final rebuildMessage = KnowledgeGraphApi.knowledgeGraphHttpUserMessage(
        action: 'rebuild',
        statusCode: 500,
        body: body,
      );

      expect(loadMessage, isNot(contains(body)));
      expect(loadMessage, isNot(contains('SECRET_INTERNAL_TRACE')));
      expect(rebuildMessage, isNot(contains(body)));
      expect(rebuildMessage, isNot(contains('SECRET_INTERNAL_TRACE')));
      expect(loadMessage.toLowerCase(), contains('knowledge graph'));
      expect(rebuildMessage.toLowerCase(), contains('knowledge graph'));
    });

    test('handles 409 conflict cleanly without leaking backend details', () {
      const conflictBody =
          '{"detail":"Canonical knowledge graph state is derived from canonical memories and cannot be deleted or rebuilt directly."}';

      final message = KnowledgeGraphApi.knowledgeGraphHttpUserMessage(
        action: 'rebuild',
        statusCode: 409,
        body: conflictBody,
      );

      expect(message, "Couldn't rebuild knowledge graph");
      expect(message, isNot(contains(conflictBody)));
      expect(message, isNot(contains('Canonical knowledge graph state')));
    });
  });

  group('rebuildKnowledgeGraph', () {
    test('synthesizes canonical_up_to_date response on HTTP 409 conflict', () async {
      final result = await KnowledgeGraphApi.rebuildKnowledgeGraph(
        apiCaller: ({required url, required headers, required body, required method}) async {
          expect(method, 'POST');
          expect(url, contains('/v1/knowledge-graph/rebuild'));
          return http.Response(
            jsonEncode({
              'detail':
                  'Canonical knowledge graph state is derived from canonical memories and cannot be deleted or rebuilt directly.',
            }),
            409,
          );
        },
      );

      expect(result['status'], 'canonical_up_to_date');
      expect(result['nodes_count'], 0);
      expect(result['edges_count'], 0);
    });

    test('decodes valid response on HTTP 200', () async {
      final result = await KnowledgeGraphApi.rebuildKnowledgeGraph(
        apiCaller: ({required url, required headers, required body, required method}) async {
          return http.Response(
            jsonEncode({
              'status': 'rebuilding',
              'nodes_count': 12,
              'edges_count': 5,
            }),
            200,
          );
        },
      );

      expect(result['status'], 'rebuilding');
      expect(result['nodes_count'], 12);
      expect(result['edges_count'], 5);
    });

    test('throws exception with sanitized message on HTTP 500 failure', () async {
      expect(
        () => KnowledgeGraphApi.rebuildKnowledgeGraph(
          apiCaller: ({required url, required headers, required body, required method}) async {
            return http.Response('{"detail":"internal server error"}', 500);
          },
        ),
        throwsA(
          isA<Exception>().having(
            (e) => e.toString(),
            'message',
            contains("Couldn't rebuild knowledge graph"),
          ),
        ),
      );
    });
  });
}
