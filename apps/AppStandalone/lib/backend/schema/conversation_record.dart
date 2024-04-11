import 'dart:async';

import 'package:collection/collection.dart';

import '/backend/schema/util/firestore_util.dart';

import 'index.dart';

class ConversationRecord extends FirestoreRecord {
  ConversationRecord._(
    super.reference,
    super.data,
  ) {
    _initializeFields();
  }

  // "user" field.
  List<DocumentReference>? _user;
  List<DocumentReference> get user => _user ?? const [];
  bool hasUser() => _user != null;

  // "messages" field.
  List<DocumentReference>? _messages;
  List<DocumentReference> get messages => _messages ?? const [];
  bool hasMessages() => _messages != null;

  void _initializeFields() {
    _user = getDataList(snapshotData['user']);
    _messages = getDataList(snapshotData['messages']);
  }

  static CollectionReference get collection =>
      FirebaseFirestore.instance.collection('conversation');

  static Stream<ConversationRecord> getDocument(DocumentReference ref) =>
      ref.snapshots().map((s) => ConversationRecord.fromSnapshot(s));

  static Future<ConversationRecord> getDocumentOnce(DocumentReference ref) =>
      ref.get().then((s) => ConversationRecord.fromSnapshot(s));

  static ConversationRecord fromSnapshot(DocumentSnapshot snapshot) =>
      ConversationRecord._(
        snapshot.reference,
        mapFromFirestore(snapshot.data() as Map<String, dynamic>),
      );

  static ConversationRecord getDocumentFromData(
    Map<String, dynamic> data,
    DocumentReference reference,
  ) =>
      ConversationRecord._(reference, mapFromFirestore(data));

  @override
  String toString() =>
      'ConversationRecord(reference: ${reference.path}, data: $snapshotData)';

  @override
  int get hashCode => reference.path.hashCode;

  @override
  bool operator ==(other) =>
      other is ConversationRecord &&
      reference.path.hashCode == other.reference.path.hashCode;
}

Map<String, dynamic> createConversationRecordData() {
  final firestoreData = mapToFirestore(
    <String, dynamic>{}.withoutNulls,
  );

  return firestoreData;
}

class ConversationRecordDocumentEquality
    implements Equality<ConversationRecord> {
  const ConversationRecordDocumentEquality();

  @override
  bool equals(ConversationRecord? e1, ConversationRecord? e2) {
    const listEquality = ListEquality();
    return listEquality.equals(e1?.user, e2?.user) &&
        listEquality.equals(e1?.messages, e2?.messages);
  }

  @override
  int hash(ConversationRecord? e) =>
      const ListEquality().hash([e?.user, e?.messages]);

  @override
  bool isValidKey(Object? o) => o is ConversationRecord;
}
