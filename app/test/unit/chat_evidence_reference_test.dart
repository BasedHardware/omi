import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/models/chat_evidence_reference.dart';

void main() {
  test(
    'round-trips the versioned envelope and all supported reference identities',
    () {
      const envelope = ChatEvidenceReferenceEnvelope(
        schemaVersion: 1,
        requestId: 'request-1',
        references: [
          ChatEvidenceReference(
            id: 'summary-1',
            kind: ChatEvidenceReferenceKind.conversationSummary,
            state: ChatEvidenceReferenceState.available,
            conversationId: 'conversation-1',
            title: 'Weekly summary',
          ),
          ChatEvidenceReference(
            id: 'segment-1',
            kind: ChatEvidenceReferenceKind.conversationSegment,
            state: ChatEvidenceReferenceState.loading,
            conversationId: 'conversation-1',
            segmentId: 'segment-1',
            startMs: 100,
            endMs: 200,
          ),
          ChatEvidenceReference(
            id: 'frame-1',
            kind: ChatEvidenceReferenceKind.keyframe,
            state: ChatEvidenceReferenceState.pruned,
            frameId: 'frame-1',
            capturedAtMs: 1234,
          ),
          ChatEvidenceReference(
            id: 'request-1',
            kind: ChatEvidenceReferenceKind.request,
            state: ChatEvidenceReferenceState.failed,
            requestId: 'request-1',
            errorCode: 'timeout',
          ),
        ],
      );

      final decoded = ChatEvidenceReferenceEnvelope.fromJson(envelope.toJson());

      expect(decoded.schemaVersion, 1);
      expect(decoded.requestId, 'request-1');
      expect(
        decoded.references[0].kind,
        ChatEvidenceReferenceKind.conversationSummary,
      );
      expect(decoded.references[1].segmentId, 'segment-1');
      expect(decoded.references[1].state, ChatEvidenceReferenceState.loading);
      expect(decoded.references[2].capturedAtMs, 1234);
      expect(decoded.references[3].errorCode, 'timeout');
    },
  );

  test(
    'accepts additive aliases and unknown future values without throwing',
    () {
      final decoded = ChatEvidenceReferenceEnvelope.fromJson({
        'schema_version': 99,
        'request_id': 'request-future',
        'evidence_refs': [
          {
            'reference_id': 'future-1',
            'type': 'future_kind',
            'status': 'future_state',
            'metadata': {'extra': true},
          },
        ],
        'future_field': 'ignored',
      });

      expect(decoded.schemaVersion, 99);
      expect(decoded.requestId, 'request-future');
      expect(decoded.references.single.id, 'future-1');
      expect(decoded.references.single.kind, ChatEvidenceReferenceKind.unknown);
      expect(
        decoded.references.single.state,
        ChatEvidenceReferenceState.unknown,
      );
      expect(decoded.references.single.metadata['extra'], isTrue);
    },
  );

  test(
    'invalid envelope values degrade to an empty optional reference list',
    () {
      expect(ChatEvidenceReferenceEnvelope.tryFromJson(null), isNull);
      expect(ChatEvidenceReferenceEnvelope.tryFromJson('legacy text'), isNull);
      expect(
        ChatEvidenceReferenceEnvelope.fromJson({'schema_version': 1}).isEmpty,
        isTrue,
      );
    },
  );

  test('fails closed for an explicitly malformed schema version', () {
    final decoded = ChatEvidenceReferenceEnvelope.fromJson({
      'schema_version': 'not-a-version',
      'references': [
        {'id': 'request-1', 'kind': 'request', 'state': 'available', 'request_id': 'req-1'},
      ],
    });

    expect(decoded.schemaVersion, 0);
    expect(decoded.references.single.kind, ChatEvidenceReferenceKind.unknown);
    expect(decoded.references.single.state, ChatEvidenceReferenceState.unknown);
    expect(decoded.references.single.canOpen, isFalse);
  });

  test('available references require a known resolvable identity', () {
    const unknown = ChatEvidenceReference(
      id: 'future',
      kind: ChatEvidenceReferenceKind.unknown,
      state: ChatEvidenceReferenceState.available,
    );
    const incompleteSegment = ChatEvidenceReference(
      id: 'segment',
      kind: ChatEvidenceReferenceKind.conversationSegment,
      state: ChatEvidenceReferenceState.available,
      conversationId: 'conversation',
    );
    const completeSegment = ChatEvidenceReference(
      id: 'segment',
      kind: ChatEvidenceReferenceKind.conversationSegment,
      state: ChatEvidenceReferenceState.available,
      conversationId: 'conversation',
      segmentId: 'segment',
    );

    expect(unknown.canOpen, isFalse);
    expect(incompleteSegment.canOpen, isFalse);
    expect(completeSegment.canOpen, isTrue);
  });

  test('bounds reference counts and display strings', () {
    final decoded = ChatEvidenceReferenceEnvelope.fromJson({
      'references': List.generate(
        40,
        (index) => {
          'id': 'id-$index',
          'kind': 'keyframe',
          'state': 'available',
          'frame_id': 'frame-$index',
          'title': 'x' * 500,
          'summary': 'y' * 2000,
        },
      ),
    });

    expect(decoded.references, hasLength(ChatEvidenceReference.maxReferencesPerEnvelope));
    expect(decoded.references.first.title, hasLength(ChatEvidenceReference.maxTitleCharacters));
    expect(decoded.references.first.summary, hasLength(ChatEvidenceReference.maxSummaryCharacters));
  });

  test('bounds errors and nested metadata', () {
    final decoded = ChatEvidenceReference.fromJson({
      'id': 'request-1',
      'kind': 'request',
      'state': 'failed',
      'request_id': 'req-1',
      'error_code': 'e' * 500,
      'error_message': 'm' * 2000,
      'metadata': {
        'nested': {
          'deeply': {
            'tooDeep': {'ignored': 'x'},
          },
        },
        'huge': 'x' * 20000,
      },
    });

    expect(decoded.errorCode, hasLength(ChatEvidenceReference.maxErrorCodeCharacters));
    expect(decoded.errorMessage, hasLength(ChatEvidenceReference.maxErrorMessageCharacters));
    expect(jsonEncode(decoded.metadata).length, lessThanOrEqualTo(2000));
  });

  test('malformed direct maps never throw', () {
    expect(
      () => ChatEvidenceReferenceEnvelope.tryFromJson({1: 'malformed'}),
      returnsNormally,
    );
    expect(ChatEvidenceReferenceEnvelope.tryFromJson({1: 'malformed'}), isNull);
  });
}
