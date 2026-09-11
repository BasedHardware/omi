import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/knowledge_graph_api.dart';

void main() {
  test('knowledge-graph error message does not contain the response body', () {
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
}
