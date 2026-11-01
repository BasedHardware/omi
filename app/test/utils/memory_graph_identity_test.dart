import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/memory_graph_identity.dart';

void main() {
  // Source of truth: backend/models/memory_promotion.py reserves "user";
  // canonical named entities get distinct ent_* IDs. The shipped canvas also
  // supports its legacy user-node anchor and explicit node_type: user records.
  test('recognizes owner IDs independently of their display label or type', () {
    for (final id in ['user', 'user-node']) {
      expect(memoryGraphIsUserNode({'id': id, 'label': 'Renamed', 'node_type': 'concept'}), isTrue);
    }
    expect(memoryGraphIsUserNode({'id': 'legacy-owner', 'label': 'Sam', 'node_type': 'user'}), isTrue);
  });

  test('names, pronouns and speculative types cannot establish owner identity', () {
    for (final label in ['Sam', 'Sam Altman', 'Me', 'The User', 'user', 'myself', 'I', 'Tú']) {
      for (final type in ['person', 'concept', 'primary_user', 'self', 'owner']) {
        expect(memoryGraphIsUserNode({'id': 'distinct-entity', 'label': label, 'node_type': type}), isFalse,
            reason: '$type/$label must stay distinct without an owner ID or explicit legacy user type');
      }
    }
    expect(memoryGraphIsUserNode({'id': 'USER', 'node_type': 'person'}), isFalse);
    expect(memoryGraphIsUserNode({'id': ' user ', 'node_type': 'person'}), isFalse);
  });

  test('canonical owner wins over legacy aliases independently of record order', () {
    final nodes = [
      {'id': 'legacy-owner', 'node_type': 'user'},
      {'id': 'user-node', 'node_type': 'person'},
      {'id': 'user', 'node_type': 'person'},
    ];
    expect(memoryGraphPrimaryOwnerId(nodes), 'user');
    expect(memoryGraphPrimaryOwnerId(nodes.reversed), 'user');
    expect(memoryGraphPrimaryOwnerId(nodes.take(2)), 'user-node');
  });

  test('typed legacy owners have deterministic selection and blank IDs are ignored', () {
    final nodes = [
      null,
      {'id': '', 'node_type': 'user'},
      {'id': 'z-owner', 'node_type': 'user'},
      {'id': 'a-owner', 'node_type': 'user'},
    ];
    expect(memoryGraphPrimaryOwnerId(nodes), 'a-owner');
    expect(memoryGraphPrimaryOwnerId(nodes.reversed), 'a-owner');
    expect(
        memoryGraphPrimaryOwnerId([
          {'id': '', 'node_type': 'user'}
        ]),
        'user-node');
  });

  test('unknown legacy names remain content, with a separate presentation anchor', () {
    expect(
        memoryGraphPrimaryOwnerId([
          {'id': 'contact-sam', 'label': 'Sam', 'node_type': 'person'},
          {'id': 'concept-i', 'label': 'I', 'node_type': 'concept'},
        ]),
        'user-node');
  });
}
