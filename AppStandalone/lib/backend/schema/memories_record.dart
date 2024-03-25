import 'dart:async';

import 'package:collection/collection.dart';

import '/backend/schema/util/firestore_util.dart';

import 'index.dart';

class MemoriesRecord extends FirestoreRecord {
  MemoriesRecord._(
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

  // "memory" field.
  String? _memory;
  String get memory => _memory ?? '';
  bool hasMemory() => _memory != null;

  // "structuredMemory" field.
  String? _structuredMemory;
  String get structuredMemory => _structuredMemory ?? '';
  bool hasStructuredMemory() => _structuredMemory != null;

  // "feedback" field.
  String? _feedback;
  String get feedback => _feedback ?? '';
  bool hasFeedback() => _feedback != null;

  // "ToShowToUser_Show_Hide" field.
  String? _toShowToUserShowHide;
  String get toShowToUserShowHide => _toShowToUserShowHide ?? '';
  bool hasToShowToUserShowHide() => _toShowToUserShowHide != null;

  // "emptyMemory" field.
  bool? _emptyMemory;
  bool get emptyMemory => _emptyMemory ?? false;
  bool hasEmptyMemory() => _emptyMemory != null;

  // "isUselessMemory" field.
  bool? _isUselessMemory;
  bool get isUselessMemory => _isUselessMemory ?? false;
  bool hasIsUselessMemory() => _isUselessMemory != null;

  // "DateWithMemory" field.
  String? _dateWithMemory;
  String get dateWithMemory => _dateWithMemory ?? '';
  bool hasDateWithMemory() => _dateWithMemory != null;

  // "audio" field.
  String? _audio;
  String get audio => _audio ?? '';
  bool hasAudio() => _audio != null;

  // "vector" field.
  List<double>? _vector;
  List<double> get vector => _vector ?? const [];
  bool hasVector() => _vector != null;

  void _initializeFields() {
    _user = snapshotData['user'] as DocumentReference?;
    _date = snapshotData['date'] as DateTime?;
    _memory = snapshotData['memory'] as String?;
    _structuredMemory = snapshotData['structuredMemory'] as String?;
    _feedback = snapshotData['feedback'] as String?;
    _toShowToUserShowHide = snapshotData['ToShowToUser_Show_Hide'] as String?;
    _emptyMemory = snapshotData['emptyMemory'] as bool?;
    _isUselessMemory = snapshotData['isUselessMemory'] as bool?;
    _dateWithMemory = snapshotData['DateWithMemory'] as String?;
    _audio = snapshotData['audio'] as String?;
    _vector = getDataList(snapshotData['vector']);
  }

  static CollectionReference get collection =>
      FirebaseFirestore.instance.collection('memories');

  static Stream<MemoriesRecord> getDocument(DocumentReference ref) =>
      ref.snapshots().map((s) => MemoriesRecord.fromSnapshot(s));

  static Future<MemoriesRecord> getDocumentOnce(DocumentReference ref) =>
      ref.get().then((s) => MemoriesRecord.fromSnapshot(s));

  static MemoriesRecord fromSnapshot(DocumentSnapshot snapshot) =>
      MemoriesRecord._(
        snapshot.reference,
        mapFromFirestore(snapshot.data() as Map<String, dynamic>),
      );

  static MemoriesRecord getDocumentFromData(
    Map<String, dynamic> data,
    DocumentReference reference,
  ) =>
      MemoriesRecord._(reference, mapFromFirestore(data));

  @override
  String toString() =>
      'MemoriesRecord(reference: ${reference.path}, data: $snapshotData)';

  @override
  int get hashCode => reference.path.hashCode;

  @override
  bool operator ==(other) =>
      other is MemoriesRecord &&
      reference.path.hashCode == other.reference.path.hashCode;
}

Map<String, dynamic> createMemoriesRecordData({
  DocumentReference? user,
  DateTime? date,
  String? memory,
  String? structuredMemory,
  String? feedback,
  String? toShowToUserShowHide,
  bool? emptyMemory,
  bool? isUselessMemory,
  String? dateWithMemory,
  String? audio,
}) {
  final firestoreData = mapToFirestore(
    <String, dynamic>{
      'user': user,
      'date': date,
      'memory': memory,
      'structuredMemory': structuredMemory,
      'feedback': feedback,
      'ToShowToUser_Show_Hide': toShowToUserShowHide,
      'emptyMemory': emptyMemory,
      'isUselessMemory': isUselessMemory,
      'DateWithMemory': dateWithMemory,
      'audio': audio,
    }.withoutNulls,
  );

  return firestoreData;
}

class MemoriesRecordDocumentEquality implements Equality<MemoriesRecord> {
  const MemoriesRecordDocumentEquality();

  @override
  bool equals(MemoriesRecord? e1, MemoriesRecord? e2) {
    const listEquality = ListEquality();
    return e1?.user == e2?.user &&
        e1?.date == e2?.date &&
        e1?.memory == e2?.memory &&
        e1?.structuredMemory == e2?.structuredMemory &&
        e1?.feedback == e2?.feedback &&
        e1?.toShowToUserShowHide == e2?.toShowToUserShowHide &&
        e1?.emptyMemory == e2?.emptyMemory &&
        e1?.isUselessMemory == e2?.isUselessMemory &&
        e1?.dateWithMemory == e2?.dateWithMemory &&
        e1?.audio == e2?.audio &&
        listEquality.equals(e1?.vector, e2?.vector);
  }

  @override
  int hash(MemoriesRecord? e) => const ListEquality().hash([
        e?.user,
        e?.date,
        e?.memory,
        e?.structuredMemory,
        e?.feedback,
        e?.toShowToUserShowHide,
        e?.emptyMemory,
        e?.isUselessMemory,
        e?.dateWithMemory,
        e?.audio,
        e?.vector
      ]);

  @override
  bool isValidKey(Object? o) => o is MemoriesRecord;
}
