// The detail title field follows a live conversation's server title only when the owner has not touched it.

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';

void main() {
  String? follow({String? previous = '', String next = 'Launch checklist', String field = '', bool editing = false}) =>
      followedServerTitle(previousServerTitle: previous, nextServerTitle: next, fieldText: field, editing: editing);

  test('an untitled live conversation takes the server title when it lands', () {
    expect(follow(), 'Launch checklist');
  });

  test('a renamed server title replaces the one the field still shows', () {
    expect(follow(previous: 'Launch checklist', next: 'Launch plan', field: 'Launch checklist'), 'Launch plan');
  });

  test('an unchanged server title leaves the field alone', () {
    expect(follow(previous: 'Launch checklist', field: 'Launch checklist'), isNull);
  });

  test('a field being edited is never overwritten', () {
    expect(follow(editing: true), isNull);
  });

  test('a typed or just-saved title survives a re-read, including one that predates the save', () {
    // Typed, not saved.
    expect(follow(field: 'My title'), isNull);
    // Saved "My title"; a stale read still carries the pre-save server title "Old".
    expect(follow(previous: '', next: 'Old', field: 'My title'), isNull);
    // The read that returns the saved title leaves it as it is.
    expect(follow(previous: 'Old', next: 'My title', field: 'My title'), isNull);
  });

  test('no server title seen yet (page not initialised) leaves the field alone', () {
    expect(follow(previous: null), isNull);
  });

  test('leaving an untouched field after a server rename saves nothing (the stale text is not edited)', () {
    // The field showed "" when it was focused; the server named it meanwhile; blur sends "".
    expect(titleEditedByOwner(text: '', shownServerTitle: ''), isFalse);
    expect(titleEditedByOwner(text: 'Old ', shownServerTitle: 'Old'), isFalse);
    expect(titleEditedByOwner(text: 'Mine', shownServerTitle: 'Old'), isTrue);
    expect(titleEditedByOwner(text: 'Mine', shownServerTitle: null), isTrue);
  });
}
