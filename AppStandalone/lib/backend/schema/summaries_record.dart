import 'dart:async';

import 'package:collection/collection.dart';

import '/backend/schema/util/firestore_util.dart';
import '/backend/schema/enums/enums.dart';

import 'index.dart';

class SummariesRecord extends FirestoreRecord {
  SummariesRecord._(
    super.reference,
    super.data,
  ) {
    _initializeFields();
  }

  // "user" field.
  DocumentReference? _user;
  DocumentReference? get user => _user;
  bool hasUser() => _user != null;

  // "date" field.
  DateTime? _date;
  DateTime? get date => _date;
  bool hasDate() => _date != null;

  // "type" field.
  SummaryType? _type;
  SummaryType? get type => _type;
  bool hasType() => _type != null;

  // "summary" field.
  String? _summary;
  String get summary => _summary ?? '';
  bool hasSummary() => _summary != null;

  void _initializeFields() {
    _user = snapshotData['user'] as DocumentReference?;
    _date = snapshotData['date'] as DateTime?;
    _type = deserializeEnum<SummaryType>(snapshotData['type']);
    _summary = snapshotData['summary'] as String?;
  }

  static CollectionReference get collection =>
      FirebaseFirestore.instance.collection('summaries');

  static Stream<SummariesRecord> getDocument(DocumentReference ref) =>
      ref.snapshots().map((s) => SummariesRecord.fromSnapshot(s));

  static Future<SummariesRecord> getDocumentOnce(DocumentReference ref) =>
      ref.get().then((s) => SummariesRecord.fromSnapshot(s));

  static SummariesRecord fromSnapshot(DocumentSnapshot snapshot) =>
      SummariesRecord._(
        snapshot.reference,
        mapFromFirestore(snapshot.data() as Map<String, dynamic>),
      );

  static SummariesRecord getDocumentFromData(
    Map<String, dynamic> data,
    DocumentReference reference,
  ) =>
      SummariesRecord._(reference, mapFromFirestore(data));

  @override
  String toString() =>
      'SummariesRecord(reference: ${reference.path}, data: $snapshotData)';

  @override
  int get hashCode => reference.path.hashCode;

  @override
  bool operator ==(other) =>
      other is SummariesRecord &&
      reference.path.hashCode == other.reference.path.hashCode;
}

Map<String, dynamic> createSummariesRecordData({
  DocumentReference? user,
  DateTime? date,
  SummaryType? type,
  String? summary,
}) {
  final firestoreData = mapToFirestore(
    <String, dynamic>{
      'user': user,
      'date': date,
      'type': type,
      'summary': summary,
    }.withoutNulls,
  );

  return firestoreData;
}

class SummariesRecordDocumentEquality implements Equality<SummariesRecord> {
  const SummariesRecordDocumentEquality();

  @override
  bool equals(SummariesRecord? e1, SummariesRecord? e2) {
    return e1?.user == e2?.user &&
        e1?.date == e2?.date &&
        e1?.type == e2?.type &&
        e1?.summary == e2?.summary;
  }

  @override
  int hash(SummariesRecord? e) =>
      const ListEquality().hash([e?.user, e?.date, e?.type, e?.summary]);

  @override
  bool isValidKey(Object? o) => o is SummariesRecord;
}
