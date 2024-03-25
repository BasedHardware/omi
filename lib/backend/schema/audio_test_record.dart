import 'dart:async';

import 'package:collection/collection.dart';

import '/backend/schema/util/firestore_util.dart';

import 'index.dart';

class AudioTestRecord extends FirestoreRecord {
  AudioTestRecord._(
    super.reference,
    super.data,
  ) {
    _initializeFields();
  }

  // "name" field.
  String? _name;
  String get name => _name ?? '';
  bool hasName() => _name != null;

  // "audio" field.
  String? _audio;
  String get audio => _audio ?? '';
  bool hasAudio() => _audio != null;

  void _initializeFields() {
    _name = snapshotData['name'] as String?;
    _audio = snapshotData['audio'] as String?;
  }

  static CollectionReference get collection =>
      FirebaseFirestore.instance.collection('audio_test');

  static Stream<AudioTestRecord> getDocument(DocumentReference ref) =>
      ref.snapshots().map((s) => AudioTestRecord.fromSnapshot(s));

  static Future<AudioTestRecord> getDocumentOnce(DocumentReference ref) =>
      ref.get().then((s) => AudioTestRecord.fromSnapshot(s));

  static AudioTestRecord fromSnapshot(DocumentSnapshot snapshot) =>
      AudioTestRecord._(
        snapshot.reference,
        mapFromFirestore(snapshot.data() as Map<String, dynamic>),
      );

  static AudioTestRecord getDocumentFromData(
    Map<String, dynamic> data,
    DocumentReference reference,
  ) =>
      AudioTestRecord._(reference, mapFromFirestore(data));

  @override
  String toString() =>
      'AudioTestRecord(reference: ${reference.path}, data: $snapshotData)';

  @override
  int get hashCode => reference.path.hashCode;

  @override
  bool operator ==(other) =>
      other is AudioTestRecord &&
      reference.path.hashCode == other.reference.path.hashCode;
}

Map<String, dynamic> createAudioTestRecordData({
  String? name,
  String? audio,
}) {
  final firestoreData = mapToFirestore(
    <String, dynamic>{
      'name': name,
      'audio': audio,
    }.withoutNulls,
  );

  return firestoreData;
}

class AudioTestRecordDocumentEquality implements Equality<AudioTestRecord> {
  const AudioTestRecordDocumentEquality();

  @override
  bool equals(AudioTestRecord? e1, AudioTestRecord? e2) {
    return e1?.name == e2?.name && e1?.audio == e2?.audio;
  }

  @override
  int hash(AudioTestRecord? e) =>
      const ListEquality().hash([e?.name, e?.audio]);

  @override
  bool isValidKey(Object? o) => o is AudioTestRecord;
}
